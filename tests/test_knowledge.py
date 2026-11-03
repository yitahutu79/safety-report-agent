import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from safety_report.documents import EvidenceIndex
from safety_report.knowledge import KnowledgeBase


class FakeHybridIndex:
    def __init__(self, chunks, path, rebuild=False):
        self.index = EvidenceIndex(chunks)
        self.client = None

    def search(self, query, limit=10):
        return self.index.search(query, limit)

    def close(self):
        pass


def item(**overrides):
    return {'category': 'analysis_rule', 'title': '消防用水量核算原则',
            'content': '消防用水量应根据适用条件和经核实的设计参数计算。',
            'source': '企业审核规则 v1', 'source_url': '', 'applicability': '工业项目；适用性须按项目确认',
            'version': 'v1', 'effective_from': '', 'effective_to': '', **overrides}


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.kb = KnowledgeBase(root / 'kb.json', root / 'index')

    def tearDown(self):
        self.temp.cleanup()

    def test_only_approved_current_records_are_retrievable(self):
        record = self.kb.create(item())
        with patch('safety_report.knowledge.HybridEvidenceIndex', FakeHybridIndex):
            self.assertEqual(self.kb.search('消防用水'), [])
            self.kb.set_status(record['id'], 'approved', '安全工程师甲')
            results = self.kb.search('消防用水')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['corpus'], 'approved_knowledge')
            self.assertEqual(results[0]['reviewed_by'], '安全工程师甲')

    def test_editing_approved_record_creates_revision_and_resets_approval(self):
        record = self.kb.create(item())
        self.kb.set_status(record['id'], 'approved', '安全工程师甲')
        updated = self.kb.update(record['id'], item(content='修订后的规则内容。', version='v2'))
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['status'], 'draft')
        self.assertEqual(updated['history'][0]['status'], 'approved')
        with patch('safety_report.knowledge.HybridEvidenceIndex', FakeHybridIndex):
            self.assertEqual(self.kb.search('修订后的规则'), [])
        self.kb.set_status(record['id'], 'approved', '安全工程师乙')
        self.kb.set_status(record['id'], 'retired')
        with patch('safety_report.knowledge.HybridEvidenceIndex', FakeHybridIndex):
            self.assertEqual(self.kb.search('修订后的规则'), [])

    def test_approval_requires_a_named_reviewer_and_valid_dates(self):
        record = self.kb.create(item())
        with self.assertRaises(ValueError):
            self.kb.set_status(record['id'], 'approved')
        with self.assertRaises(ValueError):
            self.kb.create(item(effective_from='2026-10-01', effective_to='2026-01-01'))

    def test_regulation_must_be_marked_current_before_retrieval(self):
        record = self.kb.create(item(category='regulation', title='测试标准',
            content='经核验的测试条款。', validity_status='unknown'))
        self.kb.set_status(record['id'], 'approved', '审核人甲')
        with patch('safety_report.knowledge.HybridEvidenceIndex', FakeHybridIndex):
            self.assertEqual(self.kb.search('测试条款'), [])
            updated = self.kb.update(record['id'], item(category='regulation', title='测试标准',
                content='经核验的测试条款。', validity_status='current'))
            self.assertEqual(updated['status'], 'draft')
            self.kb.set_status(record['id'], 'approved', '审核人乙')
            self.assertEqual(len(self.kb.search('测试条款')), 1)


if __name__ == '__main__':
    unittest.main()
