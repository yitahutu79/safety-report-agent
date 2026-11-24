import copy
import threading
import pytest
from safety_report import pipeline,server
from safety_report.pipeline import merge_subsection_revision


def source_report():
    return {'sections':[{'title':'1 设计依据','subheadings':['1.1 文件','1.2 标准'],'paragraphs':[
        {'heading':'1.1 文件','text':'资料摘录：此为未选中小节的旧内容，必须保持。','evidence_ids':['e1'],'human_edited':True},
        {'heading':'1.2 标准','text':'待替换的旧内容','evidence_ids':['e1']}],
        'tables':[{'heading':'1.1 文件','caption':'已有表','headers':['文件'],'rows':[['测试文件']],'evidence_ids':['e1']}],
        'missing':[],'review':[]}], 'evidence':[{'id':'e1','source':'测试文件','locator':'paragraph[1]','text':'已确认编制依据。'}]}


class Index:
    client=None;semantic_error=None
    def __init__(self,chunks,path=None):self.chunks=chunks
    def search(self,query,limit=4):return self.chunks[:limit]
    def close(self):pass


def test_generation_rewrites_selected_heading_only_and_preserves_other_content(monkeypatch):
    old=source_report();snapshot=copy.deepcopy(old);calls=[]
    profile={'sha256':'t','custom_template':True,'headings':[{'text':'1 设计依据','level':1},{'text':'1.1 文件','level':2},{'text':'1.2 标准','level':2}]}
    def graph(system,payload,model,**kwargs):
        calls.append(payload['required_subsections'])
        result={'paragraphs':[{'heading':'1.2 标准','text':'依据项目资料确定本节编制范围。','evidence_ids':['e1']}],'tables':[],'missing':[],'review':[]}
        assert not kwargs['validate'](result)
        return result
    monkeypatch.setattr(pipeline,'HybridEvidenceIndex',Index)
    monkeypatch.setattr('safety_report.agent_graph.run_chapter_graph',graph)
    result=pipeline.generate(profile,{'chunks':old['evidence']},[],True,model={'name':'测试'},previous=old,chapter_ids=['1'],subsections={'1':['1.2 标准']})
    assert calls==[['1.2 标准']]
    chapter=result['sections'][0]
    assert chapter['paragraphs'][0]==old['sections'][0]['paragraphs'][0]
    assert chapter['tables']==old['sections'][0]['tables']
    assert chapter['paragraphs'][1]['text']=='依据项目资料确定本节编制范围。'
    assert chapter['subheadings']==old['sections'][0]['subheadings']
    assert result['updated_subsections']=={'1':['1.2 标准']} and not result['quality_checked']
    assert old==snapshot


def test_failed_partial_generation_does_not_change_original(monkeypatch):
    old=source_report();snapshot=copy.deepcopy(old)
    profile={'sha256':'t','custom_template':True,'headings':[{'text':'1 设计依据','level':1,'subheadings':['1.1 文件','1.2 标准']}]}
    monkeypatch.setattr(pipeline,'HybridEvidenceIndex',Index)
    def fail(*args,**kwargs):raise ValueError('模拟节点失败')
    monkeypatch.setattr('safety_report.agent_graph.run_chapter_graph',fail)
    with pytest.raises(ValueError,match='未保存新版本'):pipeline.generate(profile,{'chunks':old['evidence']},[],True,model={},previous=old,chapter_ids=['1'],subsections={'1':['1.2 标准']})
    assert old==snapshot


def test_subsection_scope_rejects_invalid_and_cross_chapter_selections():
    old=source_report()
    for scope in [{},{'1':[]},{'1':['1.3 不存在']},{'1':['1.2 标准','1.2 标准']},{'2':['1.2 标准']}]:
        with pytest.raises(ValueError):server.validate_subsection_scope({'subsections':scope},old,['1'])
    assert server.validate_subsection_scope({'subsections':{'1':['1.2 标准']}},old,['1'])=={'1':['1.2 标准']}


def test_preflight_checks_only_the_selected_subsection(tmp_path,monkeypatch):
    server.save(tmp_path/'state.json',{'report_type':'facility_design','files':[]})
    monkeypatch.setattr(server,'template_compatible_report',lambda _:source_report())
    calls=[]
    def plan(chapter,section,evidence,model,**kwargs):calls.append(section['subheadings']);return {'requests':[],'can_draft_now':True}
    monkeypatch.setattr(server,'plan_missing_materials',plan)
    result=server.chapter_materials_plan(tmp_path,'1',{},threading.Event(),subsection_titles=['1.2 标准'])
    assert calls==[['1.2 标准']] and result['checked_subsections']==1


def test_partial_merge_does_not_clear_chapter_failure_flags():
    old=source_report()['sections'][0];old['needs_rewrite']=True;old['generation_status']='failed'
    new={'paragraphs':[{'heading':'1.2 标准','text':'修改'}],'tables':[],'missing':[],'review':[]}
    merged=merge_subsection_revision(old,new,['1.2 标准'],old['subheadings'])
    assert merged['needs_rewrite'] and merged['generation_status']=='failed'


def test_http_scoped_generation_dispatch_and_stale_version_guard(tmp_path,monkeypatch):
    import json
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(server,'DATA',tmp_path)
    monkeypatch.setattr(server.settings,'resolve',lambda *args:{'model':'mock'})
    monkeypatch.setattr(server,'validate_ready',lambda fields:None)
    calls=[]
    class Pool:
        def submit(self,*args):calls.append(args)
    monkeypatch.setattr(server,'POOL',Pool())
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    def req(path,data):
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}'+path,data=json.dumps(data).encode()),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'小节范围接口回归'})['id'];target=tmp_path/pid;route='/api/projects/'+pid
        old=source_report();old['template_sha256']=server.project_profile(target)['sha256'];server.save(target/'report.json',old)
        server.save(target/'analysis.json',{'chunks':old['evidence']})
        server.state_update(target,report_version='v1',files=[{'id':'f1','name':'测试.txt','stored':'f1.txt','sha256':'h','size':1,'role':'source','active':True}],analysis_dirty=False)
        payload={'chapter_ids':['1'],'subsections':{'1':['1.2 标准']},'model_id':'mock','use_llm':True,'base_version':'v1'}
        req(route+'/preflight',payload)
        assert calls[-1][0] is server.preflight_job and calls[-1][-1]==payload['subsections']
        server.state_update(target,busy=False)
        req(route+'/generate',payload)
        assert calls[-1][0] is server.job and calls[-1][-2]==payload['subsections'] and calls[-1][-1] is True
        server.state_update(target,busy=False)
        with pytest.raises(urllib.error.HTTPError):req(route+'/generate',{**payload,'base_version':'old'})
        workflow={'chapters':{'1':{'locked':True}}};server.save(target/'chapter-workflow.json',workflow)
        with pytest.raises(urllib.error.HTTPError):req(route+'/generate',payload)
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_partial_merge_preserves_relative_order_of_untouched_blocks():
    old={'title':'1 章','paragraphs':[{'heading':'1.3 C','text':'C'},{'heading':'1.1 A','text':'A'},{'heading':'1.2 B','text':'B'},{'heading':'1.1 A','text':'A2'}],'tables':[],'missing':[],'review':[]}
    new={'paragraphs':[{'heading':'1.2 B','text':'新B'}],'tables':[]}
    merged=merge_subsection_revision(old,new,['1.2 B'],['1.1 A','1.2 B','1.3 C'])
    assert [p['text'] for p in merged['paragraphs']]==['C','A','新B','A2']


def test_parent_selection_expands_body_subsections_and_can_be_disabled():
    old={'sections':[{'title':'1 依据','subheadings':['1.2 法规','1.2.1 国家法律','1.2.2 地方法规','1.20 其他']}]}
    data={'subsections':{'1':['1.2 法规']}}
    assert server.validate_subsection_scope(data,old,['1'])=={'1':['1.2 法规','1.2.1 国家法律','1.2.2 地方法规']}
    assert server.validate_subsection_scope({**data,'include_descendants':False},old,['1'])==data['subsections']
    assert data['subsections']=={'1':['1.2 法规']}
