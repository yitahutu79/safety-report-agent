import copy
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

class Document:
    def __init__(self):self.paragraphs=[]
    def add_heading(self,text,level):self.paragraphs.append((text,level))
    def add_paragraph(self,text):self.paragraphs.append((text,None))
    def save(self,path):
        body=''.join('<w:p>'+('<w:pPr><w:pStyle w:val="H'+str(level)+'"/></w:pPr>' if level else '')+'<w:r><w:t>'+escape(text)+'</w:t></w:r></w:p>' for text,level in self.paragraphs)
        ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="'+ns+'"><w:body>'+body+'</w:body></w:document>')
            z.writestr('word/styles.xml','<w:styles xmlns:w="'+ns+'">'+''.join('<w:style w:styleId="H'+str(i)+'"><w:pPr><w:outlineLvl w:val="'+str(i-1)+'"/></w:pPr></w:style>' for i in (1,2))+'</w:styles>')

from safety_report import project_intake as intake, server
from safety_report.structured_data import merge_candidates,report_evidence


def file(ident='r',role='reference'):
    return {'id':ident,'stored':ident+'.docx','name':ident+'.docx','sha256':'hash-'+ident,'active':True,'role':role,'document_type':'historical_design','size':1}


def test_automatic_candidates_extract_explicit_values_keep_quotes_and_remain_drafts():
    f=file();quote='建设单位：测试企业；项目名称：测试工程；建筑面积：100平方米。'
    chunks=[{'id':'e1','sha256':f['sha256'],'source':f['name'],'locator':'body[1]','text':quote}]
    records,coverage=intake.automatic_candidates({'reference_chunks':chunks},[f])
    r=next(r for r in records if r['domain']=='project_base')
    assert r['values']['对象或单位']=='测试企业' and r['source_quote']==quote
    assert r['status']=='draft' and not report_evidence(records,[f])
    existing=[];assert merge_candidates(existing,records);assert not merge_candidates(existing,records)
    r.update(status='reviewed',report_section='2',review_note='转录核对')
    assert report_evidence(records,[f])[0]['corpus']=='reference_document'
    assert coverage[0]['automatic_candidates']>0


def test_reference_reader_and_reuse_candidates_preserve_approval_on_reread(tmp_path):
    (tmp_path/'uploads').mkdir();f=file();d=Document();d.add_heading('1 设计依据',level=1);d.add_heading('1.1 通用机理',level=2)
    d.add_paragraph('电气接线部位应保持机械连接牢固，并定期检查绝缘和保护接地的可靠性。')
    d.save(tmp_path/'uploads'/f['stored'])
    docs,chunks,warnings=intake.reference_analysis(tmp_path,[f],{})
    assert docs and chunks and all(c['corpus']=='reference_document' for c in chunks)
    # Use the actual file hash, as production uploads do.
    import hashlib
    f['sha256']=hashlib.sha256((tmp_path/'uploads'/f['stored']).read_bytes()).hexdigest()
    docs,chunks,_=intake.reference_analysis(tmp_path,[f],{})
    profile=intake.reference_reuse_profile({'reference_documents':docs},[f],[{'text':'1.1 通用机理'}],{})
    assert len(profile['body_blocks'])==1 and profile['body_blocks'][0]['heading']=='1.1 通用机理'
    profile['body_blocks'][0].update(reviewed=True,decision='direct',applicability='测试条件')
    updated=intake.reference_reuse_profile({'reference_documents':docs},[f],[{'text':'1.1 通用机理'}],profile)
    assert updated==profile


def test_uploaded_materials_are_not_presented_as_not_uploaded():
    result={'requests':[{'priority':'必须','subheading':'3.1 物料','ask':'请上传MSDS','include':'安全技术说明书及危险特性','reason':'核对特性','examples':['MSDS']}],'can_draft_now':False,'note':''}
    inventory=[{'name':'危险物料MSDS.pdf','document_type':'sds','role':'source','text_available':True}]
    annotated=intake.annotate_material_availability(result,inventory)
    assert annotated['requests'][0]['availability']=='uploaded_readable'
    assert '不必重复上传' in annotated['requests'][0]['ask'] and result['requests'][0]['ask']=='请上传MSDS'
    inventory[0]['text_available']=False
    assert intake.annotate_material_availability(result,inventory)['requests'][0]['availability']=='uploaded_unreadable'


def test_analyze_reads_reference_body_and_builds_local_records_without_model(tmp_path,monkeypatch):
    import hashlib
    (tmp_path/'uploads').mkdir();files=[]
    for ident,role,text in [('p','source','建设单位：本项目企业；项目名称：工程；消防水泵设置见设计清单。'),('r','reference','电气设备应设置保护接地，定期检查接地连接和绝缘状况。')]:
        f=file(ident,role);d=Document();d.add_heading('1 设计依据',level=1);d.add_heading('1.1 文件',level=2);d.add_paragraph(text);d.save(tmp_path/'uploads'/f['stored'])
        f['sha256']=hashlib.sha256((tmp_path/'uploads'/f['stored']).read_bytes()).hexdigest();files.append(f)
    state=server.upgrade_state({'id':'test','report_type':'facility_design','files':files,'fields':[]});server.save(tmp_path/'state.json',state)
    class Index:
        client=None;semantic_error='离线测试'
        def __init__(self,*args,**kwargs):pass
    monkeypatch.setattr('safety_report.documents.HybridEvidenceIndex',Index)
    result=server.analyze_project(tmp_path)
    assert result['reference_chunks'] and all(c.get('corpus')!='reference_document' for c in result['chunks'])
    assert server.load(tmp_path/'structured-data.json')
    assert server.load(tmp_path/'reference-reuse.json')['body_blocks']
    assert server.load(tmp_path/'state.json')['reference_chunk_count']>0
    again=server.analyze_project(tmp_path)
    assert len(server.load(tmp_path/'structured-data.json'))==sum(c['automatic_candidates'] for c in again['intake_coverage'])
    assert all(r['status']=='draft' for r in server.load(tmp_path/'structured-data.json'))


def test_reference_reuse_not_available_after_source_disabled(tmp_path):
    f=file();state=server.upgrade_state({'id':'test','report_type':'facility_design','files':[f]});server.save(tmp_path/'state.json',state)
    b={'id':'ref-r-abc','heading':'1.1 文件','source_file_id':'r','source_sha256':f['sha256'],'text':'通用文字','original_text':'通用文字','decision':'direct','reviewed':True,'applicability':'条件'}
    server.save(tmp_path/'reference-reuse.json',{'body_blocks':[b],'content_revision':1})
    assert any(x['id']==b['id'] for x in server.project_profile(tmp_path)['body_blocks'])
    state['files'][0]['active']=False;server.save(tmp_path/'state.json',state)
    assert not any(x['id']==b['id'] for x in server.project_profile(tmp_path)['body_blocks'])


def test_reference_reuse_http_review_and_revision_guard(tmp_path,monkeypatch):
    import json,threading,urllib.request,urllib.error
    import pytest
    from http.server import ThreadingHTTPServer
    from safety_report.report_template import approved_reuse_evidence
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    def req(path,data=None):
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}'+path,data=json.dumps(data).encode() if data is not None else None),timeout=5) as res:return json.load(res)
    try:
        pid=req('/api/projects',{'name':'参考正文复用接口'})['id'];target=tmp_path/pid;route='/api/projects/'+pid
        f=file();server.state_update(target,files=[f])
        heading=next(h['text'] for h in server.project_profile(target)['headings'] if h['level']==2)
        text='电气设备的保护接地连接应保持牢固，并定期检查接线连接与绝缘状态。'
        block={'id':'ref-r-1','heading':heading,'source_heading':'1.1 参考节','source_file':f['name'],'source_file_id':f['id'],'source_sha256':f['sha256'],'locator':'body[2]','original_text':text,'text':text,'decision':'reference','reviewed':False,'applicability':'','risks':[]}
        server.save(target/'reference-reuse.json',{'body_blocks':[block],'content_revision':1})
        data=req(route+'/report-template-content');assert len(data['blocks'])==1
        payload={'id':block['id'],'expected_revision':data['content_revision'],'heading':heading,'text':text,'decision':'direct','applicability':'存在电气设备，通用检查要求，不认定现状','applicability_confirmed':True}
        req(route+'/template-content-review',payload)
        approved=approved_reuse_evidence(server.project_profile(target),[heading])
        assert approved[0]['text']==text and approved[0]['source']==f['name']
        with pytest.raises(urllib.error.HTTPError):req(route+'/template-content-review',payload)
        server.state_update(target,files=[{**f,'active':False}])
        assert not approved_reuse_evidence(server.project_profile(target),[heading])
    finally:http.shutdown();http.server_close();thread.join(timeout=5)


def test_preflight_receives_inventory_confirmed_fields_and_reference_boundary(monkeypatch):
    from safety_report import pipeline
    captured={}
    def complete(system,payload,model,**kwargs):
        captured.update(payload)
        return {'requests':[{'priority':'先确认适用性','subheading':'3.1 物料','ask':'请提供MSDS','include':'物料名称及危险特性','reason':'需核对物料','examples':['MSDS']}],'can_draft_now':False,'note':''}
    monkeypatch.setattr(pipeline,'complete_json',complete)
    section={'subheadings':['3.1 物料'],'available_files':[{'name':'MSDS.pdf','document_type':'sds','role':'source','text_available':True}],
             'confirmed_fields':[{'label':'建设单位','value':'测试'}],'retrieval_scope':{'reference_chunks':1}}
    evidence=[{'id':'r','source':'参考报告','locator':'body[2]','text':'参考资料记载。','corpus':'reference_document'}]
    result=pipeline.plan_missing_materials('3 分析',section,evidence,{})
    assert captured['existing_evidence'][0]['corpus']=='reference_document'
    assert captured['confirmed_fields']==section['confirmed_fields']
    assert result['requests'][0]['availability']=='uploaded_readable'


def test_heading_search_returns_body_with_context_without_altering_source_text():
    doc={'blocks':[{'kind':'paragraph','level':2,'locator':'body[1]','text':'1.3 执行标准清单'},
                   {'kind':'paragraph','level':None,'locator':'body[2]','text':'GB 50016-2014 建筑设计防火规范。'}],
         'chunks':[{'id':'h','locator':'body[1]','text':'1.3 执行标准清单'},
                   {'id':'b','locator':'body[2]','text':'GB 50016-2014 建筑设计防火规范。'}]}
    intake.attach_section_context(doc)
    result=intake.SectionEvidenceIndex(doc['chunks']).search('执行标准清单')
    assert result[0]['id']=='b' and result[0]['text']=='GB 50016-2014 建筑设计防火规范。'
    assert result[0]['source_heading']=='1.3 执行标准清单'


def test_auto_records_skip_toc_and_standalone_headings():
    title='1.2国家、行业及地方相关法律、法规、规章及规范性文件'
    doc={'sha256':'h','blocks':[{'locator':'b1','text':title+'1','style_name':'toc 2','level':None},
        {'locator':'b2','text':title,'style_name':'标题2','level':2},
        {'locator':'b3','text':'GB 50016-2014 《建筑设计防火规范》','level':None}]}
    chunks=[{'id':b['locator'],'locator':b['locator'],'sha256':'h','source':'正文.docx','text':b['text']} for b in doc['blocks']]
    result,_=intake.automatic_candidates({'documents':[doc],'chunks':chunks},[{'id':'f','name':'正文.docx','sha256':'h','role':'source'}])
    assert result and {r['source_locator'] for r in result}=={'b3'}
