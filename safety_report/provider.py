"""按任务快照使用模型配置；不修改进程环境，不回传密钥。"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import threading
import time
from contextvars import ContextVar

CALL_STATS = ContextVar("model_call_stats", default=None)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_SOCKETS = {}


class ModelDeadlineExceeded(ValueError):
    pass


class ModelOutputFormatError(ValueError):
    """The provider responded, but did not supply usable structured output."""


class ModelOutputTruncated(ModelOutputFormatError):
    pass


def is_local_ollama(config):
    config = config or {}
    return config.get("provider") == "ollama" and urllib.parse.urlsplit(config.get("base_url", "")).hostname in {"localhost", "127.0.0.1", "::1"}


class GenerationCancelled(Exception):
    pass


def cancel_request(cancel_event):
    """Close the active provider socket so a streaming generation stops promptly."""
    if cancel_event is None:
        return
    cancel_event.set()
    with _ACTIVE_LOCK:
        sock = _ACTIVE_SOCKETS.get(id(cancel_event))
    if sock:
        try:
            sock.shutdown(2)
        except OSError:
            pass


def environment_config():
    return {'id': 'environment', 'name': '管理员环境配置', 'provider': 'custom',
            'base_url': os.environ.get('LLM_BASE_URL', ''), 'model': os.environ.get('LLM_MODEL', ''),
            'api_key': os.environ.get('LLM_API_KEY', ''), 'json_mode': os.environ.get('LLM_JSON_MODE', '1') == '1'}


def configured(config=None):
    config = environment_config() if config is None else config
    return bool(config.get('base_url') and config.get('model'))


def validate_config(config, require_model=True):
    if not isinstance(config, dict):
        raise ValueError('模型配置格式不正确')
    base = str(config.get('base_url', '')).strip().rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('模型地址须为不含密钥、查询参数的 HTTP(S) 服务地址')
    if base.endswith('/chat/completions'):
        raise ValueError('服务地址请去掉结尾 /chat/completions，保留供应商要求的 /v1 等路径')
    if parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('非本机模型服务请使用 HTTPS，避免明文传输资料和密钥')
    model = str(config.get('model', '')).strip()
    if require_model and not model:
        raise ValueError('请选择或填写模型 ID')
    if len(model) > 150 or len(str(config.get('api_key', ''))) > 1000:
        raise ValueError('模型名称或密钥过长')
    return {**config, 'base_url': base, 'model': model, 'json_mode': config.get('json_mode', True) is True}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('模型服务发生重定向，请填写供应商的最终 API 地址')


def request_json(config, suffix, body=None, timeout=240, cancel_event=None):
    config = validate_config(config, require_model=body is not None)
    headers = {'Content-Type': 'application/json'}
    if config.get('api_key'):
        headers['Authorization'] = 'Bearer ' + config['api_key']
    request = urllib.request.Request(config['base_url'] + suffix,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=headers)
    deadline = time.monotonic() + timeout
    expired = threading.Event()
    watchdog = None
    try:
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled()
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
            def expire():
                expired.set()
                if sock:
                    try:
                        sock.shutdown(2)
                    except OSError:
                        pass
            watchdog = threading.Timer(max(0, deadline - time.monotonic()), expire)
            watchdog.daemon = True
            watchdog.start()
            if cancel_event and cancel_event.is_set():
                raise GenerationCancelled()
            if body and body.get('stream'):
                sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                if sock and cancel_event:
                    with _ACTIVE_LOCK:
                        _ACTIVE_SOCKETS[id(cancel_event)] = sock
                pieces = []
                streamed = response.headers.get_content_type() == 'text/event-stream'
                if streamed:
                    finish_reason = None
                    reasoning_chars = 0
                    stream_error = False
                    usage = None
                    for line in response:
                        if cancel_event and cancel_event.is_set():
                            raise GenerationCancelled()
                        if not line.startswith(b'data:'):
                            continue
                        item = line[5:].strip()
                        if item == b'[DONE]':
                            break
                        try:
                            event = json.loads(item)
                            if isinstance(event.get('usage'), dict):
                                usage = event['usage']
                            if event.get('error'):
                                stream_error = True
                                continue
                            choice = event['choices'][0]
                            delta = choice.get('delta', {})
                            content = delta.get('content', '')
                            if isinstance(content, str):
                                pieces.append(content)
                            elif isinstance(content, list):
                                pieces.extend(part.get('text', '') for part in content
                                              if isinstance(part, dict) and isinstance(part.get('text'), str))
                            reasoning = delta.get('reasoning', '')
                            if isinstance(reasoning, str):
                                reasoning_chars += len(reasoning)
                            if choice.get('finish_reason') is not None:
                                finish_reason = choice['finish_reason']
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                    raw = json.dumps({'choices': [{'finish_reason': finish_reason,
                        'message': {'content': ''.join(pieces)}}],
                        'usage': usage, '_stream_meta': {'reasoning_chars': reasoning_chars, 'provider_error': stream_error}}).encode()
                else:
                    raw = response.read(8_000_001)
                if cancel_event and cancel_event.is_set():
                    raise GenerationCancelled()
            else:
                raw = response.read(8_000_001)
        if expired.is_set():
            raise ModelDeadlineExceeded('本次模型调用超过总时限，已停止；已完成小节保留，请缩小任务后继续')
        if len(raw) > 8_000_000:
            raise ValueError('模型响应过大')
        decoded = json.loads(raw)
        stats = CALL_STATS.get()
        if stats is not None and isinstance(decoded, dict):
            usage = decoded.get('usage') or {}
            choices = decoded.get('choices') or [{}]
            stats.append({'finish_reason': choices[0].get('finish_reason'),
                          **{k: usage.get(k) if isinstance(usage.get(k), int) else None
                             for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}})
        return decoded
    except GenerationCancelled:
        raise
    except urllib.error.HTTPError as exc:
        message = {401: '密钥不正确或与服务地域不匹配', 403: '没有此模型的使用权限',
                   404: '服务地址或模型 ID 不正确', 429: '请求过于频繁或额度不足'}.get(exc.code, '请检查供应商服务状态')
        raise ValueError(f'模型服务 HTTP {exc.code}：{message}') from None
    except (urllib.error.URLError, TimeoutError):
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled() from None
        raise ValueError('模型服务连接失败或超时，请检查地址和网络') from None
    except (UnicodeError, json.JSONDecodeError):
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled() from None
        raise ValueError('模型服务没有返回有效 JSON') from None
    except Exception:
        if expired.is_set():
            raise ModelDeadlineExceeded('本次模型调用超过总时限，已停止；已完成小节保留') from None
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled() from None
        raise
    finally:
        if watchdog:
            watchdog.cancel()
        if cancel_event:
            with _ACTIVE_LOCK:
                _ACTIVE_SOCKETS.pop(id(cancel_event), None)


def list_models(config):
    result = request_json(config, '/models', timeout=25)
    return sorted({str(row['id']) for row in result.get('data', []) if isinstance(row, dict) and row.get('id')})


def complete_json(system, payload, config=None, max_tokens=8000, cancel_event=None, response_schema=None):
    config = validate_config(environment_config() if config is None else config)
    body = {'model': config['model'], 'messages': [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], 'stream': cancel_event is not None, 'max_tokens': max_tokens}
    if config.get('json_mode', True):
        body['response_format'] = {'type': 'json_object'}
    if is_local_ollama(config) and config.get('json_mode', True) and payload.get('target_subsections'):
        from .output_schema import report_unit_schema
        body['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'report_unit', 'strict': True,
            'schema': report_unit_schema(payload['target_subsections'], payload.get('evidence', []))}}
    if is_local_ollama(config) and response_schema is not None:
        body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'task_result', 'strict': True, 'schema': response_schema}}
    if is_local_ollama(config) and body['stream']:
        body['stream_options'] = {'include_usage': True}
    # MiniMax M3.1 Flash on OpenRouter spends from max_tokens on hidden reasoning.
    # A per-request reasoning cap leaves most of the chapter budget for visible JSON.
    host = urllib.parse.urlsplit(config['base_url']).hostname or ''
    # Qwen 3.5's default thinking can consume the entire JSON output budget on small local machines.
    # Limit this provider-specific setting to local Ollama Qwen 3.5; other models stay unchanged.
    if config.get('provider') == 'ollama' and host in {'localhost', '127.0.0.1', '::1'} and config['model'].lower().startswith('qwen3.5:'):
        body['reasoning_effort'] = 'none'
    if host == 'api.deepseek.com' and config['model'].lower() in {'deepseek-flash', 'deepseek-v4-pro'}:
        if payload.get('target_subsections') or payload.get('task_type') in {'evidence_review','structured_extraction','materials_review'}:
            # Bounded writing/review tasks reserve the budget for visible JSON.
            body['thinking'] = {'type': 'disabled'}
        else:
            body['reasoning_effort'] = 'low'
    if host == 'openrouter.ai' and config['model'].lower().startswith('minimax/minimax-m3.1-flash'):
        body['reasoning'] = {'max_tokens': 1200, 'exclude': True}
    result = request_json(config, '/chat/completions', body, cancel_event=cancel_event)
    # DeepSeek thinking may exhaust the output budget before returning JSON.
    # Retry once without thinking only when the provider explicitly reports truncation.
    if (host == 'api.deepseek.com' and config['model'].lower() == 'deepseek-flash'
            and body.get('thinking', {}).get('type') != 'disabled'
            and result.get('choices') and result['choices'][0].get('finish_reason') == 'length'):
        body.pop('reasoning_effort', None)
        body['thinking'] = {'type': 'disabled'}
        result = request_json(config, '/chat/completions', body, cancel_event=cancel_event)
    try:
        if result.get('_stream_meta', {}).get('provider_error'):
            raise ValueError('模型服务在流式输出中返回错误，请稍后重试或切换模型')
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ModelOutputTruncated('本节点模型输出达到上限而被截断，已完成的小节保留；请重试当前任务，仍失败时可继续细分小节或调整模型输出容量')
        message = choice['message']
        if isinstance(message.get('parsed'), dict):
            return message['parsed']
        content = message.get('content')
        if isinstance(content, list):
            content = ''.join(part.get('text', '') for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise ModelOutputFormatError('模型没有返回文本内容')
        content = content.strip()
        if not content:
            if message.get('refusal'):
                raise ValueError('模型拒绝了本次生成，请检查模型权限或任务内容')
            if result.get('_stream_meta', {}).get('reasoning_chars'):
                raise ValueError('模型只返回了推理内容，没有输出章节正文；请切换模型或降低推理强度')
            raise ModelOutputFormatError('模型返回了空正文，请稍后重试或切换模型')
        # Compatible providers sometimes wrap otherwise valid JSON in prose or fences.
        # Parse a complete object from the response instead of rejecting the whole chapter.
        decoder = json.JSONDecoder()
        for index, character in enumerate(content):
            if character == '{':
                try:
                    parsed, _ = decoder.raw_decode(content[index:])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        output = json.loads(content)
        if not isinstance(output, dict):
            raise ModelOutputFormatError('模型输出必须是 JSON 对象')
        return output
    except json.JSONDecodeError:
        raise ModelOutputFormatError(f'模型返回了 {len(content)} 个字符，但没有形成完整 JSON 对象；输出可能被截断或格式不符合要求') from None
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError('模型服务返回格式不完整，未找到标准 choices/message/content 字段') from None


def test_model(config):
    result = complete_json('只返回 JSON 对象 {"ok":true}。不要解释。', {'task': '连接测试，不含任何项目资料'}, config, max_tokens=1200)
    if result.get('ok') is not True:
        raise ValueError('接口可访问，但模型没有按要求返回结构化结果')
    return {'ok': True, 'message': '连接与 JSON 输出测试通过；未发送项目资料'}
