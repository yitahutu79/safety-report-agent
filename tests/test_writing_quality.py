from unittest.mock import patch
from safety_report.provider import complete_json
from safety_report.pipeline import readability_issues
from safety_report.writing_style import unit_writing_guidance


def test_similarity_does_not_force_rewording_of_facts_but_verbatim_still_blocks():
    source='企业资料中的名称日期地址及许可业务应准确保留，不得为改写而改变事实。'*5
    evidence=[{'id':'e1','text':source}]
    d={'paragraphs':[{'text':source,'evidence_ids':['e1']}]}
    assert readability_issues(d,evidence)
    d['paragraphs'][0]['text']='建设单位情况如下。'+source+'经营条件仍需核实。'
    assert readability_issues(d,evidence)  # Prefix/suffix must not hide copying.
    d['paragraphs'][0]['text']=source.replace('不得', '不应')
    assert not readability_issues(d,evidence)
    assert readability_issues(d,evidence,include_similarity_advice=True)
    d['paragraphs'][0]['text']='资料摘录：'+source
    assert readability_issues(d,evidence)


def test_deepseek_writer_reserves_output_for_prose_and_does_not_retry_same_mode():
    response={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
    for model in ('deepseek-flash','deepseek-v4-pro'):
        with patch('safety_report.provider.request_json',return_value=response) as req:
            complete_json('write',{'target_subsections':['2.1 建设单位']},{'base_url':'https://api.deepseek.com','model':model})
            assert req.call_args.args[2]['thinking']=={'type':'disabled'}
            assert 'reasoning_effort' not in req.call_args.args[2]
    brief=unit_writing_guidance(['建设单位概况','项目建设内容'])
    assert '许可' in brief and '原计划日期' in brief and '不抄列完整工商经营范围' in brief


def test_stitching_multiple_long_sources_is_not_original_writing():
    a=''.join(chr(0x4e00+i) for i in range(110))
    b=''.join(chr(0x5200+i) for i in range(110))
    evidence=[{'id':'a','text':a},{'id':'b','text':b}]
    draft={'paragraphs':[{'text':a[:100]+'。另据资料，'+b[:100],'evidence_ids':['a','b']}]}
    assert any('多个来源' in issue for issue in readability_issues(draft,evidence))
    draft['paragraphs'][0]['text']='涉及对象应按实际成分和用途复核，不能只依据商品名称确定分类。'
    assert not readability_issues(draft,evidence)
    assert '来源报告' in unit_writing_guidance(['危险物料辨识'])


def test_deepseek_review_uses_visible_output_budget():
    response={'choices':[{'finish_reason':'stop','message':{'content':'{"issues":[]}'}}]}
    with patch('safety_report.provider.request_json',return_value=response) as req:
        complete_json('review',{'task_type':'evidence_review'},{'base_url':'https://api.deepseek.com','model':'deepseek-v4-pro'},max_tokens=1800)
        assert req.call_count==1
        assert req.call_args.args[2]['thinking']=={'type':'disabled'}


def test_report_register_flags_editorial_padding_not_technical_conditions():
    from safety_report.writing_style import style_warnings, writing_guidance, chapter_writing_guidance
    assert style_warnings({'paragraphs':[{'text':'上述信息用于界定本次设计所属项目，不替代备案文件的审查结论。'}]})
    assert not style_warnings({'paragraphs':[{'text':'本次设计范围为一期工程，二期工程不在本次设计范围内。计算结果仅适用于已列明的储量及工况。'}]})
    assert 'missing' in unit_writing_guidance(['1.5 项目的其他相关文件'])
    assert '项目代码不能写成批复文号' in unit_writing_guidance(['1.1 备案文件'])
    assert '单项直接列文件名称和编号' in chapter_writing_guidance('1 设计依据')
    assert '安全设施设计' in writing_guidance('facility_design')
