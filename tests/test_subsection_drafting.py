import pytest
from safety_report.agent_graph import group_subsections, run_chapter_graph
from safety_report.node_checkpoint import NodeCheckpoint
from safety_report.gptr_bm25 import rank_written_sections


def test_group_respects_parent_order_and_size():
    headings=['2.1 项目','2.1.1 单位','2.1.2 规模','2.1.3 地点','2.2 工艺','2.2.1 设备']
    assert group_subsections(headings)==[headings[:3],headings[3:4],headings[4:]]


def test_resume_incomplete_second_subsection_without_rewriting_first(tmp_path):
    calls=[]; failures=[2]
    evidence=[{'id':'e1','source':'模拟文件','locator':'1','text':'车间采用机械通风。'}, {'id':'e2','source':'模拟文件','locator':'2','text':'车间使用水性清洗剂。'}]
    def complete(system,payload,model,**kw):
        if '资料规划 Agent' in system: return {'queries':[]}
        if '资料筛选 Agent' in system: return {'sources':[{'id':x['id'],'decision':'use','reason':'相关'} for x in payload['sources']]}
        if '安全生产报告的审稿人员' in system:return {'issues':[]}
        group=payload['target_subsections'];calls.append(group[0])
        if group[0]=='2.2 工艺' and failures[0]:
            failures[0]-=1;raise ValueError('模拟截断')
        return {'editorial_plan':[], 'paragraphs':[{'heading':group[0],'text':'仅根据虚构证据编写。','evidence_ids':['e1']}], 'tables':[], 'missing':[], 'review':[]}
    args=dict(system='写作要求',payload={'chapter':'2 项目概况','required_subsections':['2.1 通风','2.2 工艺'],'evidence':evidence},model={},search=lambda q:[],validate=lambda d:[],complete=complete)
    path=tmp_path/'cache.json'
    with pytest.raises(ValueError,match='模拟截断'):
        run_chapter_graph(**args,checkpoint=NodeCheckpoint(path,{'project':'x'}))
    progress=[]
    result=run_chapter_graph(**args,checkpoint=NodeCheckpoint(path,{'project':'x'}),on_progress=progress.append)
    assert calls==['2.1 通风','2.2 工艺','2.2 工艺','2.2 工艺']
    assert [p['heading'] for p in result['paragraphs']]==['2.1 通风','2.2 工艺']
    assert any('已恢复小节 1/2' in msg for msg in progress)


def test_written_context_reuses_gptr_chinese_bm25():
    sections=[{'section_title':'消防水系统','written_content':'消防水泵设置在泵房。'}, {'section_title':'车间通风','written_content':'车间设置机械通风。'}]
    matches=rank_written_sections('机械通风车间',sections)
    assert matches and '通风' in matches[0]


def test_design_basis_rules_reach_writer_and_preserve_file_entries():
    from safety_report.pipeline import SYSTEM, load_chapter_skill
    from safety_report.writing_style import writing_guidance

    filing = '1.1建设项目的批复（核准、备案）文件'
    contract = '1.4设计合同'
    other = '1.5项目的其他相关文件'
    evidence = [{'id': 'e1', 'source': '备案证明.pdf', 'locator': 'page[1]',
                 'text': '建设项目备案证明，项目代码 TEST-001。'},
                {'id': 'e2', 'source': '工艺流程图.pdf', 'locator': 'page[1]',
                 'text': '设计资料：工艺流程图，图号 GY-01。'}]
    entries = {filing: ('（1）建设项目备案证明（项目代码 TEST-001）。', 'e1'),
               other: ('（1）工艺流程图（图号 GY-01）。', 'e2')}
    writer_prompts = []

    def complete(system, payload, model, **kwargs):
        if '资料筛选 Agent' in system:
            return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '相关'}
                                for item in payload['sources']]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        writer_prompts.append(system)
        heading = payload['target_subsections'][0]
        if heading == contract:
            return {'paragraphs': [], 'tables': [], 'missing': ['需提供设计合同'], 'review': []}
        text, ident = entries[heading]
        return {'paragraphs': [{'heading': heading, 'text': text, 'evidence_ids': [ident]}],
                'tables': [], 'missing': [], 'review': []}

    system = SYSTEM + '\n' + load_chapter_skill('1') + '\n' + writing_guidance('facility_design')
    result = run_chapter_graph(system, {'chapter': '1 设计依据',
        'required_subsections': [filing, contract, other], 'evidence': evidence}, {},
        search=lambda query: [], validate=lambda draft: [], complete=complete)

    assert len(writer_prompts) == 3
    for prompt in writer_prompts:
        assert '逐项列举' in prompt
        assert '合同小节须有合同材料' in prompt
        assert '投资、产能' in prompt
    assert [(p['heading'], p['text'], p['evidence_ids']) for p in result['paragraphs']] == [
        (heading, text, [ident]) for heading, (text, ident) in entries.items()]
    assert '需提供设计合同' in result['missing']


def test_basis_file_lists_retain_sources_when_one_report_dominates_retrieval():
    from unittest.mock import Mock, patch
    from safety_report import pipeline

    filing = '1.1建设项目的批复（核准、备案）文件'
    other = '1.5项目的其他相关文件'
    chunks = [{'id': f'report-{i}', 'source': '综合分析报告.docx', 'locator': str(i),
               'text': '项目的其他相关文件及建设项目批复情况。'} for i in range(24)]
    filenames = ['营业执照.pdf', '备案证明.pdf', '租赁合同.pdf', '工艺图.pdf', '总图.pdf', '消防图.pdf', '电气图.pdf']
    chunks += [{'id': f'file-{i}', 'source': name, 'locator': 'page[1]',
                'text': '企业提供的项目文件。'} for i, name in enumerate(filenames)]
    index = Mock(client=None, semantic_error='')
    index.search.side_effect = lambda query, limit=10: chunks[:limit]
    received = {}

    def complete(system, payload, model, **kwargs):
        if '资料筛选 Agent' in system:
            return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '相关'}
                                for item in payload['sources']]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        heading = payload['target_subsections'][0]
        received[heading] = payload['evidence']
        item = next(item for item in payload['evidence'] if item['source'] == '营业执照.pdf')
        return {'paragraphs': [{'heading': heading, 'text': '（1）营业执照。', 'evidence_ids': [item['id']]}],
                'tables': [], 'missing': [], 'review': []}

    profile = {'sha256': 'template', 'report_type': 'facility_design', 'headings': [
        {'text': '1 设计依据', 'level': 1}, {'text': filing, 'level': 2}, {'text': other, 'level': 2}]}
    with patch.object(pipeline, 'HybridEvidenceIndex', return_value=index), patch.object(pipeline, 'complete_json', side_effect=complete):
        result = pipeline.generate(profile, {'chunks': chunks}, [], True, model={'name': '模拟模型'}, chapter_ids=['1'])

    assert result['generation_errors'] == []
    for heading in (filing, other):
        assert {item['source'] for item in received[heading]} == {'综合分析报告.docx', *filenames}
        assert len({item['source'] for item in received[heading]}) == 8


def test_subsection_rejects_unknown_evidence_and_never_persists_invalid_output(tmp_path):
    evidence=[{'id':'e1','source':'模拟','locator':'1','text':'机械通风'}]
    calls=[]
    def complete(system,payload,model,**kw):
        if '资料规划 Agent' in system:return {'queries':[]}
        if '资料筛选 Agent' in system:return {'sources':[{'id':'e1','decision':'use','reason':'相关'}]}
        calls.append('draft')
        return {'paragraphs':[{'heading':payload['target_subsections'][0], 'text':'不应保存', 'evidence_ids':['unknown']}], 'tables':[], 'missing':[], 'review':[]}
    path=tmp_path/'nodes.json'
    with pytest.raises(ValueError, match='未提供的证据'):
        run_chapter_graph('写作',{'chapter':'2 概况','required_subsections':['2.1 通风','2.2 工艺'],'evidence':evidence},{},search=lambda q:[],validate=lambda d:[],complete=complete,checkpoint=NodeCheckpoint(path,{}))
    assert calls==['draft','draft']
    assert '不应保存' not in path.read_text()


def test_missing_basis_retries_without_placeholder_and_continues_later_subsections():
    from safety_report.pipeline import SYSTEM, validate_section

    laws = '1.2国家有关法律法规'
    other = '1.5项目的其他相关文件'
    evidence = [{'id': 'e1', 'source': '工艺图.pdf', 'locator': 'page[1]', 'text': '工艺图 GY-01'}]
    calls = []

    def complete(system, payload, model, **kwargs):
        if '资料筛选 Agent' in system:
            return {'sources': [{'id': 'e1', 'decision': 'use', 'reason': '相关'}]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        heading = payload['target_subsections'][0]
        calls.append(heading)
        if heading == laws:
            if calls.count(laws) == 1:
                return {'paragraphs': [{'heading': laws, 'text': '暂无可用法规资料', 'evidence_ids': []}],
                        'tables': [], 'missing': [], 'review': []}
            assert '本次允许引用的 evidence_ids' in system
            assert 'e1' in system
            assert 'paragraphs=[]、tables=[]' in system
            return {'paragraphs': [], 'tables': [], 'missing': ['需提供本项目适用的法律法规依据'], 'review': []}
        return {'paragraphs': [{'heading': other, 'text': '（1）工艺图 GY-01。', 'evidence_ids': ['e1']}],
                'tables': [], 'missing': [], 'review': []}

    def validate(draft):
        validate_section(draft, evidence)
        return []

    result = run_chapter_graph(SYSTEM, {'chapter': '1 设计依据',
        'required_subsections': [laws, other], 'evidence': evidence}, {},
        search=lambda query: [], validate=validate, complete=complete)

    assert calls == [laws, laws, other]
    assert [item['heading'] for item in result['paragraphs']] == [other]
    assert result['missing'] == ['需提供本项目适用的法律法规依据']


@pytest.mark.parametrize(('returned_heading', 'allowed'), [
    ('１．５ 项目的其他相关文件：', True),
    ('1.1 建设项目的批复（核准、备案）文件', False),
    ('1.51 项目的其他相关文件', False),
    ('1.5 设计依据', False),
])
def test_subsection_matches_only_cosmetic_heading_variants(returned_heading, allowed):
    filing = '1.1建设项目的批复（核准、备案）文件'
    other = '1.5项目的其他相关文件'
    evidence = [{'id': 'e1', 'source': '模拟文件', 'locator': '1', 'text': '项目技术资料'}]
    drafts = []
    checked_headings = []

    def complete(system, payload, model, **kwargs):
        if '资料规划 Agent' in system:
            return {'queries': []}
        if '资料筛选 Agent' in system:
            return {'sources': [{'id': 'e1', 'decision': 'use', 'reason': '相关'}]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        target = payload['target_subsections'][0]
        drafts.append(target)
        heading = returned_heading if target == other else '1.1 建设项目的批复(核准,备案)文件'
        paragraph = {'heading': heading, 'text': '相关资料见原件。', 'evidence_ids': ['e1']}
        return {'paragraphs': [paragraph], 'tables': [dict(paragraph)], 'missing': [], 'review': []}

    def validate(draft):
        checked_headings.extend(item['heading'] for item in draft['paragraphs'] + draft['tables'])
        return []

    args = dict(system='写作', payload={'chapter': '1 设计依据', 'required_subsections': [filing, other],
                'evidence': evidence}, model={}, search=lambda q: [], validate=validate, complete=complete)
    if allowed:
        result = run_chapter_graph(**args)
        assert [item['heading'] for item in result['paragraphs']] == [filing, other]
        assert [item['heading'] for item in result['tables']] == [filing, other]
        assert set(checked_headings) == {filing, other}
        assert drafts == [filing, other]
    else:
        with pytest.raises(ValueError, match='返回了范围外的标题'):
            run_chapter_graph(**args)
        assert drafts == [filing, other, other]
