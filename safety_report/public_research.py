"""Bounded official-source discovery. DDGS search follows GPT Researcher's retriever;
trafilatura extracts webpage bodies. Findings are candidates, never legal validity decisions.
"""
from datetime import datetime, timezone, timedelta
import gzip
import io
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import threading
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid

LOCK = threading.RLock()
MAX_BYTES = 8_000_000
TOPICS = [
    ('安全生产基本法律', '中华人民共和国安全生产法', '报告通用法律依据；需核对适用条款'),
    ('建设项目安全设施', '建设项目安全设施 三同时 监督管理办法', '安全设施设计及建设程序'),
    ('重大事故隐患', '工贸企业重大事故隐患判定标准', '工贸企业隐患辨识参考；先确认行业'),
    ('建筑与消防', '建筑防火通用规范 消防设施通用规范', '建筑及消防设计依据；按建筑用途核对'),
]
SPECIAL = {
    '印刷': [('印刷与溶剂', '印刷企业 安全生产 危险化学品 静电 标准', '涉及油墨、溶剂时核对火灾、爆炸及静电要求')],
    '化工': [('危险化学品', '危险化学品安全管理条例 重大危险源辨识', '有危化品时核对管理要求及辨识标准')],
    '应急': [('应急预案', '生产安全事故应急预案管理办法 编制导则', '应急预案编制、备案及演练要求')],
    '有限空间': [('有限空间', '工贸企业有限空间作业安全规定', '存在有限空间作业时核对')],
    '粉尘': [('粉尘防爆', '工贸企业粉尘防爆安全规定', '存在可燃性粉尘时核对')],
}


def recommendations(context='', region_context=None):
    rows = [{'title': title, 'query': query, 'reason': reason, 'conditional': True}
            for title, query, reason in TOPICS]
    for keyword, topics in SPECIAL.items():
        if keyword in context:
            rows.extend({'title': a, 'query': b, 'reason': c, 'conditional': True} for a, b, c in topics)
    match = re.search(r'(山东|江苏|浙江|广东|河南|河北|四川|湖北|湖南|安徽|福建|上海|北京|天津|重庆|山西|陕西|辽宁|吉林|黑龙江|江西|云南|贵州|海南|甘肃|青海|内蒙古|广西|宁夏|新疆|西藏)', context if region_context is None else region_context)
    if match:
        region = match[0]
        rows.append({'title': region+'地方规定', 'query': region+' 安全生产条例 建设项目 安全设施',
                     'reason': '根据资料中的地区线索推荐；请确认实际建设地点', 'conditional': True})
    return rows


def official_url(url):
    try:
        p = urlsplit(url)
        host = (p.hostname or '').lower()
        return p.scheme == 'https' and not p.username and not p.password and p.port in (None, 443) and host.endswith('.gov.cn')
    except ValueError:
        return False


def validate_url(url):
    if not official_url(url):
        raise ValueError('仅支持 HTTPS 官方政府网站来源')
    addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('来源地址不可访问内部网络')


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    validate_url(url)
    req = Request(url, headers={'User-Agent': 'SafetyReport/0.9 public-reference-check'})
    with build_opener(OfficialRedirect()).open(req, timeout=15) as response:
        data = response.read(MAX_BYTES + 1)
        mime = response.headers.get_content_type()
        encoding = response.headers.get_content_charset() or 'utf-8'
        final = response.url
    if len(data) > MAX_BYTES:
        raise ValueError('资料超过 8 MB，请从官方页面自行下载后上传')
    data = decompress_response(data)
    return data, mime, encoding, final



def decompress_response(data):
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:
        raise ValueError('解压后资料超过 8 MB，请从官方页面自行下载')
    return data


def search(query):
    # Same maintained search dependency as GPT Researcher's Duckduckgo retriever.
    from ddgs import DDGS
    return list(DDGS(timeout=10).text(query+' site:gov.cn', max_results=6))


def root(data):
    path = Path(data) / 'public-research'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(data, state):
    path = root(data) / 'latest.json'
    with LOCK:
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)


def latest(data):
    with LOCK:
        path = root(data) / 'latest.json'
        state = json.loads(path.read_text()) if path.exists() else {'status': 'idle', 'candidates': []}
        if state.get('status') == 'running' and datetime.now(timezone.utc)-datetime.fromisoformat(state['checked_at']) > timedelta(minutes=8):
            state.update(status='interrupted', message='上次检查已中断或超时，可以重新搜索。')
            _save(data, state)
        return state


def begin(data, queries, references=None):
    queries = [str(q).strip() for q in queries if str(q).strip()]
    if not queries or len(queries) > 6 or any(len(q) > 180 for q in queries):
        raise ValueError('每次请选择 1—6 个主题，每个主题不超过 180 字')
    with LOCK:
        if latest(data).get('status') == 'running':
            raise ValueError('正在检查，请等待当前任务完成')
        state = {'id': uuid.uuid4().hex, 'status': 'running', 'queries': list(dict.fromkeys(queries)),
                 'checked_at': datetime.now(timezone.utc).isoformat(), 'candidates': [], 'errors': [],
                 'references': references or [],
                 'message': '正在搜索官方发布；只发送所选公共检索词，不发送项目文件'}
        _save(data, state)
    return state


def run(data, state):
    try:
        seen = set()
        for query in state['queries']:
            try:
                results = search(query)
                for row in results:
                    url = row.get('href') or row.get('url') or row.get('link') or ''
                    if not official_url(url) or url in seen:
                        continue
                    seen.add(url)
                    summary = str(row.get('body') or row.get('snippet') or '')[:700]
                    title = str(row.get('title') or query)[:300]
                    registered = next((r for r in state.get('references', []) if r.get('source_url') == url), None)
                    notice = '已登记的来源页面；请核对正文是否更新' if registered else '库内未登记此来源；相关发布候选，尚未确认是否为新版本'
                    if re.search(r'废止|替代|修订|修改|失效', title+' '+summary):
                        notice += '。检索摘要含变更线索，请打开官方正文核对'
                    if re.search(r'解读|新闻|答记者问', title):
                        notice += '。此项属于解读或新闻线索，不能替代法规原文'
                    state['candidates'].append({'id': uuid.uuid4().hex, 'query': query, 'url': url,
                        'title': title, 'summary': summary, 'notice': notice})
            except Exception as exc:
                state['errors'].append({'query': query, 'message': str(exc)[:240]})
            state['message'] = '已找到 '+str(len(state['candidates']))+' 项候选，正在继续检查'
            _save(data, state)
        state['status'] = 'partial' if state['errors'] else 'completed'
        state['message'] = ('已找到 '+str(len(state['candidates']))+' 项官方资料候选。请核对版本及适用条件。'
            if state['candidates'] else '未找到可核对的官方候选；不代表库内资料已经是最新版本。')
    except Exception as exc:
        state.update(status='failed', message='检查失败：'+str(exc)[:240])
    finally:
        _save(data, state)


def candidate(data, ident):
    item = next((r for r in latest(data).get('candidates', []) if r['id'] == ident), None)
    if item is None:
        raise ValueError('候选已过期，请重新检查')
    return item


def download(data, ident):
    item = candidate(data, ident)
    # Stable cache by URL; no refetch when downloading then importing the same candidate.
    key = hashlib.sha256(item['url'].encode()).hexdigest()
    meta = root(data) / (key+'.json')
    with LOCK:
        if meta.exists():
            info = json.loads(meta.read_text())
            if (root(data) / info['file']).exists():
                return info
    raw, mime, encoding, final = fetch(item['url'])
    if raw.startswith(b'%PDF-'):
        suffix, content = '.pdf', raw
    elif raw.startswith(b'PK') and urlsplit(final).path.lower().endswith('.docx'):
        suffix, content = '.docx', raw
    elif mime in ('text/html', 'application/xhtml+xml', 'text/plain'):
        import trafilatura
        html = raw.decode(encoding, errors='replace')
        text = trafilatura.extract(raw, include_tables=True, include_links=True, favor_recall=True) if mime != 'text/plain' else html
        if not text or len(text.strip()) < 40:
            raise ValueError('官方页面未取得正文，可能需要登录或人工下载，请打开原网页')
        suffix, content = '.txt', text.encode('utf-8')
    else:
        raise ValueError('当前只支持 PDF、DOCX 和公开网页正文，请从官方页面下载其他格式')
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', item['title'])[:90]+suffix
    info = {'file': key+suffix, 'name': name, 'source_url': final, 'candidate_url': item['url'],
            'sha256': hashlib.sha256(content).hexdigest(), 'downloaded_at': datetime.now(timezone.utc).isoformat(),
            'title': item['title'], 'mime': 'application/pdf' if suffix == '.pdf' else 'application/octet-stream'}
    with LOCK:
        (root(data) / info['file']).write_bytes(content)
        meta.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
    return info


def import_candidate(data, ident, kb):
    info = download(data, ident)
    receipt = root(data) / (info['sha256']+'.import.json')
    with LOCK:
        if receipt.exists():
            saved = json.loads(receipt.read_text())
            active = {r['id'] for r in kb.list()}
            if saved.get('record_ids') and set(saved['record_ids']) <= active:
                return {**saved, 'already_imported': True}
        from .documents import parse_file
        parsed = parse_file(root(data) / info['file'])
        chunks = parsed['chunks']
        if not chunks or len(chunks) > 100 or any(len(c['text']) > 30000 for c in chunks):
            raise ValueError('正文为空或过长，请下载后分批导入；扫描件需先 OCR')
        from .import_identity import joined_blocks
        imported = kb.import_chunks([{'category': 'regulation', 'title': (info['title'][:150]+' · '+c['locator'])[:200],
            'content': c['text'], 'source': (info['title'][:200]+' · '+c['locator'])[:300],
            'source_url': info['source_url'], 'validity_status': 'unknown'} for c in chunks], info['sha256'], joined_blocks(parsed))
        result = {**imported, 'warnings': parsed['warnings'],
                  'sha256': info['sha256'], 'source_url': info['source_url'], 'downloaded_at': info['downloaded_at']}
        receipt.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        return result
