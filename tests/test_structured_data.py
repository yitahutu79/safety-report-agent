from unittest.mock import patch
import pytest
from safety_report.structured_data import extract_candidates,select_evidence,merge_candidates,update_record,report_evidence
from safety_report.document_catalog import DOMAINS

FILE={'id':'f1','name':'设备台账.txt','sha256':'hash','active':True,'document_type':'equipment_ledger'}
EVIDENCE=[{'id':'e1','source':'设备台账.txt','sha256':'hash','locator':'paragraph[1]','text':'设备名称：反应釜；设备编号：R-01；来源为设计清单，并非现场核查。'}]

def response(quote=None):
    return {'records':[{'title':'反应釜清单','values':{'设施名称或编号':'反应釜 R-01','计划或现场状态':'设计清单，非现场核查'},'evidence_id':'e1','source_quote':quote or EVIDENCE[0]['text']}]}


def test_candidates_are_unapproved_grounded_and_file_scoped():
    selected,coverage=select_evidence(EVIDENCE+[dict(EVIDENCE[0],id='other',source='他项目',sha256='other'),dict(EVIDENCE[0],id='same-name',sha256='different-version')],FILE,'facility')
    assert len(selected)==1 and coverage['available_chunks']==1
    with patch('safety_report.structured_data.provider.complete_json',return_value=response()) as call:
        candidates=extract_candidates(selected,'facility',FILE,{})
    assert candidates[0]['status']=='draft' and candidates[0]['values']['核查依据']==''
    assert not report_evidence(candidates,[FILE])
    records=[];assert len(merge_candidates(records,candidates))==1
    assert not merge_candidates(records,candidates)
    update_record(records,{'id':records[0]['id'],'revision':1,'values':records[0]['values'],'status':'reviewed','reviewer':'核对人','review_note':'与设计清单一致，不是现场认定','report_section':'6'},{'6'},[FILE])
    evidence=report_evidence(records,[FILE])
    assert evidence[0]['report_section']=='6' and '并非现场核查' in evidence[0]['text']
    assert not report_evidence(records,[dict(FILE,active=False)])
    assert not report_evidence(records,[])
    with pytest.raises(ValueError):update_record(records,{'id':records[0]['id'],'revision':1,'values':records[0]['values'],'status':'draft'},{'6'},[FILE])


def test_fabricated_quotes_and_unknown_fields_do_not_enter_records():
    for data in [response('并不存在的引句'),{'records':[dict(response()['records'][0],values={'不存在字段':'值'})]}]:
        with patch('safety_report.structured_data.provider.complete_json',return_value=data),pytest.raises(ValueError):extract_candidates(EVIDENCE,'facility',FILE,{})


def test_approval_needs_reviewer_scope_and_active_source():
    with patch('safety_report.structured_data.provider.complete_json',return_value=response()):records=extract_candidates(EVIDENCE,'facility',FILE,{})
    r=records[0]
    with pytest.raises(ValueError):update_record(records,{'id':r['id'],'revision':1,'values':r['values'],'status':'reviewed'},{'6'},[FILE])
    with pytest.raises(ValueError):update_record(records,{'id':r['id'],'revision':1,'values':r['values'],'status':'reviewed','reviewer':'A','review_note':'核对','report_section':'6'},{'6'},[])
