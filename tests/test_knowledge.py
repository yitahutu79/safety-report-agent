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


def test_approved_unknown_regulation_reports_exclusion_reason(tmp_path):
    kb=KnowledgeBase(tmp_path/'kb.json')
    record=kb.create(item(category='regulation',title='条文第一条',validity_status='unknown'))
    kb.set_status(record['id'],'approved','审核人')
    stored=kb.list()[0]
    eligible,reason=kb.retrieval_eligibility(stored)
    assert not eligible and '有效状态未知' in reason and '未纳入检索' in reason
    assert kb._approved_chunks()==[]
    revised=kb.update(record['id'],item(category='regulation',title='条文第一条',validity_status='current'))
    assert not kb.retrieval_eligibility(revised)[0]
    kb.set_status(record['id'],'approved','审核人')
    assert kb.retrieval_eligibility(kb.list()[0])[0] and len(kb._approved_chunks())==1


def test_reference_reading_unknown_regulation_keeps_report_filter_strict(tmp_path):
    kb=KnowledgeBase(tmp_path/'kb.json')
    r=kb.create(item(category='regulation',title='标准第一条',content='第一条说明制定目的。',validity_status='unknown'))
    kb.set_status(r['id'],'approved','审核人')
    with patch('safety_report.knowledge.HybridEvidenceIndex',FakeHybridIndex):
        assert kb.search('标准第一条')==[]
        found=kb.search('标准第一条',purpose='reference')
        assert found and found[0]['validity_status']=='unknown'
        assert kb.search('标准第一条')==[]
    assert kb.list()[0]['validity_status']=='unknown'


def test_single_approval_confirms_use_and_validity_without_second_setting(tmp_path):
    kb=KnowledgeBase(tmp_path/'kb.json');r=kb.create(item(category='regulation',validity_status='unknown'))
    approved=kb.set_status(r['id'],'approved','审核人',confirm_use=True)
    assert approved['validity_status']=='current' and approved['status']=='approved'
    assert approved['audit'][-1]['confirmed_use'] and kb._approved_chunks()
    for invalid in ('repealed','superseded'):
        other=kb.create(item(category='regulation',validity_status=invalid))
        import pytest
        with pytest.raises(ValueError,match='不能审核启用'):kb.set_status(other['id'],'approved','审核人',confirm_use=True)
        assert next(x for x in kb.list() if x['id']==other['id'])['status']=='draft'
