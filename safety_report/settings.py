import json
import os
from pathlib import Path
import re
import secrets
import threading
from .provider import environment_config, configured, validate_config

LOCK = threading.RLock()
PRESETS = [
    {'id': 'deepseek', 'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com', 'key_required': True},
    {'id': 'qwen', 'name': '通义千问 · 百炼（北京）', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'key_required': True},
    {'id': 'ollama', 'name': 'Ollama · 本机模型', 'base_url': 'http://127.0.0.1:11434/v1', 'key_required': False},
    {'id': 'custom', 'name': '自定义兼容服务', 'base_url': '', 'key_required': False},
]


def read(data):
    path = Path(data) / 'settings.json'
    result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'models': [], 'default_model_id': ''}
    if configured() and not any(m['id'] == 'environment' for m in result['models']):
        result['models'].append(environment_config())
        if not result['default_model_id']:
            result['default_model_id'] = 'environment'
    return result


def public(data):
    with LOCK:
        result = read(data)
        return {'models': [{k: v for k, v in m.items() if k != 'api_key'} | {'key_saved': bool(m.get('api_key'))} for m in result['models']],
                'default_model_id': result['default_model_id'], 'presets': PRESETS}


def resolve(data, model_id=None):
    with LOCK:
        result = read(data)
        model_id = model_id or result['default_model_id']
        model = next((dict(m) for m in result['models'] if m['id'] == model_id), None)
        if not model:
            raise ValueError('请先在“模型设置”中保存并选择一个模型')
        return validate_config(model)


def merge_input(data, values, require_model=True):
    with LOCK:
        previous = next((m for m in read(data)['models'] if m['id'] == values.get('id')), {})
        result = {**previous, **{k: v for k, v in values.items() if k in {'id', 'name', 'provider', 'base_url', 'model', 'json_mode'}}}
        key = values.get('api_key')
        if key:
            result['api_key'] = key.strip()
        elif values.get('clear_key'):
            result['api_key'] = ''
        elif previous and (str(result.get('base_url', '')).rstrip('/') != str(previous.get('base_url', '')).rstrip('/') or result.get('provider') != previous.get('provider')):
            result['api_key'] = ''
        result.setdefault('api_key', '')
        result['name'] = str(result.get('name', '')).strip()[:80] or str(result.get('model', '')).strip()[:80] or '新模型'
        result['provider'] = result.get('provider', 'custom')
        if result['provider'] in {'deepseek', 'qwen'} and not result['api_key']:
            raise ValueError('此云服务需要 API Key；请在设置窗口填写，不要发送到聊天中')
        return validate_config(result, require_model)


def save_model(data, values):
    with LOCK:
        model = merge_input(data, values)
        result = read(data)
        model['id'] = model.get('id') if re.fullmatch('[a-f0-9]{16}', str(model.get('id', ''))) else secrets.token_hex(8)
        result['models'] = [m for m in result['models'] if m['id'] != model['id']] + [model]
        if values.get('make_default', True) or not result['default_model_id']:
            result['default_model_id'] = model['id']
        path = Path(data) / 'settings.json'
        temporary = path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        return model['id']
