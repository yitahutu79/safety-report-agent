import unittest

from safety_report.agent_graph import run_chapter_graph


class ChapterAgentGraphTests(unittest.TestCase):
    def test_planner_query_routes_to_project_evidence_search(self):
        calls = []
        evidence = {'id': 'e-flow', 'text': '工艺流程：原料接收、反应、储存。',
                    'source': '工艺说明.docx', 'locator': '第2页'}

        def complete(system, payload, model, **kwargs):
            calls.append((system, payload))
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
                         ['资料规划 Agent', '证据检索工具', '报告撰写 Agent', '质量审核 Agent'])

    def test_quality_gate_routes_one_targeted_repair(self):
        writes = []
        draft_outputs = [
            {'paragraphs': [], 'tables': [], 'missing': [], 'review': []},
            {'paragraphs': [{'heading': '1 项目工艺', 'text': '已依据流程证据组织说明。',
                             'evidence_ids': ['e1']}], 'tables': [], 'missing': [], 'review': []},
        ]

        def complete(system, payload, model, **kwargs):
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


if __name__ == '__main__':
    unittest.main()
