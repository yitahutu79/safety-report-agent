import copy,json,threading,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server,versions
from safety_report.subsection_locks import set_lock,assert_scope,assert_unchanged


def report():
    return {'confirmed_fields':[],'sections':[{'id':'1','title':'1 依据','subheadings':['1.1 文件','1.2 标准'],'paragraphs':[{'heading':'1.1 文件','text':'原始备案依据。','evidence_ids':[]},{'heading':'1.2 标准','text':'原始标准清单。','evidence_ids':[]}],'tables':[],'missing':[],'review':[]}],'evidence':[]}


@pytest.fixture
def session(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    def req(path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}'+path,data=body),timeout=5) as r:return json.load(r)
    pid=req('/api/projects',{'name':'编辑暂存隔离回归'})['id'];target=tmp_path/pid;route='/api/projects/'+pid
    old=report();old['template_sha256']=server.project_profile(target)['sha256']
    meta=versions.commit(target,old,lambda r,p:server.write_docx(r,{},p),kind='edit');server.state_update(target,report_version=meta['id'],analysis_dirty=False,fields=[])
    yield target,route,req,meta['id']
    http.shutdown();http.server_close();thread.join(timeout=5)


def edit_payload(base,revision=0,first='本轮文件修改。',second='原始标准清单。'):
    paragraphs=[{'heading':'1.1 文件','text':first,'original_index':0},{'heading':'1.2 标准','text':second,'original_index':1}]
    return {'base_version':base,'working_revision':revision,'defer_version':True,'sections':[{'title':'1 依据','paragraphs':paragraphs,'tables':[]}]}


def test_multiple_subsection_edits_create_one_download_only_on_explicit_save(session):
    target,route,req,base=session;old_doc=(target/'report.docx').read_bytes()
    req(route+'/edit',edit_payload(base))
    state=req(route);assert state['has_working_report'] and state['working_revision']==1 and state['report_version']==base
    assert len(versions.history(target))==1 and (target/'report.docx').read_bytes()==old_doc
    current=req(route+'/report')['report'];assert current['sections'][0]['paragraphs'][0]['text']=='本轮文件修改。'
    req(route+'/edit',edit_payload(base,1,second='本轮标准修改。'))
    assert len(versions.history(target))==1 and req(route)['working_revision']==2
    with pytest.raises(urllib.error.HTTPError) as e:req(route+'/download/report.docx')
    assert e.value.code==409
    assert versions.load_report(target,base)['sections'][0]['paragraphs'][0]['text']=='原始备案依据。'
    saved=req(route+'/save-working',{'base_version':base,'working_revision':2})
    assert saved['version']!=base and len(versions.history(target))==2
    assert not req(route)['has_working_report'] and (target/'report.docx').read_bytes()!=old_doc
    texts=[p['text'] for p in versions.load_report(target)['sections'][0]['paragraphs']]
    assert texts==['本轮文件修改。','本轮标准修改。'] and not (target/'working-report.json').exists()


def test_working_copy_is_durable_and_stale_client_cannot_overwrite(session):
    target,route,req,base=session
    req(route+'/edit',edit_payload(base))
    assert versions.load_working(target)['revision']==1
    # A fresh request/reader recovers the same content without an in-memory session.
    assert versions.load_report(target)['sections'][0]['paragraphs'][0]['text']=='本轮文件修改。'
    with pytest.raises(urllib.error.HTTPError):req(route+'/edit',edit_payload(base,0,first='旧页面覆盖。'))
    with pytest.raises(urllib.error.HTTPError):req(route+'/save-working',{'base_version':'stale','working_revision':1})
    assert versions.working_revision(target)==1 and len(versions.history(target))==1


def test_failed_export_preserves_working_copy(session,monkeypatch):
    target,route,req,base=session;req(route+'/edit',edit_payload(base))
    def fail(*args):raise ValueError('模拟导出失败')
    monkeypatch.setattr(server,'export_report',fail)
    with pytest.raises(urllib.error.HTTPError):req(route+'/save-working',{'base_version':base,'working_revision':1})
    assert versions.working_revision(target)==1 and len(versions.history(target))==1
    assert req(route)['report_version']==base


def test_subsection_lock_does_not_publish_and_protects_only_selected_content(session):
    target,route,req,base=session;req(route+'/edit',edit_payload(base))
    req(route+'/subsection-approval',{'base_version':base,'working_revision':1,'chapter_id':'1','heading':'1.1 文件','locked':True})
    assert len(versions.history(target))==1 and versions.working_revision(target)==1
    assert req(route+'/report')['report']['subsection_locks']['1']['1.1 文件']['locked']
    with pytest.raises(urllib.error.HTTPError):req(route+'/edit',edit_payload(base,1,first='改动已锁定段落。'))
    req(route+'/edit',edit_payload(base,1,second='另一小节可继续编辑。'))
    assert versions.working_revision(target)==2 and len(versions.history(target))==1
    req(route+'/subsection-approval',{'base_version':base,'working_revision':2,'chapter_id':'1','heading':'1.1 文件','locked':False})
    req(route+'/edit',edit_payload(base,2,first='解锁后可修改。'))
    assert versions.working_revision(target)==3


def test_subsection_lock_blocks_whole_chapter_scope_but_allows_other_subsection():
    old=report();workflow={};set_lock(old,workflow,'1','1.1 文件',True)
    with pytest.raises(ValueError):assert_scope(workflow,['1'],None)
    with pytest.raises(ValueError):assert_scope(workflow,['1'],{'1':['1.1 文件']})
    assert_scope(workflow,['1'],{'1':['1.2 标准']})
    updated=copy.deepcopy(old);updated['sections'][0]['paragraphs'][1]['text']='其他小节修改';assert_unchanged(old,updated,workflow)
    updated['sections'][0]['subheadings'].remove('1.1 文件')
    with pytest.raises(ValueError):assert_unchanged(old,updated,workflow)


def test_generation_stages_result_without_export_or_history(session,monkeypatch):
    target,route,req,base=session
    server.save(target/'analysis.json',{'chunks':[{'id':'e','source':'资料','locator':'p1','text':'项目来源。'}]})
    monkeypatch.setattr(server,'validate_ready',lambda fields:None)
    seen=[]
    def generate(*args,**kwargs):
        seen.append(kwargs['previous']);draft=copy.deepcopy(kwargs['previous']);draft['sections'][0]['paragraphs'][0]['text']='重写的小节内容。';return draft
    monkeypatch.setattr(server,'generate',generate)
    monkeypatch.setattr(server,'export_report',lambda *args:pytest.fail('暂存生成不得导出'))
    server.job(target,'generate',False,None,['1'],defer_version=True)
    assert seen and len(versions.history(target))==1 and versions.working_revision(target)==1
    assert versions.load_report(target)['sections'][0]['paragraphs'][0]['text']=='重写的小节内容。'
    assert server.load(target/'state.json')['report_version']==base and not server.load(target/'state.json').get('error')


def test_first_generation_working_copy_has_no_download_or_fake_legacy_version(tmp_path):
    server.save(tmp_path/'state.json',{'report_version':''})
    versions.stage(tmp_path,report())
    assert versions.load_report(tmp_path) and versions.history(tmp_path)==[]
    assert not (tmp_path/'report.docx').exists()
    assert versions.load_working(tmp_path)['base_version']==''


def test_locked_subsection_is_rejected_before_any_generation_task(session,monkeypatch):
    target,route,req,base=session
    server.state_update(target,files=[{'id':'f','name':'source.txt','stored':'source.txt','sha256':'h','size':1,'role':'source','active':True}],analysis_dirty=False)
    server.save(target/'analysis.json',{'chunks':[]})
    req(route+'/subsection-approval',{'base_version':base,'working_revision':0,'chapter_id':'1','heading':'1.1 文件','locked':True})
    monkeypatch.setattr(server.settings,'resolve',lambda *args:{'model':'mock'})
    monkeypatch.setattr(server,'validate_ready',lambda *args:None)
    calls=[]
    class Pool:
        def submit(self,*args):calls.append(args)
    monkeypatch.setattr(server,'POOL',Pool())
    data={'base_version':base,'working_revision':0,'chapter_ids':['1'],'subsections':{'1':['1.1 文件']},'use_llm':True}
    with pytest.raises(urllib.error.HTTPError) as e:req(route+'/generate',data)
    assert '锁定' in json.load(e.value)['error'] and not calls
    req(route+'/generate',{**data,'subsections':{'1':['1.2 标准']}})
    assert calls[-1][-1] is True and calls[-1][-2]=={'1':['1.2 标准']}
