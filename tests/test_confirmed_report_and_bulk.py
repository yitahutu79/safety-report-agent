import copy
import pytest
from safety_report import pipeline,server
from safety_report.report_source import provided_report_draft
from safety_report.structured_data import bulk_review,report_evidence


def analysis():
    text='本项目依据备案文件编制。'+('现有报告正文应保留原有表述及限定条件。'*200)
    return {'chunks':[],'confirmed_report_sources':[{'id':'f','sha256':'h','name':'正文.docx'}],
            'documents':[{'sha256':'h','blocks':[{'kind':'paragraph','level':2,'text':'1.1 批复文件','locator':'b1'},
            {'kind':'paragraph','level':None,'text':text,'locator':'b2'},
            {'kind':'table','level':None,'text':'项目|数值\n编号|123','rows':[['项目','数值'],['编号','123']],'locator':'b3'}]}]}


def test_confirmed_report_preserves_long_paragraph_and_table_without_model(monkeypatch):
    a=analysis();profile={'sha256':'t','custom_template':True,'headings':[{'text':'1 依据','level':1,'subheadings':['1.1 批复文件']}]}
    class Index:
        client=None;semantic_error=None
        def __init__(self,*args):pass
        def search(self,*args,**kwargs):return []
        def close(self):pass
    monkeypatch.setattr(pipeline,'HybridEvidenceIndex',Index)
    monkeypatch.setattr(pipeline,'complete_json',lambda *args,**kw:pytest.fail('原文复用不应调用模型'))
    old={'sections':[{'title':'1 依据','subheadings':['1.1 批复文件'],'paragraphs':[],'tables':[],'missing':[],'review':[]}],'evidence':[]}
    result=pipeline.generate(profile,a,[],True,model={},previous=old,chapter_ids=['1'],subsections={'1':['1.1 批复文件']})
    chapter=result['sections'][0]
    assert chapter['paragraphs'][0]['text']==a['documents'][0]['blocks'][1]['text']
    assert len(chapter['paragraphs'][0]['text'])>2200 and chapter['tables'][0]['rows']==[['编号','123']]
    assert not result['quality_checked']


def test_preflight_uses_confirmed_report_and_does_not_request_original_scan(tmp_path,monkeypatch):
    a=analysis();server.save(tmp_path/'analysis.json',a)
    server.save(tmp_path/'state.json',{'id':'t','files':[{'id':'f','name':'正文.docx','stored':'f.docx','sha256':'h','role':'source','active':True,'report_source_confirmed':True}],'fields':[],'report_type':'facility_design'})
    monkeypatch.setattr(server,'template_compatible_report',lambda _: {'sections':[{'title':'1 依据','subheadings':['1.1 批复文件']}]})
    monkeypatch.setattr(server,'plan_missing_materials',lambda *a,**kw:pytest.fail('已有报告不应重复要求备案原件'))
    plan=server.chapter_materials_plan(tmp_path,'1',{},subsection_titles=['1.1 批复文件'])
    assert plan['requests']==[] and plan['can_draft_now']


def test_unconfirmed_report_does_not_gain_copy_permission():
    a=analysis();a['confirmed_report_sources']=[]
    assert not provided_report_draft(a,['1.1 批复文件'])['covered_headings']


def records():
    from safety_report.document_catalog import DOMAINS
    return [{'id':str(i),'revision':1,'status':'draft','domain':'hazard','file_id':'f','source_sha256':'h','source_file':'资料','source_locator':'p1','document_type':'sds','source_quote':'原句','title':'危险因素','values':{k:'' for k in DOMAINS['hazard']['fields']},'report_section':'','history':[]} for i in range(3)]


def test_bulk_review_once_with_no_chapter_keeps_records_out_of_writing():
    old=records();files=[{'id':'f','sha256':'h','active':True}]
    data={'items':[{'id':r['id'],'revision':1} for r in old],'reviewer':'统一核对人','review_note':'按原句核对','status':'reviewed'}
    new,changed=bulk_review(old,data,{'3'},files)
    assert len(changed)==3 and all(r['status']=='checked' and r['reviewer']=='统一核对人' for r in new)
    assert not report_evidence(new,files) and all(r['revision']==1 for r in old)
    assigned,_=bulk_review(new,{**data,'items':[{'id':r['id'],'revision':2} for r in new],'report_section':'3'},{'3'},files)
    assert len(report_evidence(assigned,files))==3


def test_bulk_stale_revision_rolls_back_entire_batch():
    old=records();snapshot=copy.deepcopy(old)
    with pytest.raises(ValueError):bulk_review(old,{'items':[{'id':'0','revision':1},{'id':'1','revision':99}],'reviewer':'甲','review_note':'核对','report_section':'3'},{'3'},[{'id':'f','sha256':'h'}])
    assert old==snapshot


def test_local_extraction_is_not_limited_to_forty_rows():
    from safety_report.project_intake import automatic_candidates
    text='\n'.join('GB '+str(50000+i)+'-2020 《专业技术标准示例条目》' for i in range(60))
    result,_=automatic_candidates({'chunks':[{'id':'e','sha256':'h','source':'资料','locator':'p1','text':text}]},[{'id':'f','name':'资料','sha256':'h','role':'source','active':True}])
    assert len([r for r in result if r['domain']=='regulation'])==60


def test_partial_reuse_removes_stale_missing_note_only_for_selected_heading():
    old={'title':'1 依据','paragraphs':[],'tables':[],'missing':['1.1 批复文件：缺少完整备案扫描件','1.2 标准：需补充标准清单'],'review':[]}
    new={'paragraphs':[],'tables':[],'missing':[],'review':['原件有效性由专业人员核验']}
    merged=pipeline.merge_subsection_revision(old,new,['1.1 批复文件'],['1.1 批复文件','1.2 标准'])
    assert merged['missing']==['1.2 标准：需补充标准清单']
    assert merged['review']==new['review']
