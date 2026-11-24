import pytest

from safety_report import provider
from safety_report.gptr_reviewer import ReviewerAgent, ground_findings, review_targets

DRAFT={'paragraphs':[{'text':'项目投资200万元。许可项目经批准后开展。','evidence_ids':['e1']}],'tables':[]}
EVIDENCE=[{'id':'e1','text':'项目投资100万元。许可项目经批准后开展。'}]
def finding(**kw):
    return dict(dict(target_id='p:0',draft_quote='项目投资200万元。',evidence_id='e1',evidence_quote='项目投资100万元。',category='factual',expected_text='',reason='投资数值不同',suggestion='核实并改为来源数值'),**kw)
def run(issues,decisions):
    calls=[]
    def complete(system,payload,model,**kw):
        calls.append(payload)
        return {'issues':issues} if len(calls)==1 else {'decisions':decisions}
    result=ReviewerAgent(complete).run({'task':{},'draft':DRAFT,'evidence':EVIDENCE,'model':{}})
    return result,calls

def test_fabricated_quote_and_unknown_source_do_not_trigger_repair():
    for f in [finding(draft_quote='虚构正文'),finding(evidence_id='missing'),finding(evidence_quote='虚构证据'),'无依据的自由文本']:
        r,calls=run([f],[])
        assert not r['review'] and r['review_notes'] and len(calls)==1

def test_existing_condition_is_not_missing():
    r,calls=run([finding(category='omission',expected_text='经批准后开展',evidence_quote='许可项目经批准后开展。')],[])
    assert not r['review'] and len(calls)==1
    assert '已存在' in r['review_records'][0]['reason']

def test_real_quotes_still_need_independent_confirmation():
    for decision in ('reject','manual'):
        r,calls=run([finding()],[{'id':'f0','decision':decision,'reason':'需核对上下文'}])
        assert not r['review'] and len(calls)==2
    r,_=run([finding()],[{'id':'f0','decision':'confirm','reason':'同一投资字段数值冲突'}])
    assert len(r['review'])==1 and '200万元' in r['review'][0] and '100万元' in r['review'][0]

def test_invalid_duplicate_or_missing_decision_is_manual():
    for ds in [[{'id':'f0','decision':'confirm','reason':123}],[],[{'id':'other','decision':'confirm','reason':'错ID'}],[{'id':'f0','decision':'confirm','reason':'重复'}]*2]:
        r,_=run([finding()],ds)
        assert not r['review'] and r['review_notes']

def test_style_is_advice_and_table_quotes_require_exact_cell():
    r,calls=run([finding(category='style')],[])
    assert not r['review'] and r['review_notes'] and len(calls)==1
    t=review_targets({'tables':[{'rows':[['100万元','拟建']],'evidence_ids':['e1']}]})
    ok,bad=ground_findings([finding(target_id='t:0:0:0',draft_quote='100万元')],t,EVIDENCE)
    assert ok and not bad
    ok,bad=ground_findings([finding(target_id='t:0:0:1',draft_quote='100万元')],t,EVIDENCE)
    assert bad and not ok


def test_malformed_provider_json_retries_with_complete_targets_and_evidence(monkeypatch):
    import json

    model = {'provider': 'qwen', 'model': 'mock-review', 'base_url': 'https://example.com/v1'}
    requests = []

    def request_json(config, suffix, body, **kwargs):
        requests.append(body)
        content = '{"issues": [' if len(requests) == 1 else '{"issues": []}'
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}

    monkeypatch.setattr(provider, 'request_json', request_json)
    result = ReviewerAgent(provider.complete_json).run({'task': {}, 'draft': DRAFT, 'evidence': EVIDENCE, 'model': model})

    assert result['review'] == []
    assert len(requests) == 2
    first, retry = [json.loads(body['messages'][1]['content']) for body in requests]
    assert first['targets'] == retry['targets']
    assert first['evidence'] == retry['evidence'] == EVIDENCE
    assert 'draft' in first and 'draft' not in retry
    assert '上次输出无法解析' in requests[1]['messages'][0]['content']


def test_invalid_review_shape_retries_once_and_does_not_pass():
    calls = []

    def complete(prompt, payload, model, **kwargs):
        calls.append(payload)
        return {'unexpected': []}

    with pytest.raises(ValueError, match='审稿结果格式异常，自动重试后仍失败'):
        ReviewerAgent(complete).run({'task': {}, 'draft': DRAFT, 'evidence': EVIDENCE, 'model': {}})
    assert len(calls) == 2
