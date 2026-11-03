import tempfile
import unittest
from pathlib import Path

from safety_report.measures import MeasuresLedger


class MeasuresLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = MeasuresLedger(Path(self.temp.name) / 'measures.json')

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **changes):
        return {'recommendation': '对甲类仓库设置相应安全设施。', 'source_file': '综合分析报告.docx',
                'source_locator': 'page[12]', 'source_evidence_id': 'ev-1', 'disposition': 'adopted',
                'design_response': '设计图纸 Z-03 设置对应设施。', 'report_section': '4.2 仓库安全设施',
                'reviewed_by': '安全工程师甲', **changes}

    def test_decided_items_are_reportable_and_pending_items_are_not(self):
        pending = self.ledger.save(self.payload(disposition='pending', reviewed_by='', design_response=''))
        decided = self.ledger.save(self.payload())
        chunks = self.ledger.report_evidence()
        self.assertEqual(len(chunks), 1)
        self.assertIn(decided['id'], chunks[0]['id'])
        self.assertNotIn(pending['id'], chunks[0]['id'])
        self.assertEqual(chunks[0]['disposition'], 'adopted')
        self.assertEqual(chunks[0]['source'], '综合分析报告.docx')

    def test_adoption_decision_requires_reviewer_and_design_detail(self):
        with self.assertRaises(ValueError):
            self.ledger.save(self.payload(reviewed_by=''))
        with self.assertRaises(ValueError):
            self.ledger.save(self.payload(design_response=''))
        with self.assertRaises(ValueError):
            self.ledger.save(self.payload(disposition='not_adopted', design_response=''))

    def test_revision_history_is_preserved(self):
        first = self.ledger.save(self.payload())
        updated = self.ledger.save(self.payload(design_response='更新设计落实说明。'), first['id'])
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['history'][0]['design_response'], '设计图纸 Z-03 设置对应设施。')


if __name__ == '__main__':
    unittest.main()
