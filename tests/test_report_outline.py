import copy
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report.report_outline import edit_chapter_outline,outline_profile
from safety_report import server


def report():
    return {'confirmed_fields':[],'report_name':'测试报告','mode':'llm','template_sha256':'old','sections':[{'title':'1 依据','subheadings':['1.1 文件','1.2 标准'],'paragraphs':[{'heading':'1.1 文件','text':'已经写好的事实','evidence_ids':['e1']}],'tables':[{'heading':'1.2 标准','caption':'表1 标准清单','headers':['名称'],'rows':[['测试依据']],'evidence_ids':['e1']}],'missing':[],'review':[]}], 'evidence':[{'id':'e1','text':'已经写好的事实','source':'资料','locator':'body[1]'}]}


def test_rename_preserves_content_refs_and_changes_heading_bindings():
    old=report();original=copy.deepcopy(old)
    new,mapping=edit_chapter_outline(old,'1','1 编制依据',[{'original':'1.1 文件','text':'1.1 备案文件'},{'original':'1.2 标准','text':'1.2 适用标准'},{'text':'1.3 合同文件'}])
    assert old==original
    assert new['sections'][0]['paragraphs'][0]==dict(old['sections'][0]['paragraphs'][0],heading='1.1 备案文件')
    assert new['sections'][0]['tables'][0]['heading']=='1.2 适用标准'
    assert new['evidence']==old['evidence']
    assert outline_profile(new)['headings'][0]['subheadings'][-1]=='1.3 合同文件'


def test_rejects_dangling_duplicate_or_renumbered_headings():
    with pytest.raises(ValueError,match='仍有正文'):edit_chapter_outline(report(),'1','1 依据',[])
    with pytest.raises(ValueError,match='编号'):edit_chapter_outline(report(),'1','2 依据',[])
    with pytest.raises(ValueError):edit_chapter_outline(report(),'1','1 依据',[{'original':'1.1 文件','text':'1.1 X'},{'original':'1.2 标准','text':'1.1 Y'}])
    with pytest.raises(ValueError):edit_chapter_outline(report(),'1','1 依据',[{'text':'1.1.1 无父小节'}])


def test_http_outline_persists_into_generation_profile_and_lock_guard(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None):
        with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'目录接口回归'})['id'];route='/api/projects/'+pid;target=tmp_path/pid
        old=report();server.save(target/'report.json',old);server.state_update(target,report_version='v1')
        payload={'base_version':'v1','chapter_id':'1','title':'1 编制依据','subheadings':[{'original':'1.1 文件','text':'1.1 项目备案'},{'original':'1.2 标准','text':'1.2 标准清单'}]}
        result=req(route+'/outline-edit',payload)
        current=req(route+'/report')['report']
        assert current['sections'][0]['paragraphs'][0]['text']=='已经写好的事实'
        profile=req('/api/template?project_id='+pid)
        assert profile['headings'][0]['text']=='1 编制依据'
        assert server.template_compatible_report(target) is not None
        assert req(route)['outline_revision']==1
        with pytest.raises(urllib.error.HTTPError):req(route+'/outline-edit',payload)
        req(route+'/chapter-approval',{'base_version':result['version'],'chapter_id':'1','locked':True})
        payload['base_version']=result['version']
        with pytest.raises(urllib.error.HTTPError):req(route+'/outline-edit',payload)
        assert len(list((target/'versions').glob('*/meta.json')))>=2
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_generation_keeps_edited_headings_and_custom_sections_once():
    from safety_report.pipeline import generate
    edited,_=edit_chapter_outline(report(),'1','1 编制依据',[{'original':'1.1 文件','text':'1.1 备案材料'},{'original':'1.2 标准','text':'1.2 适用标准'}])
    edited['sections'].append({'id':'custom-abc','custom':True,'title':'专项补充','subheadings':[],'paragraphs':[],'tables':[],'missing':[],'review':[]})
    profile={**outline_profile(edited),'sha256':'edited','report_type':'facility_design'}
    result=generate(profile,{'chunks':[{'id':'e1','source':'资料.txt','locator':'paragraph[1]','text':'建设项目依据及备案文件。'}]},[],False,previous=edited)
    assert [s['title'] for s in result['sections']]==['1 编制依据','专项补充']
    assert result['sections'][0]['subheadings']==['1.1 备案材料','1.2 适用标准']


def test_add_delete_chapters_and_delete_populated_subsections_preserves_original():
    from safety_report.report_outline import change_outline
    old=report();original=copy.deepcopy(old)
    expanded,_=change_outline(old,{'operation':'add','title':'2 新增章节'})
    assert expanded['sections'][1]['generation_status']=='not_generated'
    with pytest.raises(ValueError,match='编号已存在'):change_outline(expanded,{'operation':'add','title':'2 重复'})
    with pytest.raises(ValueError,match='确认'):change_outline(expanded,{'operation':'delete','chapter_id':'1'})
    reduced,_=change_outline(expanded,{'operation':'delete','chapter_id':'1','delete_content':True})
    assert [s['title'] for s in reduced['sections']]==['2 新增章节']
    with pytest.raises(ValueError,match='至少'):change_outline(reduced,{'operation':'delete','chapter_id':'2','delete_content':True})
    edited,_=change_outline(old,{'operation':'edit','chapter_id':'1','title':'1 依据','subheadings':[{'original':'1.2 标准','text':'1.2 标准'}],'delete_content':True})
    assert edited['sections'][0]['paragraphs']==[] and len(edited['sections'][0]['tables'])==1
    assert old==original


def test_http_outline_crud_before_generation_and_after_report(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None):
        with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'章节目增删接口'})['id'];route='/api/projects/'+pid;target=tmp_path/pid
        state=req(route);version=state.get('report_version')
        req(route+'/outline-edit',{'base_version':version,'outline_revision':0,'operation':'add','title':'14 项目补充'})
        assert not (target/'report.json').exists()
        profile=req('/api/template?project_id='+pid);assert profile['headings'][-1]['text']=='14 项目补充'
        req(route+'/outline-edit',{'base_version':version,'outline_revision':1,'operation':'edit','chapter_id':'14','title':'14 其他事项','subheadings':[{'text':'14.1 附加资料'},{'text':'14.1.1 详细记录'}]})
        assert req('/api/template?project_id='+pid)['headings'][-1]['text']=='14.1.1 详细记录'
        with pytest.raises(urllib.error.HTTPError):req(route+'/outline-edit',{'base_version':version,'outline_revision':1,'operation':'delete','chapter_id':'14'})
        old=report();server.save(target/'report.json',old);server.state_update(target,report_version='v1')
        added=req(route+'/outline-edit',{'base_version':'v1','operation':'add','title':'2 补充章'})
        deleted=req(route+'/outline-edit',{'base_version':added['version'],'operation':'delete','chapter_id':'1','delete_content':True})
        assert [s['title'] for s in req(route+'/report')['report']['sections']]==['2 补充章']
        assert any(json.loads(p.read_text())['sections'][0]['paragraphs'] for p in (target/'versions').glob('*/report.json'))
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)
