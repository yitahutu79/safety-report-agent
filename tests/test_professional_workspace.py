from safety_report.professional_workspace import link_record,link_views,apply_links_to_evidence
import pytest


def test_references_master_once_and_detects_revision_or_review_changes():
    p=[{'id':'p1','title':'风险分析','report_section':'3','status':'reviewed'}]
    c=[{'id':'c1','title':'用水计算','status':'reviewed','revision':1}];m=[];links=[]
    link_record(links,'p1','calculation','c1','引用用水计算结果',p,c,m)
    link_record(links,'p1','calculation','c1','更新引用说明',p,c,m)
    assert len(links)==1
    evidence=[{'id':'calculation-c1-r1','text':'原始结果'}]
    apply_links_to_evidence(evidence,links,p,c,m)
    assert len(evidence)==1 and evidence[0]['linked_report_sections']==['3']
    assert link_views(links,p,c,m)[0]['status']=='可引用'
    c[0]['revision']=2
    assert link_views(links,p,c,m)[0]['status']=='引用版本已变化'
    new=[{'id':'calculation-c1-r2','text':'新结果'}]
    apply_links_to_evidence(new,links,p,c,m)
    assert 'linked_report_sections' not in new[0]
    link_record(links,'p1','calculation','c1','复核新版本',p,c,m)
    c[0]['status']='draft'
    assert link_views(links,p,c,m)[0]['status']=='目标待审核'
    with pytest.raises(ValueError):link_record(links,'missing','calculation','c1','用途说明',p,c,m)


def test_measure_references_do_not_approve_unreviewed_source():
    p=[{'id':'p1','title':'分析','report_section':'5','status':'draft'}]
    m=[{'id':'m1','recommendation':'设置措施','revision':1,'disposition':'adopted','reviewed_by':'审核人'}]
    links=[];link_record(links,'p1','measure','m1','用于设计承接',p,[],m)
    assert link_views(links,p,[],m)[0]['status']=='分析待审核'
    p[0]['status']='reviewed'
    assert link_views(links,p,[],m)[0]['status']=='可引用'


def test_http_workspace_links_do_not_copy_or_mutate_master_records(tmp_path,monkeypatch):
    import json,threading,urllib.request
    from http.server import ThreadingHTTPServer
    from safety_report import server
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None):
        with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None),timeout=5) as response:return json.load(response)
    try:
        pid=req('/api/projects',{'name':'专业关联接口回归'})['id'];route='/api/projects/'+pid;t=tmp_path/pid
        p={'items':[{'id':'p1','title':'风险分析','status':'reviewed','report_section':'3','revision':1}]}
        c={'items':[{'id':'c1','title':'用水计算','status':'reviewed','revision':1}]}
        server.save(t/'professional.json',p);server.save(t/'calculations.json',c)
        request={'source_id':'p1','target_kind':'calculation','target_id':'c1','note':'引用原计算，不重复填写'}
        req(route+'/professional-link',request);req(route+'/professional-link',request)
        view=req(route+'/professional-workspace')
        assert len(view['links'])==1 and view['links'][0]['status']=='可引用'
        assert server.load(t/'professional.json')==p and server.load(t/'calculations.json')==c
        c['items'][0]['revision']=2;server.save(t/'calculations.json',c)
        assert req(route+'/professional-workspace')['links'][0]['status']=='引用版本已变化'
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)
