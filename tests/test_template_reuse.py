import pytest
from safety_report.report_template import review_body_block,approved_reuse_evidence,exact_approved_reuse
from safety_report.pipeline import readability_issues

TEXT='触电危险可能发生于接线端、电线接头、插头、插座及开关等部位。保护措施失效或不规范操作时，人员接触带电体可能受到电击。相关分析应结合电气设备及作业条件确定。'*2

def profile():
    return {'sha256':'template','name':'模板','body_blocks':[{'id':'b1','heading':'3.1 触电','locator':'body[2]','text':TEXT,'original_text':TEXT,'decision':'reference','reviewed':False,'applicability':''}]}

def test_only_reviewed_applicable_generic_text_can_be_reused_verbatim():
    p=profile();assert not approved_reuse_evidence(p)
    request={'id':'b1','expected_revision':0,'decision':'direct','text':TEXT,'applicability':'适用于本项目低压用电的一般机理分析，不表示存在现场缺陷','applicability_confirmed':True}
    review_body_block(p,request);e=approved_reuse_evidence(p,['3.1 触电'])
    para={'heading':'3.1 触电','text':TEXT,'evidence_ids':[e[0]['id']]}
    assert exact_approved_reuse(para,e)
    assert not readability_issues({'paragraphs':[para]},e)
    assert readability_issues({'paragraphs':[dict(para,heading='2 概况')]},e)
    assert readability_issues({'paragraphs':[dict(para,text=TEXT+'本项目已完成验收。')]},e)
    assert not approved_reuse_evidence(p,['2 概况'])
    with pytest.raises(ValueError,match='已更新'):review_body_block(p,request)


def test_project_facts_and_laws_require_adaptation_not_direct_approval():
    p=profile()
    for text in ['本项目已安装报警装置。','执行GB 50016-2014。','设备设计压力为2MPa。']:
        with pytest.raises(ValueError):review_body_block(p,{'id':'b1','expected_revision':0,'decision':'direct','text':text,'applicability':'适用','applicability_confirmed':True})
    with pytest.raises(ValueError,match='适用条件'):review_body_block(p,{'id':'b1','expected_revision':0,'decision':'direct','text':TEXT})
    review_body_block(p,{'id':'b1','expected_revision':0,'decision':'adapt','text':'本项目已安装报警装置。','applicability':'仅作写作参考，需现场证据','applicability_confirmed':True})
    e=approved_reuse_evidence(p)
    assert e and not exact_approved_reuse({'text':e[0]['text'],'heading':'3.1 触电','evidence_ids':[e[0]['id']]},e)


def test_fixed_text_is_assembled_exactly_and_other_content_retained():
    from safety_report.report_template import insert_approved_fixed_text
    p=profile();review_body_block(p,{'id':'b1','expected_revision':0,'decision':'direct','text':TEXT,'applicability':'低压配电一般机理','applicability_confirmed':True})
    evidence=approved_reuse_evidence(p)
    draft={'paragraphs':[{'heading':'3.1 触电','text':'模型改写固定内容','evidence_ids':[evidence[0]['id']]},{'heading':'3.1 触电','text':'项目证据支持的具体分析','evidence_ids':['project-id']}],'tables':[]}
    insert_approved_fixed_text(draft,evidence)
    assert len(draft['paragraphs'])==2 and draft['paragraphs'][0]['text']==TEXT
    assert draft['paragraphs'][1]['evidence_ids']==['project-id']
    assert draft['template_reuse_records'][0]['applicability']=='低压配电一般机理'
    insert_approved_fixed_text(draft,evidence)
    assert len(draft['paragraphs'])==2
