from safety_report.writing_style import writing_guidance, style_warnings, basis_listing_issues, format_basis_entries
from safety_report.gptr_bm25 import bm25_scores
from safety_report.documents import EvidenceIndex, tokens


def test_report_specific_guidance_preserves_phase_and_facts():
    expected = {'facility_design':'设计方案', 'pre_evaluation':'拟建',
                'acceptance_evaluation':'现场核查', 'emergency_plan':'应急资源'}
    for kind, phrase in expected.items():
        prompt = writing_guidance(kind)
        assert phrase in prompt
        assert '数量、单位、条件、否定、例外' in prompt
        assert '不能凭风格模板补造事实' in prompt


def test_style_check_is_review_only_and_does_not_modify_text():
    section = {'paragraphs':[{'text':'该方案绝对安全。'}, {'text':'相关措施拟在储罐区设置。'}]}
    assert style_warnings(section) == ['第1段含绝对安全表述，请核实其语境、依据并修改']
    assert section['paragraphs'][0]['text'] == '该方案绝对安全。'


def test_gptr_bm25_ranks_chinese_and_never_adds_unrelated_evidence():
    passages = ['储罐区设置可燃气体报警装置', '厂房消防用水量和消防水池', '办公室人员培训记录']
    scores = bm25_scores(tokens('储罐气体报警'), [tokens(s) for s in passages])
    assert scores[0] > scores[1] == scores[2] == 0
    chunks = [{'id':str(i), 'text':text} for i,text in enumerate(passages)]
    assert EvidenceIndex(chunks).search('完全无关甲乙丙丁', 5) == []
    assert EvidenceIndex(chunks).search('储罐气体报警', 5)[0]['id'] == '0'


def test_basis_lists_reject_extra_fields_without_affecting_other_chapters():
    section = {'paragraphs': [
        {'heading': '1.1建设项目的批复文件', 'text': '营业执照，法定代表人张某，注册资本100万元。'},
        {'heading': '1.5项目的其他相关文件', 'text': '图纸，证书编号ABC，设计阶段初步设计。'}]}
    assert len(basis_listing_issues(section, '1 设计依据')) == 2
    assert basis_listing_issues(section, '2 建设项目概况') == []
    section['paragraphs'][0]['human_edited'] = True
    assert len(basis_listing_issues(section, '1 设计依据')) == 1
    concise = {'paragraphs': [
        {'heading': '1.1建设项目的批复文件', 'text': '（1）营业执照（统一社会信用代码：TEST）；'},
        {'heading': '1.5项目的其他相关文件', 'text': '（1）设计单位提供的设计资料（工艺、设备布置、消防、电气）。'}]}
    assert basis_listing_issues(concise, '1 设计依据') == []


def test_basis_entry_format_is_idempotent_and_keeps_evidence():
    section = {'paragraphs': [
        {'heading': '1.1批复文件', 'text': '（3）营业执照', 'evidence_ids': ['e1']},
        {'heading': '1.1批复文件', 'text': '（8）备案证明；', 'evidence_ids': ['e2']},
        {'heading': '1.5其他相关文件', 'text': '1）设计资料', 'evidence_ids': ['e3']}]}
    format_basis_entries(section, '1 设计依据')
    assert [p['text'] for p in section['paragraphs']] == ['（1）营业执照；', '（2）备案证明。', '（1）设计资料。']
    format_basis_entries(section, '1 设计依据')
    assert section['paragraphs'][1]['text'] == '（2）备案证明。'
    assert [p['evidence_ids'] for p in section['paragraphs']] == [['e1'], ['e2'], ['e3']]
    section['paragraphs'][0].update(text='手工保留内容', human_edited=True)
    format_basis_entries(section, '1 设计依据')
    assert section['paragraphs'][0]['text'] == '手工保留内容'
    multiline = {'paragraphs': [{'heading': '1.1批复文件', 'text': '（1）营业执照\n（2）备案证明', 'evidence_ids': ['e1', 'e2']}]}
    format_basis_entries(multiline, '1 设计依据')
    assert [p['text'] for p in multiline['paragraphs']] == ['（1）营业执照；', '（2）备案证明。']
    assert all(p['evidence_ids'] == ['e1', 'e2'] for p in multiline['paragraphs'])
