import tempfile
import unittest
from pathlib import Path

from safety_report.calculations import CalculationLedger, calculate_major_hazard_indicator
from safety_report.quality import review_report


def record(status='draft'):
    return {'kind': 'fire_water', 'title': '消防用水量核算记录', 'status': status,
        'inputs': [{'name': '设计流量', 'value': '20', 'unit': 'L/s',
                    'source_file': '消防设计说明.docx', 'source_locator': '第 8 页',
                    'evidence_id': 'source-1'}],
        'source_rule': '经公司核验的设计依据', 'rule_version': '2025版',
        'rule_clause': '第 6 章', 'rule_validity_status':'current','rule_checked_date':'2026-11-03',
        'formula': '按核准公式计算',
        'steps': '人工复核的过程记录', 'result': '待复核结果', 'result_unit': 'L/s',
        'assumptions': '边界条件说明', 'reviewer': '专业工程师甲',
        'review_note': '已对照原始资料', 'report_section': '5.4 消防设施'}


class CalculationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = CalculationLedger(Path(self.temp.name) / 'calculations.json')

    def tearDown(self):
        self.temp.cleanup()

    def test_reviewed_record_requires_sources_and_auditable_method(self):
        bad = record('reviewed')
        bad['inputs'][0]['source_locator'] = ''
        with self.assertRaisesRegex(ValueError, '来源文件和位置'):
            self.ledger.save(bad)
        bad = record('reviewed')
        bad['formula'] = ''
        with self.assertRaisesRegex(ValueError, '公式'):
            self.ledger.save(bad)

    def test_gb18218_single_and_multiple_species_screening(self):
        def row(name, q, Q):
            return {'name':name,'quantity_t':q,'critical_t':Q,
                    'quantity_source_file':'项目物料清单.xlsx','quantity_source_locator':'Sheet1 行2',
                    'critical_source_file':'GB 18218-2018','critical_source_locator':'表1 经专业人员确认'}
        single=calculate_major_hazard_indicator('储存单元 A','总图.pdf','第 1 页',[row('物质甲','1','1')])
        self.assertTrue(single['is_at_or_above_threshold'])
        self.assertIn('单一品种',single['rule_clause'])
        mixed=calculate_major_hazard_indicator('生产单元 B','工艺说明.docx','第 4 页',
            [row('物质乙','0.5','1'),row('物质丙','1','4')])
        self.assertEqual(mixed['indicator'],'0.75')
        self.assertFalse(mixed['is_at_or_above_threshold'])
        self.assertIn('式（1）',mixed['rule_clause'])
        with self.assertRaisesRegex(ValueError,'来源文件及位置'):
            calculate_major_hazard_indicator('A','x','第 1 页',[{**row('物质甲','1','10'),'critical_source_locator':''}])
        with self.assertRaisesRegex(ValueError,'重复物质名称'):
            calculate_major_hazard_indicator('A','x','第 1 页',[row('甲','1','10'),row('甲','2','10')])

    def test_only_reviewed_records_become_report_evidence_and_revisions_persist(self):
        draft = self.ledger.save(record())
        self.assertEqual(self.ledger.report_evidence(), [])
        approved = self.ledger.save(record('reviewed'), draft['id'])
        evidence = self.ledger.report_evidence()
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['result'], '待复核结果')
        self.assertEqual(approved['history'][0]['status'], 'draft')
        self.assertEqual(approved['revision'], 2)
        changed = self.ledger.save({**record('reviewed'), 'result':'21'}, approved['id'])
        self.assertEqual(changed['status'], 'draft')
        self.assertEqual(changed['reviewer'], '')
        self.assertEqual(self.ledger.report_evidence(), [])

    def test_quality_review_flags_unresolved_conflict_and_measure_omission(self):
        report = {'sections': [{'id': '3', 'title': '3 危险分析', 'paragraphs': [], 'tables': [],
                                'missing': [], 'review': []}],
                  'evidence': [], 'unconfirmed_fields': []}
        state = {'fields': [{'key': 'project', 'label': '项目名称', 'conflict': True}],
                 'files': [], 'report_outdated': False, 'source_changes_pending': False}
        measures = [{'id': 'm1', 'revision': 1, 'disposition': 'adopted', 'recommendation': '设置围堰'}]
        result = review_report(report, state, measures=measures)
        statuses = {item['key']: item['status'] for item in result['checks']}
        self.assertEqual(statuses['source_conflicts'], 'fail')
        self.assertEqual(statuses['measure_adoption'], 'warning')
        self.assertEqual(statuses['pending_measures'], 'pass')
        self.assertEqual(result['overall'], 'needs_review')

    def test_quality_review_requires_current_knowledge_evidence_for_standard_citations(self):
        body={'id':'e1','text':'旧项目按 GB 18218-2018 核验。','source':'项目报告.docx','locator':'第 5 页'}
        report={'sections':[{'id':'3','title':'3 危险分析','paragraphs':[
            {'text':'旧项目按 GB 18218-2018 核验。','evidence_ids':['e1']}], 'tables':[],'missing':[],'review':[]}],
            'evidence':[body],'unconfirmed_fields':[]}
        state={'fields':[{'key':'project','label':'项目名称','value':'新项目','candidates':[
            {'value':'旧项目'}]}], 'files':[], 'report_outdated':False,'source_changes_pending':False}
        checks={item['key']:item for item in review_report(report,state)['checks']}
        self.assertEqual(checks['regulation_validity']['status'],'warning')
        self.assertEqual(checks['cross_chapter_consistency']['status'],'warning')
        current={'id':'law','source':'知识库：GB 18218-2018','locator':'审核版本 v1',
            'corpus':'approved_knowledge','category':'regulation','validity_status':'current'}
        report['sections'][0]['paragraphs'][0]['evidence_ids'].append('law')
        report['evidence'].append(current)
        checks={item['key']:item for item in review_report(report,state)['checks']}
        self.assertEqual(checks['regulation_validity']['status'],'pass')
        current['source']='知识库：GB 50016-2014'
        checks={item['key']:item for item in review_report(report,state)['checks']}
        self.assertEqual(checks['regulation_validity']['status'],'warning')

    def test_empty_measures_is_flagged_when_analysis_report_exists(self):
        report={'sections':[],'evidence':[],'unconfirmed_fields':[]}
        state={'fields':[],'files':[{'name':'综合分析报告.docx','document_type':'safety_analysis','active':True}]}
        checks={item['key']:item for item in review_report(report,state)['checks']}
        self.assertEqual(checks['measure_adoption']['status'],'warning')


if __name__ == '__main__':
    unittest.main()
