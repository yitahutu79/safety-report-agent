from safety_report.agent_graph import run_chapter_graph, budget_groups
from safety_report.node_checkpoint import NodeCheckpoint


def test_repair_only_failed_unit_and_cache_unchanged_review(tmp_path):
    writes=[]; reviews=[]
    evidence=[{'id':'e1','text':'有储罐。','source':'test','locator':'1'}]
    def complete(system,payload,model,**kw):
        assert '资料规划 Agent' not in system and '资料筛选 Agent' not in system
        if '安全生产报告的审稿人员' in system:
            h=payload['guidelines'][0];reviews.append(h)
            return {'issues':[dict(target_id='p:0',draft_quote='储罐资料说明。1',evidence_id='e1',evidence_quote='有储罐。',category='factual',expected_text='',reason='测试可定位意见',suggestion='更正')] if h=='2.2 设备' and reviews.count(h)==1 else []}
        if '审稿意见复核员' in system:
            return {'decisions':[{'id':'f0','decision':'confirm','reason':'测试定位返修路由'}]}
        h=payload['target_subsections'][0];writes.append(h)
        return {'paragraphs':[{'heading':h,'text':'储罐资料说明。'+str(writes.count(h)),'evidence_ids':['e1']}],
                'tables':[], 'missing':[], 'review':[]}
    cp=NodeCheckpoint(tmp_path/'nodes.json',{'model':'test'})
    result=run_chapter_graph('写作',{'chapter':'2 概况','required_subsections':['2.1 工艺','2.2 设备'],'evidence':evidence},
        {'api_key':'SECRET'}, search=lambda q:[],validate=lambda d:[],complete=complete,checkpoint=cp)
    assert writes==['2.1 工艺','2.2 设备','2.2 设备']
    assert reviews==['2.1 工艺','2.2 设备','2.2 设备']
    assert len(result['paragraphs'])==2
    metrics=(tmp_path/'generation-metrics.jsonl').read_text()
    assert 'SECRET' not in metrics and '储罐' not in metrics
    assert 'elapsed_seconds' in metrics and 'cache_hit' in metrics


def test_short_sibling_titles_share_call_but_large_evidence_splits():
    headings=['2.1 单位','2.1.1 地址']
    assert budget_groups(headings,[],True)==[headings]
    assert budget_groups(headings,[{'text':'单位地址'*1000}],True)==[[headings[0]],[headings[1]]]


def test_source_tail_and_failed_review_survive_retry(tmp_path):
    cp=NodeCheckpoint(tmp_path/'nodes.json',{})
    evidence=[{'id':'e1','text':'工艺资料。'*300+'仅为拟建设施，尚未实施。','source':'test','locator':'1'}]
    writes=[];reviews=[]
    def complete(system,payload,model,**kw):
        if '安全生产报告的审稿人员' in system:
            reviews.append(1)
            assert payload['evidence'][0]['text'].endswith('尚未实施。')
            if len(reviews)==1: raise ValueError('测试网络失败')
            return {'issues':[]}
        writes.append(1)
        assert payload['evidence'][0]['text'].endswith('尚未实施。')
        return {'paragraphs':[{'heading':'2.1 工艺','text':'待建设','evidence_ids':['e1']}], 'tables':[], 'missing':[], 'review':[]}
    args=dict(system='写作',payload={'chapter':'2 概况','required_subsections':['2.1 工艺'],'evidence':evidence},model={},
        search=lambda q:[],validate=lambda d:[],complete=complete,checkpoint=cp)
    import pytest
    with pytest.raises(ValueError,match='网络失败'): run_chapter_graph(**args)
    run_chapter_graph(**args)
    assert len(writes)==1 and len(reviews)==2


def test_local_writer_uses_native_schema_without_changing_other_calls():
    from unittest.mock import patch
    from safety_report.provider import complete_json
    config={'provider':'ollama','base_url':'http://127.0.0.1:11434/v1','model':'qwen3.5:4b'}
    response={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
    with patch('safety_report.provider.request_json',return_value=response) as req:
        complete_json('write',{'target_subsections':['2.1 单位'],'evidence':[{'id':'e1'}]},config)
        fmt=req.call_args.args[2]['response_format']
        assert fmt['type']=='json_schema'
        assert fmt['json_schema']['schema']['properties']['missing']['items']['type']=='string'
        assert fmt['json_schema']['schema']['properties']['paragraphs']['items']['properties']['evidence_ids']['items']['enum']==['e1']
        complete_json('test',{},config)
        assert req.call_args.args[2]['response_format']['type']=='json_object'
