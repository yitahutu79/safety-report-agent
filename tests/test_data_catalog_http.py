import json
import threading
import urllib.request
import urllib.parse
from http.server import ThreadingHTTPServer
from safety_report import server
from safety_report.default_outlines import catalog_profile
from safety_report.document_catalog import DOMAINS


def test_new_projects_use_catalog_existing_projects_keep_original(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None,raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'默认大纲接口回归'})['id'];route='/api/projects/'+pid
        profile=req('/api/template?project_id='+pid)
        assert '工作资料/大纲设计' in profile['outline_source']
        assert len([h for h in profile['headings'] if h['level']==1])==13
        assert req(route+'/professional')['kinds']['design'][1]=='6'
        uploaded=req(route+'/upload?name='+urllib.parse.quote('危险化学品MSDS.txt'),raw='仅作分类测试的文本'.encode())
        file=req(route)['files'][0]
        assert file['document_type']=='sds'
        req(route+'/files',{'id':file['id'],'document_type':'equipment_inspection'})
        assert req(route)['files'][0]['document_type']=='equipment_inspection'
        oldid=req('/api/projects',{'name':'旧项目兼容回归'})['id'];old=tmp_path/oldid
        (old/'default-outline.json').unlink()
        oldprofile=req('/api/template?project_id='+oldid)
        assert len([h for h in oldprofile['headings'] if h['level']==1])==7
        req('/api/projects/'+oldid+'/template-reset',{})
        assert len([h for h in req('/api/template?project_id='+oldid)['headings'] if h['level']==1])==13
        preid=req('/api/projects',{'name':'预评价无来源大纲回归','report_type':'pre_evaluation'})['id']
        assert req('/api/template?project_id='+preid)['outline_source']=='系统原有大纲'
        assert 'facility' in req('/api/knowledge')['categories']
        assert req(route+'/structured-data')['records']==[]
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_structured_job_and_approval_pass_only_reviewed_records_to_report(tmp_path,monkeypatch):
    from safety_report.structured_data import report_evidence
    monkeypatch.setattr(server,'DATA',tmp_path)
    pid='a'*24;t=tmp_path/pid;t.mkdir()
    file={'id':'f1','name':'设计清单.txt','stored':'f1.txt','sha256':'h','active':True,'role':'source','document_type':'historical_design','size':1}
    server.save(t/'state.json',{'id':pid,'name':'隔离提取测试','files':[file],'fields':[],'busy':True,'report_type':'facility_design'})
    server.save(t/'analysis.json',{'chunks':[{'id':'e1','source':file['name'],'sha256':'h','locator':'paragraph[1]','text':'设计清单载明拟设置报警设施，参数尚未确定。'}]})
    response={'records':[{'title':'报警设施','values':{'设施名称或编号':'报警设施','计划或现场状态':'拟设置，非现场核查'},'evidence_id':'e1','source_quote':'设计清单载明拟设置报警设施，参数尚未确定。'}]}
    monkeypatch.setattr('safety_report.structured_data.provider.complete_json',lambda *args,**kwargs:response)
    server.structured_extract_job(t,'f1','facility',{},threading.Event())
    state=server.load(t/'state.json');records=server.load(t/'structured-data.json')
    assert not state['busy'] and records[0]['status']=='draft'
    assert state['structured_coverage']['selected_chunks']==1
    assert not report_evidence(records,[file])
