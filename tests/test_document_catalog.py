from pathlib import Path
import hashlib
from safety_report.document_catalog import suggest_document_type,DOMAINS
from safety_report.default_outlines import catalog_profile,semantic_workflows
from safety_report.professional_workflow import WORKFLOWS
from safety_report import server


def test_business_outline_has_seven_types_and_missing_pre_eval_is_not_invented():
    p=catalog_profile(server.ROOT,'facility_design')
    mains=[h for h in p['headings'] if h['level']==1]
    assert len(mains)==13
    assert mains[10]['text'].startswith('11 安全预评价报告中对策措施')
    assert catalog_profile(server.ROOT,'pre_evaluation') is None
    mapped=semantic_workflows(WORKFLOWS['facility_design'],p)
    assert mapped['design'][1]=='6' and mapped['hazard'][1]=='3'
    assert semantic_workflows(WORKFLOWS['acceptance_evaluation'],catalog_profile(server.ROOT,'acceptance_evaluation'))['regulatory'][1]=='2'


def test_file_type_suggestions_keep_sensitive_project_documents_out_of_common_kb():
    assert suggest_document_type('化工原料MSDS.pdf')=='sds'
    assert suggest_document_type('营业执照.docx')=='company_certificate'
    assert suggest_document_type('特种作业持证名单.csv')=='special_operation_certificate'
    assert suggest_document_type('设备检验报告.pdf')=='equipment_inspection'
    assert suggest_document_type('总平面布置图.pdf')=='layout_drawing'
    assert len(DOMAINS)==6 and 'project_base' in DOMAINS
