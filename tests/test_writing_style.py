from safety_report.writing_style import writing_guidance, style_warnings
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
