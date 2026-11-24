import json
from pathlib import Path

import pytest

from safety_report.pipeline import generate, section_identity
from safety_report.professional_workflow import ProfessionalLedger, WORKFLOWS
from safety_report.workflow_schema import SCHEMAS
from safety_report.quality import review_report
from safety_report.report_types import report_profile
from safety_report import server


@pytest.mark.parametrize('kind', list(WORKFLOWS))
def test_reviewed_records_are_routed_to_their_chapter_with_source(kind, tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', kind)
    category, (_, chapter) = next(iter(WORKFLOWS[kind].items()))
    payload = {'kind': category, 'title': '测试项目专业记录', 'content': '人工核实的测试内容',
               'source_file': 'sample.docx', 'source_locator': '第 2 页', 'report_section': chapter,
               'status': 'draft', 'reviewer': '', 'review_note': ''}
    payload['details'] = {field['key']: (field.get('options') or ['测试内容'])[0] for field in SCHEMAS[kind][category]}
    original = ledger.save(payload)
    assert ledger.report_evidence() == []
    with pytest.raises(ValueError, match='复核人'):
        ledger.save({**payload, 'status': 'reviewed'}, original['id'])
    revised = ledger.save({**payload, 'status': 'reviewed', 'reviewer': '审核人'}, original['id'])
    assert revised['revision'] == 2 and revised['history'][0]['status'] == 'draft'
    evidence = ledger.report_evidence()
    facility = json.loads((Path(__file__).resolve().parent.parent / 'reference/profile.json').read_text())
    profile = report_profile(kind, facility)
    report = generate(profile, {'chunks': []}, [], False, chapter_ids=[chapter], professional_evidence=evidence)
    target = next(s for s in report['sections'] if section_identity(s) == chapter)
    assert target['paragraphs'][0]['evidence_ids'] == [evidence[0]['id']]
    assert any(e['id'] == evidence[0]['id'] and e['locator'] == '第 2 页' for e in report['evidence'])
    review = review_report(report, {'fields': [], 'files': [], 'report_type': kind}, professional_records=ledger.list())
    check = next(c for c in review['checks'] if c['key'] == 'professional_workflow')
    assert check['status'] == 'warning'  # Remaining work categories need professional review.


def test_cross_type_record_is_rejected(tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'emergency_plan')
    with pytest.raises(ValueError, match='类别'):
        ledger.save({'kind': 'inspection', 'title': '测试', 'content': '测试', 'source_file': 'a',
                     'source_locator': 'p1', 'status': 'draft'})


def test_preflight_includes_only_reviewed_records_for_selected_chapter(tmp_path, monkeypatch):
    (tmp_path / 'state.json').write_text(json.dumps({'report_type': 'emergency_plan', 'files': []}), encoding='utf-8')
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'emergency_plan')
    ledger.save({'kind': 'resources', 'title': '救援物资', 'content': '已核实清单', 'source_file': '清单.docx',
                 'source_locator': '第 1 页', 'status': 'reviewed', 'reviewer': '复核人',
                 'details': {'resource': '测试装备', 'quantity': '一套', 'location': '测试地点'}})
    ledger.save({'kind': 'resources', 'title': '待审核清单', 'content': '尚待核实', 'source_file': '清单.docx',
                 'source_locator': '第 2 页', 'status': 'draft'})
    received = []
    monkeypatch.setattr(server.versions, 'load_report', lambda _: None)
    def plan(chapter, section, evidence, model, **kwargs):
        received.extend(evidence)
        return {'requests': [], 'can_draft_now': True, 'note': ''}
    monkeypatch.setattr(server, 'plan_missing_materials', plan)
    server.chapter_materials_plan(tmp_path, '6', {'name': 'mock'})
    assert received and len({item['id'] for item in received}) == 1 and all(item['reviewed_by']=='复核人' for item in received)
    received.clear()
    server.chapter_materials_plan(tmp_path, '3', {'name': 'mock'})
    assert received == []


def test_rectification_requires_structured_review_and_warns_until_rechecked(tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'acceptance_evaluation')
    data = {'kind': 'rectification', 'title': '测试整改', 'content': '模拟问题整改', 'source_file': '整改记录.docx',
            'source_locator': '第 1 页', 'status': 'reviewed', 'reviewer': '复核人',
            'details': {'problem': '测试问题', 'action': '整改方案', 'progress': '进行中'}}
    with pytest.raises(ValueError, match='复查记录'):
        ledger.save(data)
    data['details']['verification'] = '现场照片第 1 页'
    record = ledger.save(data)
    report = {'report_type': 'acceptance_evaluation', 'sections': [], 'evidence': [], 'unconfirmed_fields': []}
    check = next(c for c in review_report(report, {'fields': [], 'files': []}, professional_records=ledger.list())['checks'] if c['key'] == 'professional_workflow')
    assert '尚未记录为复查通过' in check['detail']
    assert '整改状态：进行中' in ledger.report_evidence()[0]['text']
    data['details']['progress'] = '复查通过'
    changed = ledger.save(data, record['id'])
    assert changed['status'] == 'draft'
    ledger.save(data, record['id'])  # Explicit second review after content changed.
    check = next(c for c in review_report(report, {'fields': [], 'files': []}, professional_records=ledger.list())['checks'] if c['key'] == 'professional_workflow')
    assert '尚未记录为复查通过' not in check['detail']
    assert ledger.list()[0]['history'][0]['details']['progress'] == '进行中'


def test_legacy_reviewed_record_is_retained_but_incomplete_fields_are_warned(tmp_path):
    record = {'id': 'old', 'kind': 'resources', 'title': '旧资源记录', 'content': '历史内容', 'source_file': 'a',
              'source_locator': 'p1', 'status': 'reviewed', 'reviewer': '甲', 'report_section': '6', 'revision': 1, 'review_note': ''}
    (tmp_path / 'professional.json').write_text(json.dumps({'items': [record]}), encoding='utf-8')
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'emergency_plan')
    assert len(ledger.report_evidence()) == 1
    report = {'report_type': 'emergency_plan', 'sections': [], 'evidence': []}
    check = next(c for c in review_report(report, {'fields': [], 'files': []}, professional_records=ledger.list())['checks'] if c['key'] == 'professional_workflow')
    assert '专业分项待补全' in check['detail']
