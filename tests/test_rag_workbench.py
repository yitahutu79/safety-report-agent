import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from safety_report import server
from safety_report.rag_workbench import retrieval_metrics, search_project


def test_metrics_count_all_labels_even_those_not_retrieved():
    result = retrieval_metrics([{'id':'a'}, {'id':'x'}], ['a','b'], 5)
    assert result['precision_at_k'] == 0.2
    assert result['precision_returned'] == 0.5
    assert result['recall_at_k'] == 0.5
    assert result['unretrieved_relevant_ids'] == ['b']
    with pytest.raises(ValueError): retrieval_metrics([], [], 5)


def test_real_keyword_fallback_retrieves_relevant_evidence_without_a_model():
    chunks = [{'id': 'a', 'text': '消防系统设计流量为二十升每秒。', 'source': '示例.txt', 'locator': '第1段'},
              {'id': 'b', 'text': '设备清单描述冷却泵。', 'source': '示例.txt', 'locator': '第2段'}]
    results, mode, warning = search_project(chunks, None, '消防系统流量', 2)
    assert mode == 'keyword_fallback' and results[0]['id'] == 'a'
    assert not warning


def test_public_import_and_project_retrieval_stay_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    # Avoid downloading an embedding model in an offline unit test.
    def fake_project(chunks, path, query, limit):
        return [c for c in chunks if query in c['text']][:limit], 'keyword_fallback', ''
    monkeypatch.setattr(server, 'search_project', fake_project)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def request(path, data=None, raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=10) as response:
            return json.load(response)
    try:
        a=request('/api/projects',{'name':'甲项目'}); b=request('/api/projects',{'name':'乙项目'})
        for project, chunk in [(a,{'id':'private-a','text':'甲资料关键字','source':'甲.txt','locator':'第1段'}),
                               (b,{'id':'private-b','text':'乙资料关键字','source':'乙.txt','locator':'第1段'})]:
            (tmp_path/project['id']/'analysis.json').write_text(json.dumps({'chunks':[chunk]},ensure_ascii=False))
        route='/api/projects/'+a['id']+'/rag-test'
        result=request(route,{'scope':'project','query':'资料','limit':5})
        assert [row['id'] for row in result['results']]==['private-a']
        result=request(route,{'scope':'project','query':'资料','limit':5,'operation':'evaluate','relevant_ids':['private-a']})
        assert result['metrics']['precision_at_k']==0.2 and result['metrics']['recall_at_k']==1
        url='/api/knowledge/import?'+urllib.parse.urlencode({'filename':'公开.txt','category':'hazard'})
        imported=request(url,raw='公开危险因素资料。'.encode())
        assert imported['count']==1
        records=request('/api/knowledge')['records']
        assert records[0]['status']=='draft' and records[0]['source'].startswith('公开.txt')
        public=request(route,{'scope':'public','query':'公开','limit':5})
        assert public['results']==[]  # Unapproved material never enters public RAG.
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)
