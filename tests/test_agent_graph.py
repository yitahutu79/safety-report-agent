import unittest

from safety_report.agent_graph import run_chapter_graph


class ChapterAgentGraphTests(unittest.TestCase):
    def test_planner_format_failure_falls_back_to_chapter_and_subsections(self):
        searched = []
        def complete(system, payload, model, **kwargs):
            if '资料筛选 Agent' in system:
                return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '与章节相关'} for item in payload['sources']]}
            if '安全生产报告的审稿人员' in system:
                return {'issues': []}
            if '资料规划 Agent' in system:
                raise ValueError('模型未返回有效 JSON')
            return {'paragraphs': [], 'tables': [], 'missing': ['需要补充数据'], 'review': []}
        result = run_chapter_graph(
            '写作规则', {'chapter': '3 危险分析', 'required_subsections': ['3.1 危险物料'], 'evidence': []},
            {'name': 'test'}, search=lambda query: (searched.append(query) or []),
            validate=lambda _: [], complete=complete)
        self.assertEqual(searched, ['3 危险分析', '3.1 危险物料'])
        self.assertIn('按章节标题和子节检索', result['agent_trace'][0]['status'])

    def test_planner_query_routes_to_project_evidence_search(self):
        calls = []
        evidence = {'id': 'e-flow', 'text': '工艺流程：原料接收、反应、储存。',
                    'source': '工艺说明.docx', 'locator': '第2页'}

        def complete(system, payload, model, **kwargs):
            calls.append((system, payload))
            if '资料筛选 Agent' in system:
                return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '与章节相关'} for item in payload['sources']]}
            if '安全生产报告的审稿人员' in system:
                return {'issues': []}
            if '资料规划 Agent' in system:
                return {'queries': ['工艺流程图']}
            return {'paragraphs': [{'heading': '1 项目工艺', 'text': '工艺包含原料接收、反应和储存环节。',
                                   'evidence_ids': ['e-flow']}],
                    'tables': [], 'missing': [], 'review': []}

        searched = []
        result = run_chapter_graph(
            '撰写规则', {'chapter': '1 项目工艺', 'required_subsections': [], 'evidence': []},
            {'name': 'test-model'}, search=lambda query: (searched.append(query) or [evidence]),
            validate=lambda draft: [], complete=complete)

        self.assertIn('工艺流程图', searched)
        self.assertEqual(result['paragraphs'][0]['evidence_ids'], ['e-flow'])
        self.assertEqual([row['agent'] for row in result['agent_trace']],
                         ['资料规划 Agent', '证据检索工具', '资料筛选 Agent', '报告撰写 Agent', '质量审核 Agent', '证据审稿 Agent'])

    def test_quality_gate_routes_one_targeted_repair(self):
        writes = []
        draft_outputs = [
            {'paragraphs': [], 'tables': [], 'missing': [], 'review': []},
            {'paragraphs': [{'heading': '1 项目工艺', 'text': '已依据流程证据组织说明。',
                             'evidence_ids': ['e1']}], 'tables': [], 'missing': [], 'review': []},
        ]

        def complete(system, payload, model, **kwargs):
            if '资料筛选 Agent' in system:
                return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '与章节相关'} for item in payload['sources']]}
            if '安全生产报告的审稿人员' in system:
                return {'issues': []}
            if '资料规划 Agent' in system:
                return {'queries': []}
            writes.append(system)
            return draft_outputs.pop(0)

        result = run_chapter_graph(
            '写作规则', {'chapter': '1 项目工艺', 'required_subsections': [], 'evidence': [
                {'id': 'e1', 'text': '流程说明', 'source': '流程.docx', 'locator': '第1页'}]},
            {'name': 'test-model'}, search=lambda _query: [],
            validate=lambda draft: ['正文为空'] if not draft['paragraphs'] else [], complete=complete)

        self.assertEqual(len(writes), 2)
        self.assertIn('审核 Agent 指出的质量问题', writes[1])
        self.assertTrue(any(row['status'] == '已完成一次定向返修' for row in result['agent_trace']))
        self.assertEqual(result['paragraphs'][0]['evidence_ids'], ['e1'])


    def test_model_review_sends_evidence_and_triggers_one_revision(self):
        calls = []
        evidence = {'id': 'e1', 'text': '工艺资料仅说明有储罐。', 'source': '合成资料.txt', 'locator': '第1段'}
        def complete(system, payload, model, **kwargs):
            if '资料规划 Agent' in system:
                return {'queries': []}
            if '资料筛选 Agent' in system:
                return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '与章节相关'} for item in payload['sources']]}
            if '安全生产报告的审稿人员' in system:
                calls.append(payload)
                return {'issues': ['没有证据证明已安装报警装置'] if len(calls) == 1 else []}
            if '审核 Agent 指出的质量问题' in system:
                return {'paragraphs': [{'text':'资料载明设置储罐。','evidence_ids':['e1']}], 'tables': [], 'missing':['报警设施情况待补充'], 'review': []}
            return {'paragraphs': [{'text':'储罐已安装报警装置。','evidence_ids':['e1']}], 'tables': [], 'missing': [], 'review': []}
        result = run_chapter_graph('写作规则', {'chapter':'1 工艺','evidence':[evidence]}, {},
            search=lambda q: [], validate=lambda draft: [], complete=complete)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['evidence'][0]['id'], 'e1')
        self.assertIn('报警装置', calls[1]['revision_notes'][0])
        self.assertIn('待补充', result['missing'][0])

    def test_invalid_model_review_does_not_pass(self):
        def complete(system, payload, model, **kwargs):
            if '资料规划 Agent' in system: return {'queries': []}
            if '资料筛选 Agent' in system:
                return {'sources': [{'id': item['id'], 'decision': 'use', 'reason': '与章节相关'} for item in payload['sources']]}
            if '安全生产报告的审稿人员' in system: return {'unexpected': True}
            return {'paragraphs': [], 'tables': [], 'missing': [], 'review': []}
        with self.assertRaisesRegex(ValueError, '审稿结果格式'):
            run_chapter_graph('写作规则', {'chapter':'测试','evidence':[]}, {},
                search=lambda q: [], validate=lambda draft: [], complete=complete)

if __name__ == '__main__':
    unittest.main()
