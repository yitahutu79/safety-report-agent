from safety_report.rag_workbench import expand_source_context
from safety_report.knowledge_qa import prepare_evidence


def item(ident,text,number,source='source.docx',sha='s'):
    return dict(id=ident,text=text,locator=f'body[{number}]',source=source,sha256=sha)


def test_title_resolves_to_nearby_body_without_crossing_file_or_revision():
    heading=item('h','2.1.1建设单位',20)
    body=item('b','测试有限公司成立于2025年03月21日。经营范围：包装制造。',21)
    foreign=item('f','另一家有限公司成立于2024年，经营范围：其他。',21,source='other.docx')
    old=item('o','旧有限公司成立于2020年，经营范围：其他。',21,sha='old')
    actual=expand_source_context([heading,body,foreign,old],[heading],'建设单位的名称、成立日期和经营范围是什么？',8)
    assert actual[0]['id']=='b' and {x['id'] for x in actual}=={'h','b'}


def test_personal_fields_and_company_facts_are_retained():
    q='建设单位的名称、成立日期和经营范围是什么？'
    evidence=[item('b','测试有限公司成立于2025年03月21日，法定代表人为张某。经营范围包括许可项目：包装制造；一般项目：材料销售。联系电话：13812345678。',21)]
    text=prepare_evidence(q,evidence)[0]['text']
    assert '成立于2025年03月21日' in text and '经营范围' in text
    assert '张某' in text and '13812345678' in text


def test_business_scope_preserves_complete_bounded_paragraph():
    text='测试有限公司成立于2025年03月21日，经营范围：'+('包装材料销售；'*70)+'技术进出口。'
    result=prepare_evidence('建设单位的成立日期和经营范围是什么？',[item('b',text,21)])
    assert result[0]['text'].endswith('技术进出口。') and result[0]['text']==text


def test_question_can_use_personal_fields_with_source_citation():
    from safety_report.knowledge_qa import answer_question
    source=item('contact','法定代表人：张某。联系人：李某。联系电话：13812345678。证照号码：TEST-001。',21)
    def model(system,payload,config,**kwargs):
        text=payload['evidence'][0]['text']
        assert all(value in text for value in ('张某','李某','13812345678','TEST-001'))
        return {'paragraphs':[{'text':'联系人为李某，联系电话为13812345678。','evidence_ids':['contact']}],'missing':[]}
    result=answer_question('法定代表人、联系人、联系电话和证照号码是什么？',[source],{},complete=model)
    assert result['sources'][0]['id']=='contact'
    assert source['text'].endswith('TEST-001。')


def test_short_sds_page_keeps_name_and_hazard_section_together():
    text='DICDRY LX-830FR\n其他标识：无资料。\n'+('企业说明。'*35)+'\n通用名称：胶粘剂\n第2部分 危险性概述\n易燃液体-类别2'
    source=item('sds',text,4)
    assert prepare_evidence('LX-830FR的产品名称、通用名称和危险性分类是什么？',[source])[0]['text']==text


def test_explicit_model_and_file_exclude_similar_sds_products():
    target=item('a','DICDRY LX-830FR 产品名称 通用名称 胶粘剂 第2部分 危险性概述 易燃液体类别2',4,source='MSDS.pdf')
    other=item('b','DICDRY LX-500FR 产品名称 通用名称 胶粘剂 危险性分类',5,source='MSDS.pdf')
    unrelated=item('c',target['text'],4,source='其他项目.docx')
    result=expand_source_context([target,other,unrelated],[other,unrelated],'请查《MSDS.pdf》中LX-830FR的产品名称、通用名称和危险性分类',8)
    assert [x['id'] for x in result]==['a']
    assert expand_source_context([other],[other],'查《MSDS.pdf》中LX-999FR的危险性分类',8)==[]


def test_association_question_retrieves_model_and_generic_project_material_list():
    msds=item('m','DICDRY LX-830FR 通用名称胶粘剂。',4,source='MSDS.pdf')
    other=item('wrong','DICDRY LX-500FR 通用名称胶粘剂。',14,source='MSDS.pdf')
    project=item('p','本项目实际使用干复胶，储存在油墨胶水仓库。',264,source='正文.docx')
    result=expand_source_context([msds,other,project],[msds,other],'本项目实际使用的干复胶是否明确对应DICDRY LX-830FR型号？',8)
    assert {x['id'] for x in result}=={'m','p'}
    assert 'LX-830FR' not in project['text']
