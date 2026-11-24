import copy
import pytest
from safety_report.chapter_workflow import (set_chapter_approval,workflow_view,assert_unlocked,ordered_report,assembly_checks)


def sample():
    section={'title':'1 依据','subheadings':[],'paragraphs':[{'text':'文件依据','evidence_ids':['e1']}],'tables':[],'missing':[],'review':[]}
    report={'template_sha256':'t1','sections':[section,dict(copy.deepcopy(section),title='2 概况')],'evidence':[{'id':'e1'}]}
    state={'fields':[{'key':'capacity','value':'100','confirmed':True}],'files':[],'data_revision':0}
    profile={'sha256':'t1','headings':[{'text':'1 依据','level':1},{'text':'2 概况','level':1}]}
    return report,state,profile


def test_lock_requires_completed_section_and_prevents_changes():
    report,state,_=sample();w={}
    set_chapter_approval(report,state,w,'1',True)
    assert workflow_view(report,state,w)['1']['status']=='已确认锁定'
    with pytest.raises(ValueError,match='已锁定'):assert_unlocked(w,['1'])
    assert_unlocked(w,['2'])
    set_chapter_approval(report,state,w,'1',False);assert_unlocked(w,['1'])
    report['sections'][0]['generation_status']='not_generated'
    with pytest.raises(ValueError):set_chapter_approval(report,state,w,'1',True)


def test_changes_warn_without_silently_unlocking_or_rewriting():
    report,state,_=sample();w={};set_chapter_approval(report,state,w,'1',True)
    old=copy.deepcopy(report)
    state['fields'][0]['value']='200'
    v=workflow_view(report,state,w)['1']
    assert v['locked'] and v['status']=='需复核' and '基础数据' in v['warnings'][0]
    assert report==old
    set_chapter_approval(report,state,w,'1',True)
    assert not workflow_view(report,state,w)['1']['warnings']
    report['sections'][0]['paragraphs'][0]['text']='内容变化'
    assert '章节内容' in workflow_view(report,state,w)['1']['warnings'][0]


def test_assembly_uses_saved_order_and_blocks_unfinished_or_stale():
    report,state,profile=sample();w={'order':['2','1']}
    checks=assembly_checks(report,state,w,profile,{'checks':[]})
    assert not checks['can_assemble']
    for i in ['1','2']:set_chapter_approval(report,state,w,i,True)
    assert assembly_checks(report,state,w,profile,{'checks':[]})['can_assemble']
    ordered=ordered_report(report,w)
    assert [s['title'] for s in ordered['sections']]==['2 概况','1 依据']
    assert report['sections'][0]['title']=='1 依据'
    report['sections'][1]['missing']=['缺少储量']
    assert not assembly_checks(report,state,w,profile,{'checks':[]})['can_assemble']
    report,state,profile=sample();state['analysis_dirty']=True
    assert not assembly_checks(report,state,w,profile,{'checks':[]})['can_assemble']


def test_http_locks_order_and_assembly_without_model_calls(tmp_path,monkeypatch):
    import threading,json,urllib.request,urllib.error
    from http.server import ThreadingHTTPServer
    from safety_report import server,provider
    monkeypatch.setattr(server,'DATA',tmp_path)
    report,state,profile=sample();report.update(confirmed_fields=[],report_name='测试报告',structure_confirmed=True,mode='llm')
    report['evidence']=[{'id':'e1','source':'资料.txt','locator':'paragraph[1]','text':'文件依据'}]
    monkeypatch.setattr(server,'project_profile',lambda *args:profile)
    monkeypatch.setattr(provider,'complete_json',lambda *args,**kw:pytest.fail('组稿不应调用模型'))
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None):
        with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None),timeout=5) as response:return json.load(response)
    try:
        pid=req('/api/projects',{'name':'组稿接口回归'})['id'];route='/api/projects/'+pid;target=tmp_path/pid
        server.save(target/'report.json',report);server.state_update(target,report_version='v1',files=[{'id':'f1','name':'资料.txt','stored':'f1.txt','sha256':'hash','size':1,'active':True,'role':'source'}])
        assert not req(route+'/assembly-check',{'base_version':'v1'})['can_assemble']
        for ident in ['1','2']:req(route+'/chapter-approval',{'base_version':'v1','chapter_id':ident,'locked':True})
        with pytest.raises(urllib.error.HTTPError):req(route+'/edit',{'base_version':'v1','sections':[{'title':'1 依据','paragraphs':[]}]})
        with pytest.raises(urllib.error.HTTPError) as error:req(route+'/generate',{'chapter_ids':['1'],'use_llm':False})
        assert '锁定' in json.load(error.value)['error']
        with pytest.raises(urllib.error.HTTPError):req(route+'/chapter-order',{'base_version':'v1','order':['2','2']})
        req(route+'/chapter-order',{'base_version':'v1','order':['2','1']})
        assert req(route+'/report')['report']['sections'][0]['title']=='2 概况'
        checks=req(route+'/assembly-check',{'base_version':'v1'})
        assert checks['can_assemble'] and checks['warnings']
        with pytest.raises(urllib.error.HTTPError):req(route+'/assemble',{'base_version':'v1'})
        assembled=req(route+'/assemble',{'base_version':'v1','acknowledge_warnings':True})
        assert assembled['version']!='v1' and (target/'report.docx').exists()
        assert server.load(target/'report.json')['sections'][0]['title']=='2 概况'
        assert server.load(target/'report.json')['assembly_checks']['can_assemble']
        assert req(route+'/report')['report']['chapter_workflow']['1']['locked']
        server.state_update(target,data_revision=1)
        checks=req(route+'/assembly-check',{'base_version':assembled['version']})
        assert not checks['can_assemble'] and any('更新' in x for x in checks['blockers'])
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)
