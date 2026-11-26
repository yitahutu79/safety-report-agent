"""Reference discovery must not certify search snippets or overwrite approved knowledge."""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest
from safety_report import public_research as research, server
from safety_report.knowledge import KnowledgeBase

OFFICIAL = 'https://www.mem.gov.cn/gk/test.shtml'


def test_official_sources_and_internal_redirect_boundaries():
    assert research.official_url(OFFICIAL)
    for url in ('http://www.mem.gov.cn/a', 'https://mem.gov.cn.evil.com/a',
                'https://user:pass@www.mem.gov.cn/a', 'https://127.0.0.1/a',
                'https://www.mem.gov.cn:10443/a', 'file:///etc/passwd'):
        assert not research.official_url(url)
    with patch.object(research.socket, 'getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
        with pytest.raises(ValueError, match='内部网络'):
            research.validate_url(OFFICIAL)


def test_recommendations_use_industry_and_region_without_company_facts():
    rows = research.recommendations('山东省烟台市 印刷 应急预案 粉尘')
    assert any('山东' in r['query'] for r in rows)
    assert any('印刷' in r['query'] for r in rows)
    assert any('应急预案' in r['query'] for r in rows)
    assert all(r['conditional'] for r in rows)
    assert all('烟台' not in r['query'] for r in rows)


def test_search_limits_deduplicates_and_keeps_change_as_unverified(tmp_path):
    with pytest.raises(ValueError):research.begin(tmp_path, ['x']*7)
    state = research.begin(tmp_path, ['安全生产法'])
    with pytest.raises(ValueError, match='正在检查'):research.begin(tmp_path, ['其他'])
    rows = [{'href': OFFICIAL, 'title': '条例修订', 'body': '修订公告'},
            {'href': OFFICIAL, 'title': '重复'}, {'href': 'https://example.com/law', 'title': '非官方'}]
    with patch.object(research, 'search', return_value=rows):research.run(tmp_path, state)
    saved=research.latest(tmp_path)
    assert saved['status']=='completed'
    assert len(saved['candidates'])==1
    assert '尚未确认' in saved['candidates'][0]['notice']
    assert '变更线索' in saved['candidates'][0]['notice']


def test_failed_search_does_not_claim_up_to_date(tmp_path):
    state=research.begin(tmp_path,['法律'])
    with patch.object(research,'search',side_effect=RuntimeError('网络不可用')):research.run(tmp_path,state)
    saved=research.latest(tmp_path)
    assert saved['status']=='partial'
    assert '不代表' in saved['message']
    assert saved['errors']


def test_download_and_import_preserve_provenance_approval_and_deduplicate(tmp_path):
    kb=KnowledgeBase(tmp_path/'kb.json')
    existing=kb.create({'category':'regulation','title':'旧条款','content':'旧条文','source':'原文件'})
    kb.set_status(existing['id'],'approved','复核人')
    state=research.begin(tmp_path,['法规'])
    with patch.object(research,'search',return_value=[{'href':OFFICIAL,'title':'官方法规'}]):research.run(tmp_path,state)
    ident=research.latest(tmp_path)['candidates'][0]['id']
    text=('第一条 这里是官方条文，用于验证正文导入、原始来源留存和人工审核边界。\n'*3).encode()
    with patch.object(research,'fetch',return_value=(text,'text/plain','utf-8',OFFICIAL)) as fetch:
        info=research.download(tmp_path,ident)
        result=research.import_candidate(tmp_path,ident,kb)
        again=research.import_candidate(tmp_path,ident,kb)
    assert fetch.call_count==1
    assert again['already_imported']
    assert result['source_url']==OFFICIAL
    assert result['sha256']==info['sha256']
    records=kb.list()
    assert records[0]['status']=='approved'
    assert all(r['status']=='draft' and r['validity_status']=='unknown' and r['source_url']==OFFICIAL for r in records[1:])
    with pytest.raises(ValueError):research.candidate(tmp_path,'bad')


def test_research_http_round_trip(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def request(path,data=None):
        raw=json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base+path,data=raw),timeout=5) as res:return json.load(res)
    try:
        assert request('/api/knowledge/recommendations')['topics']
        with patch.object(server.POOL,'submit') as submit:
            started=request('/api/knowledge/research',{'queries':['中华人民共和国安全生产法']})
            assert started['status']=='running';submit.assert_called_once()
        assert request('/api/knowledge/research')['id']==started['id']
    finally:
        http.shutdown();http.server_close();thread.join();server.close_knowledge_stores(tmp_path)


def test_local_recommendations_do_not_use_supplier_or_template_region():
    assert not any('地方规定' in r['title'] for r in research.recommendations('江苏设计单位；山东建设项目', region_context=''))
    rows = research.recommendations('江苏设计单位', region_context='山东省烟台市')
    assert any(r['title']=='山东地方规定' for r in rows)


def test_gzip_official_pages_decode_with_a_bounded_decompressed_size(monkeypatch):
    import gzip
    raw='第一条 官方正文'.encode()
    assert research.decompress_response(gzip.compress(raw))==raw
    monkeypatch.setattr(research,'MAX_BYTES',50)
    with pytest.raises(ValueError,match='解压后'):
        research.decompress_response(gzip.compress(b'x'*1000))
