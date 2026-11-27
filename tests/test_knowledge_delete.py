import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from safety_report import server
from safety_report.documents import EvidenceIndex
from safety_report.knowledge import KnowledgeBase


def law(title):
    return dict(category='regulation', title=title, content=title+'的完整条文。',
                source='合成测试法规', version='测试版本', validity_status='current')


class LocalIndex(EvidenceIndex):
    def __init__(self, chunks, path, rebuild=False):
        super().__init__(chunks)
        self.client = None
        self.closed = False

    def close(self):
        self.closed = True


def test_delete_removes_from_warm_index_and_both_retrieval_modes(tmp_path, monkeypatch):
    monkeypatch.setattr('safety_report.knowledge.HybridEvidenceIndex', LocalIndex)
    kb = KnowledgeBase(tmp_path/'kb.json')
    removed = kb.create(law('待删除消防规则'))
    kept = kb.create(law('保留消防规则'))
    for record in (removed, kept):
        kb.set_status(record['id'], 'approved', '测试审核人')
    assert {r['knowledge_id'] for r in kb.search('消防规则')} == {removed['id'], kept['id']}
    index = kb.index
    result = kb.delete(removed['id'], 1)
    assert result['deleted_id'] == removed['id'] and index.closed and kb.index is None
    assert [r['id'] for r in kb.list()] == [kept['id']]
    for purpose in ('report', 'reference'):
        assert {r['knowledge_id'] for r in kb.search('消防规则', purpose=purpose)} == {kept['id']}
    archive = json.loads(kb.path.read_text(encoding='utf-8'))['deleted_records'][0]
    assert archive['id'] == removed['id'] and archive['content'] == removed['content']
    assert archive['deleted_at'] and archive['audit'][-1]['action'] == 'deleted'
    with pytest.raises(ValueError):
        kb.set_status(removed['id'], 'approved', '测试审核人')
    kb.close()


@pytest.mark.parametrize('revision', [None, True, '1', 0, 2])
def test_invalid_or_stale_delete_does_not_write(tmp_path, revision):
    kb = KnowledgeBase(tmp_path/'kb.json'); record = kb.create(law('保留法规'))
    before = kb.path.read_bytes()
    with pytest.raises(ValueError): kb.delete(record['id'], revision)
    assert kb.path.read_bytes() == before


@pytest.mark.parametrize('status', ['draft', 'approved', 'retired'])
def test_can_delete_every_active_record_status(tmp_path, status):
    kb = KnowledgeBase(tmp_path/'kb.json'); record = kb.create(law('测试法规'))
    if status != 'draft': kb.set_status(record['id'], status, '测试审核人')
    kb.delete(record['id'], 1)
    assert not kb.list() and not kb._approved_chunks(purpose='reference')
    before = kb.path.read_bytes()
    with pytest.raises(ValueError, match='已不存在'): kb.delete(record['id'], 1)
    assert kb.path.read_bytes() == before


def test_http_delete_requires_same_origin_and_preserves_other_records(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    monkeypatch.setenv('APP_PASSWORD', '')
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{http.server_port}'

    def request(path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base+path, data=body, headers=headers or {}), timeout=10) as response:
            return json.load(response)

    try:
        removed = request('/api/knowledge', law('错误资料'))['record']
        kept = request('/api/knowledge', law('正确资料'))['record']
        route = '/api/knowledge/'+removed['id']+'/delete'
        with pytest.raises(HTTPError) as error:
            request(route, {'revision': 1}, {'Origin': 'https://untrusted.example'})
        assert error.value.code == 403
        assert len(request('/api/knowledge')['records']) == 2
        assert request(route, {'revision': 1})['deleted_id'] == removed['id']
        assert [r['id'] for r in request('/api/knowledge')['records']] == [kept['id']]
        with pytest.raises(HTTPError):
            request('/api/knowledge/'+removed['id']+'/status', {'status': 'draft'})
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        server.close_knowledge_stores(tmp_path)
