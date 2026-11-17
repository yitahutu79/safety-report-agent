from datetime import date
from pathlib import Path

import pytest

from safety_report.calculations import calculate_distance_margin
from safety_report.professional_workflow import ProfessionalLedger
from safety_report.quality import review_report


def test_distance_calculation_keeps_input_sources_and_does_not_decide_compliance():
    actual = {'value': '10.125', 'source_file': '总图.pdf', 'source_locator': '图 1'}
    reference = {'value': '12.5', 'source_file': '人工核验标准', 'source_locator': '条款 1'}
    result = calculate_distance_margin(actual, reference)
    assert result['result'] == '-2.375' and result['result_unit'] == 'm'
    assert [row['source_file'] for row in result['inputs']] == ['总图.pdf', '人工核验标准']
    assert '不判断合规性' in result['assumptions']
    with pytest.raises(ValueError, match='来源'):
        calculate_distance_margin({**actual, 'source_locator': ''}, reference)


def regulation_payload(decision='适用', validity='现行', checked_date=None):
    return {'kind': 'regulatory', 'title': '测试标准', 'content': '人工核对的适用性记录',
            'source_file': '标准文本', 'source_locator': '条款 1', 'status': 'reviewed', 'reviewer': '审核人',
            'details': {'rule': 'GB 12345-2020 条款 1', 'decision': decision, 'scope_reason': '按项目对象与范围核对',
                        'validity': validity, 'checked_date': checked_date or date.today().isoformat(),
                        'official_source': 'https://example.org/standard'}}


@pytest.mark.parametrize('kind', ['facility_design', 'pre_evaluation', 'acceptance_evaluation', 'emergency_plan'])
def test_project_applicability_records_include_project_decision_and_date(kind, tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', kind)
    item = ledger.save(regulation_payload())
    evidence = ledger.report_evidence()[0]
    assert evidence['report_section'] == '1'
    assert evidence['evidence_type'] == 'regulatory_applicability'
    assert evidence['project_applicability'] == '适用' and evidence['rule_validity_status'] == '现行'
    assert evidence['id'].endswith('-r1') and item['details']['official_source']


@pytest.mark.parametrize('decision,validity', [('待确认', '现行'), ('适用', '已废止'), ('不适用', '现行')])
def test_uncertain_or_inapplicable_regulation_does_not_satisfy_citation_check(tmp_path, decision, validity):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'pre_evaluation')
    ledger.save(regulation_payload(decision, validity))
    e = ledger.report_evidence()[0]
    report = {'report_type': 'pre_evaluation', 'sections': [{'id': '1', 'title': '1 依据',
        'paragraphs': [{'text': '按照 GB 12345-2020 编制。', 'evidence_ids': [e['id']]}],
        'tables': [], 'missing': [], 'review': []}], 'evidence': [e]}
    checks = {c['key']: c for c in review_report(report, {'fields': [], 'files': []}, professional_records=ledger.list())['checks']}
    assert checks['regulation_validity']['status'] != 'pass'


def test_regulatory_review_requires_parseable_nonfuture_check_date(tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'facility_design')
    with pytest.raises(ValueError, match='YYYY-MM-DD'):
        ledger.save(regulation_payload(checked_date='不是日期'))
    with pytest.raises(ValueError, match='不能晚于今天'):
        ledger.save(regulation_payload(checked_date='2999-01-01'))


def test_cited_standard_needs_a_project_specific_applicability_record(tmp_path):
    ledger = ProfessionalLedger(tmp_path / 'professional.json', 'facility_design')
    ledger.save(regulation_payload())
    report = {'report_type': 'facility_design', 'sections': [{'id': '1', 'title': '1 依据',
        'paragraphs': [{'text': '采用 GB 12345-2020。', 'evidence_ids': []}], 'tables': []}], 'evidence': []}
    state = {'fields': [], 'files': []}
    checks = {c['key']: c for c in review_report(report, state)['checks']}
    assert checks['regulation_applicability']['status'] == 'warning'
    checks = {c['key']: c for c in review_report(report, state, professional_records=ledger.list())['checks']}
    assert checks['regulation_applicability']['status'] == 'pass'
    report['sections'][0]['paragraphs'][0]['text'] = '采用 GB 54321-2020。'
    checks = {c['key']: c for c in review_report(report, state, professional_records=ledger.list())['checks']}
    assert checks['regulation_applicability']['status'] == 'warning'


def test_project_api_exposes_regulatory_review_and_distance_calculator(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from safety_report import server

    monkeypatch.setattr(server, 'DATA', tmp_path)
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{http.server_port}'
    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data), timeout=5) as response:
            return json.load(response)
    try:
        project = request('/api/projects', {'name': '隔离测试', 'report_type': 'facility_design'})
        route = '/api/projects/' + project['id']
        schema = request(route + '/professional')
        assert 'regulatory' in schema['kinds'] and 'regulatory' in schema['schemas']
        record = request(route + '/professional', regulation_payload())['item']
        assert record['details']['decision'] == '适用'
        result = request(route + '/calculations', {'operation': 'compare_distance', 'name': '测试对象',
            'actual': {'value': '15', 'source_file': '总图', 'source_locator': '第1页'},
            'reference': {'value': '10', 'source_file': '参考文件', 'source_locator': '第2页'}})
        assert result['calculation']['result'] == '5' and result['item']['status'] == 'draft'
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=5)
