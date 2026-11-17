import pytest
from safety_report.gptr_curator import curate_sources
from safety_report.agent_graph import run_chapter_graph

EVIDENCE = [
    {'id': 'p', 'source': '合成项目.txt', 'locator': '第1段', 'corpus':'project_evidence', 'text':'拟设置储罐。'},
    {'id': 'k', 'source': '合成知识.txt', 'locator': '第2段', 'corpus':'approved_knowledge', 'text':'通用知识。'},
]


def test_curator_passes_bounded_evidence_and_validates_all_ids():
    def model(system, payload, model, **kwargs):
        assert [x['id'] for x in payload['sources']] == ['p', 'k']
        return {'sources':[{'id':'k','decision':'verify','reason':'需核验适用性'}, {'id':'p','decision':'use','reason':'项目依据'}]}
    rows = curate_sources('测试章节', EVIDENCE, {}, model)
    assert [x['id'] for x in rows] == ['p', 'k']
    assert rows[1]['decision'] == 'verify'


@pytest.mark.parametrize('rows', [
    [{'id':'invented','decision':'use','reason':'伪造'},{'id':'k','decision':'use','reason':'相关'}],
    [{'id':'p','decision':'use','reason':'相关'},{'id':'p','decision':'use','reason':'重复'}],
    [{'id':'p','decision':'use','reason':'遗漏另一条'}],
])
def test_curator_rejects_unknown_duplicate_and_missing_source(rows):
    with pytest.raises(ValueError):
        curate_sources('测试章节', EVIDENCE, {}, lambda *args, **kw: {'sources':rows})


def test_invalid_curation_falls_back_without_dropping_evidence():
    draft_inputs=[]
    def model(system, payload, config, **kwargs):
        if '资料规划 Agent' in system: return {'queries': []}
        if '资料筛选 Agent' in system: return {'sources': [{'id':'invented','decision':'use','reason':'无效'}]}
        if '安全生产报告的审稿人员' in system: return {'issues': []}
        draft_inputs.append(payload)
        return {'paragraphs': [{'text':'拟设置储罐。','evidence_ids':['p']}], 'tables': [], 'missing': [], 'review': []}
    result = run_chapter_graph('写作规则', {'chapter':'测试章节','evidence':EVIDENCE}, {},
                               search=lambda q: [], validate=lambda d: [], complete=model)
    assert {x['id'] for x in draft_inputs[0]['evidence']} == {'p','k'}
    assert draft_inputs[0]['source_review'] == []
    assert any('保留全部原证据' in x['status'] for x in result['agent_trace'])


def test_curator_results_flow_into_draft_and_review_export():
    from safety_report import versions
    written = []
    def model(system, payload, config, **kwargs):
        if '资料规划 Agent' in system:
            return {'queries': []}
        if '资料筛选 Agent' in system:
            return {'sources': [{'id':item['id'], 'decision':'verify' if item['id']=='k' else 'use',
                                 'reason':'需核对' if item['id']=='k' else '项目依据'} for item in payload['sources']]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        written.append(payload)
        return {'paragraphs':[{'text':'项目拟设置储罐。','evidence_ids':['p']}], 'tables':[], 'missing':[], 'review':[]}
    section = run_chapter_graph('写作规则', {'chapter':'1 项目概况','evidence':EVIDENCE}, {},
                                search=lambda q: [], validate=lambda d: [], complete=model)
    assert len(written[0]['source_review']) == 2
    section['title'] = '1 项目概况'
    report={'sections':[section], 'evidence': EVIDENCE}
    audit=versions.audit(report)
    assert audit['source_review'][0]['items'][1]['id'] == 'k'
    html=versions.review_html(report)
    assert '模型资料筛选记录' in html and '合成知识.txt 第2段' in html and '需核对' in html
