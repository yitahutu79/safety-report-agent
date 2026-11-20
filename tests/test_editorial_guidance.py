from safety_report.agent_graph import run_chapter_graph


def test_chapter_brief_reaches_writer_and_reviewer_without_extra_calls():
    calls = []
    evidence = {'id': 'e1', 'text': '装置采用间歇进料工艺。', 'source': '说明', 'locator': '1'}
    def complete(system, payload, model, **kwargs):
        calls.append((system, payload))
        if '资料规划 Agent' in system:
            return {'queries': ['工艺']}
        if '资料筛选 Agent' in system:
            return {'sources': [{'id': 'e1', 'decision': 'use', 'reason': '相关'}]}
        if '安全生产报告的审稿人员' in system:
            return {'issues': []}
        return {'paragraphs': [], 'tables': [], 'missing': ['待补分析依据'], 'review': []}
    result = run_chapter_graph('写作规则', {'chapter': '3 危险因素分析', 'evidence': [evidence], 'revision_instructions': '在正文说明待核条件'}, {},
                              complete=complete, search=lambda _: [], validate=lambda _: [])
    assert len(calls) == 4
    assert '发生环节' in calls[2][0] and '发生环节' in calls[3][1]['chapter_brief']
    assert 'draft_quote' in calls[3][0]
    assert result['missing'] == ['待补分析依据']
    assert calls[2][1]['evidence'][0]['id'] == 'e1'


def test_reviewer_receives_specific_writing_requirements():
    from safety_report.gptr_reviewer import ReviewerAgent
    seen=[]
    def complete(system,payload,model,**kwargs):
        seen.append(payload)
        return {'issues': []}
    ReviewerAgent(complete).run({'task':{'chapter':'项目概况','writing_requirements':'保留许可条件，表格四列'},'draft':{},'evidence':[],'model':{}})
    assert seen[0]['writing_requirements']=='保留许可条件，表格四列'
