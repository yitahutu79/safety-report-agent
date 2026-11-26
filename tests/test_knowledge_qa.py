import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from safety_report import knowledge_qa, server


def test_no_evidence_never_calls_model():
    def forbidden(*args, **kwargs):
        pytest.fail('无证据时不应调用模型')
    result = knowledge_qa.answer_question('测试问题', [], {}, complete=forbidden)
    assert not result['paragraphs'] and result['missing']


def test_answer_citations_are_checked():
    evidence = [{'id':'known','source':'示例.txt','locator':'第1段','text':'该设备为储罐。'}]
    def good(system, payload, model, **kwargs):
        assert payload['evidence'][0]['id'] == 'known'
        return {'paragraphs':[{'text':'资料提到了储罐。','evidence_ids':['known']}], 'missing':[]}
    result = knowledge_qa.answer_question('有哪些设备？', evidence, {}, complete=good)
    assert result['sources'][0]['id'] == 'known'
    def bad(*args, **kwargs):
        return {'paragraphs':[{'text':'已符合要求。','evidence_ids':['invented']}], 'missing':[]}
    with pytest.raises(ValueError, match='不存在的证据'):
        knowledge_qa.answer_question('是否符合？', evidence, {}, complete=bad)


def test_http_question_uses_only_selected_project_and_fake_model(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    monkeypatch.setattr(server.settings, 'resolve', lambda *_: {'model':'fake'})
    monkeypatch.setattr(server, 'search_project', lambda chunks, path, query, limit: (chunks[:limit], 'keyword_fallback', ''))
    received=[]
    def fake(system, payload, model, **kwargs):
        received.extend(x['id'] for x in payload['evidence'])
        return {'paragraphs':[{'text':'示例资料提到了储罐。','evidence_ids':['private-a']}], 'missing':[]}
    monkeypatch.setattr(server.provider, 'complete_json', fake)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def request(path, data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as response:
            return json.load(response)
    try:
        a=request('/api/projects',{'name':'合成项目甲'}); b=request('/api/projects',{'name':'合成项目乙'})
        for p,ident in ((a,'private-a'),(b,'private-b')):
            (tmp_path/p['id']/'analysis.json').write_text(json.dumps({'chunks':[{'id':ident,'source':'示例.txt','locator':'第1段','text':'示例储罐'}]}))
        route='/api/projects/'+a['id']
        request(route+'/knowledge-qa',{'scope':'project','question':'有哪些设备？','model_id':'fake'})
        for _ in range(100):
            state=request(route)
            if not state['busy']: break
            time.sleep(.02)
        assert not state['busy'] and not state.get('error')
        assert received == ['private-a']
        assert state['qa_result']['paragraphs'][0]['evidence_ids'] == ['private-a']
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_unknown_validity_can_be_explained_with_explicit_warning():
    source={'id':'a','source':'标准第一条','locator':'第一条','text':'第一条说明制定目的。','corpus':'approved_knowledge','validity_status':'unknown'}
    def model(system,payload,config,**kwargs):
        assert '不表示条文不存在' in system
        assert '第一条说明制定目的' in payload['evidence'][0]['text']
        return {'paragraphs':[{'text':'第一条说明制定目的。','evidence_ids':['a']}],'missing':[]}
    result=knowledge_qa.answer_question('第一条说明什么？',[source],{},complete=model)
    assert result['paragraphs'] and '未核验' in result['validity_warnings'][0]
