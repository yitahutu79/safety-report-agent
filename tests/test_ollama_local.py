from unittest.mock import patch
from safety_report.provider import complete_json


def test_local_qwen_disables_thinking_for_structured_output_only():
    config = {'provider':'ollama','base_url':'http://127.0.0.1:11434/v1','model':'qwen3.5:4b','api_key':'','json_mode':True}
    response = {'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
    with patch('safety_report.provider.request_json', return_value=response) as request:
        assert complete_json('test', {}, config) == {'ok': True}
        assert request.call_args.args[2]['reasoning_effort'] == 'none'
    config['model'] = 'other:4b'
    with patch('safety_report.provider.request_json', return_value=response) as request:
        complete_json('test', {}, config)
        assert 'reasoning_effort' not in request.call_args.args[2]


def test_local_structured_review_notes_preserve_fields_without_bypassing_validation():
    from safety_report.agent_graph import normalize_local_review_lists
    config = {'provider':'ollama','base_url':'http://127.0.0.1:11434/v1','model':'qwen3.5:4b'}
    draft = {'missing':[{'item':'缺少参数','impact':'需要补充'}, {'item':['无效值']}], 'review':[{'id':'e1','task':'核对来源'}]}
    result = normalize_local_review_lists(draft, config)
    assert result['missing'][0] == 'item：缺少参数；impact：需要补充'
    assert isinstance(result['missing'][1], dict)
    assert result['review'][0] == 'id：e1；task：核对来源'
    assert normalize_local_review_lists(draft, {'provider':'deepseek'}) == draft
