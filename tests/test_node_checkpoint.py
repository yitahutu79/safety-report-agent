import threading
import pytest
from safety_report.agent_graph import run_chapter_graph
from safety_report.node_checkpoint import NodeCheckpoint


def test_resume_after_review_failure_without_repeating_completed_calls(tmp_path):
    calls = []
    evidence = {'id':'e1','text':'模拟证据','source':'模拟.txt','locator':'1'}
    def complete(system, payload, model, **kwargs):
        if '资料规划 Agent' in system:
            calls.append('plan'); return {'queries':['模拟']}
        if '资料筛选 Agent' in system:
            calls.append('curate'); return {'sources':[{'id':x['id'],'decision':'use','reason':'相关'} for x in payload['sources']]}
        if '安全生产报告的审稿人员' in system:
            calls.append('review')
            if calls.count('review') == 1: raise ValueError('模拟输出截断')
            return {'issues':[]}
        calls.append('draft'); return {'paragraphs':[{'text':'模拟正文','evidence_ids':['e1']}], 'tables':[], 'missing':[], 'review':[]}
    path = tmp_path/'nodes.json'
    arguments = dict(system='写作要求',payload={'chapter':'1 测试','evidence':[evidence]},model={},search=lambda q:[],validate=lambda x:[],complete=complete)
    with pytest.raises(ValueError, match='模型审稿节点失败'):
        run_chapter_graph(**arguments, checkpoint=NodeCheckpoint(path, {'revision':1}))
    assert calls == ['plan','curate','draft','review']
    progress=[]; restored=[]
    result=run_chapter_graph(**arguments, checkpoint=NodeCheckpoint(path, {'revision':1}), on_progress=progress.append, on_evidence=lambda x:restored.extend(x))
    assert calls == ['plan','curate','draft','review','review']
    assert restored[0]['id']=='e1'
    assert any('恢复完成的节点' in x for x in progress)
    assert result['paragraphs'][0]['text']=='模拟正文'
    assert not NodeCheckpoint(path, {'revision':2}).entries
    assert 'api_key' not in path.read_text()


def test_cancel_does_not_create_an_incomplete_node(tmp_path):
    stop=threading.Event(); stop.set(); checkpoint=NodeCheckpoint(tmp_path/'node.json',{})
    from safety_report.provider import GenerationCancelled
    with pytest.raises(GenerationCancelled):
        run_chapter_graph('s', {'chapter':'1 测试','evidence':[]}, {}, search=lambda q:[], validate=lambda d:[], cancel_event=stop, checkpoint=checkpoint)
    assert not checkpoint.path.exists()


def test_preflight_reuses_completed_chapter_and_invalidates_changed_model(tmp_path, monkeypatch):
    import json
    from safety_report import server
    target = tmp_path/'project'; target.mkdir()
    (target/'state.json').write_text(json.dumps({'id':'x','files':[],'fields':[], 'report_type':'facility_design'}))
    (target/'analysis.json').write_text(json.dumps({'chunks':[]}))
    profile=tmp_path/'profile.json'; profile.write_text('{}')
    monkeypatch.setattr(server, 'PROFILE', profile)
    monkeypatch.setattr(server.versions, 'load_report', lambda target: None)
    calls=[]
    def plan(target, chapter_id, model, event):
        calls.append(chapter_id)
        return {'chapter_id':chapter_id,'chapter':chapter_id,'requests':[],'can_draft_now':True}
    monkeypatch.setattr(server, 'chapter_materials_plan', plan)
    server.preflight_job(target,['1','2'],{'model':'a'},threading.Event())
    server.preflight_job(target,['1','2'],{'model':'a'},threading.Event())
    assert calls == ['1','2']
    server.preflight_job(target,['1'],{'model':'b'},threading.Event())
    assert calls == ['1','2','1']
