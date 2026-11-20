import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zipfile
from http.server import ThreadingHTTPServer

from safety_report import assets, calculations, pipeline, provider, server, settings, versions
from safety_report.word import write_docx
from safety_report.documents import parse_file


def sample_report():
    return {'mode': 'llm', 'status': 'draft', 'confirmed_fields': [{'label': '项目名称', 'value': '测试项目'}, {'label': '建设单位', 'value': '测试公司'}],
        'sections': [{'title': '1 设计依据', 'subheadings': ['1.1 备案文件', '1.2 未编写的空标题'],
            'paragraphs': [{'heading': '1.1 备案文件', 'text': '本项目已取得备案文件。', 'evidence_ids': ['real']}],
            'tables': [{'heading': '1.1 备案文件', 'caption': '文件清单', 'headers': ['文件', '数量'], 'rows': [['备案', '1']], 'evidence_ids': ['real']}],
            'missing': ['缺少原件'], 'review': ['请人工核对']}],
        'evidence': [{'id': 'real', 'text': '原始依据', 'source': '原件.txt', 'locator': 'paragraph[1]', 'offset': 0}],
        'unconfirmed_fields': []}


class RevisionUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reviewer = patch('safety_report.agent_graph.ReviewerAgent.run', return_value={'review': []})
        self.reviewer.start()
        self.addCleanup(self.reviewer.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_fire_water_and_relief_calculations_require_sources_and_preserve_inputs(self):
        def sourced(value):
            return {'value': value, 'source_file': '设计依据.pdf', 'source_locator': '第 3 页'}
        water = calculations.calculate_fire_water([
            {'name': '室内消火栓', 'flow': sourced('20'), 'duration': sourced('2')},
            {'name': '自动喷水', 'flow': sourced('10'), 'duration': sourced('1')},
        ])
        self.assertEqual(water['result'], '180.000')
        self.assertEqual(len(water['inputs']), 4)
        self.assertIn('同一建筑', water['assumptions'])
        relief = calculations.calculate_pressure_relief(sourced('1000'), sourced('0.11'))
        self.assertEqual(relief['result'], '110.000')
        self.assertEqual(relief['inputs'][1]['source_locator'], '第 3 页')
        for invalid in ('0', '-1', 'NaN', 'Infinity'):
            with self.assertRaises(ValueError):
                calculations.calculate_pressure_relief(sourced(invalid), sourced('0.11'))
        with self.assertRaises(ValueError):
            calculations.calculate_fire_water([{'name': '室内', 'flow': sourced('20'),
                                               'duration': {'value':'2'}}])

    def test_additional_sources_keep_manual_fields_and_flag_conflicts(self):
        old = [{'key': 'company', 'value': '人工填写公司', 'confirmed': True, 'manual': True, 'candidates': []}]
        new = [{'key': 'company', 'value': '另一家公司', 'confirmed': False, 'candidates': [{'value': '另一家公司'}]}]
        result = pipeline.merge_fields(old, new)
        self.assertEqual(result[0]['value'], '人工填写公司')
        self.assertFalse(result[0]['confirmed'])
        self.assertTrue(result[0]['changed'])

    def test_incremental_parse_reuses_existing_file(self):
        old = self.root / 'old.txt'; old.write_text('建设单位：测试公司', encoding='utf-8')
        new = self.root / 'new.txt'; new.write_text('项目名称：测试项目', encoding='utf-8')
        previous = pipeline.analyze([old])
        with patch('safety_report.pipeline.parse_file', wraps=parse_file) as parser:
            result = pipeline.analyze([old, new], previous)
        self.assertEqual(parser.call_count, 1)
        self.assertEqual(result['reused_documents'], 1)

    def test_unconfirmed_information_cannot_be_silently_ignored(self):
        fields = [{'key': 'company', 'label': '建设单位', 'value': '甲公司', 'confirmed': False}]
        with self.assertRaisesRegex(ValueError, '尚未核对'):
            pipeline.validate_ready(fields)

    def test_dwl2_is_skipped_and_dwg_is_archived(self):
        self.assertTrue(assets.classify('2#辅助车间消防设施示意图.dwl2')['skip'])
        cad = assets.classify('消防图.dwg')
        self.assertFalse(cad['renderable'])
        self.assertFalse(cad['include'])
        self.assertIn('需导出', cad['status'])
        self.assertEqual(assets.classify('消防设施布置图.pdf')['role'], 'figure')

    def test_pdf_page_selection_is_bounded(self):
        self.assertEqual(assets.parse_pages('1,3-5', 5), [1,3,4,5])
        for text in ('0', '5-3', '1-10000', 'a', '6'):
            with self.assertRaises(ValueError): assets.parse_pages(text, 5)

    def test_model_configuration_redacts_secret_and_preserves_on_empty(self):
        data = {'provider': 'custom', 'name': '测试模型', 'base_url': 'https://example.test/v1', 'model': 'test', 'api_key': 'private-test-key', 'json_mode': True}
        ident = settings.save_model(self.root, data)
        public = settings.public(self.root)
        self.assertNotIn('private-test-key', json.dumps(public))
        self.assertTrue(public['models'][0]['key_saved'])
        if os.name == 'posix':
            self.assertEqual(os.stat(self.root / 'settings.json').st_mode & 0o777, 0o600)
        settings.save_model(self.root, {**data, 'id': ident, 'api_key': ''})
        self.assertEqual(settings.resolve(self.root, ident)['api_key'], 'private-test-key')
        config = settings.merge_input(self.root, {**data, 'id': ident, 'api_key': '', 'base_url': 'https://another.test/v1'})
        self.assertEqual(config['api_key'], '')

    def test_nonlocal_plaintext_or_embedded_credentials_are_rejected(self):
        for address in ('http://example.test/v1', 'https://user:password@example.test/v1', 'https://example.test/v1?key=secret'):
            with self.assertRaises(ValueError): provider.validate_config({'base_url': address, 'model': 'x'})

    def test_manual_edit_retains_provenance_and_table_changes(self):
        report = sample_report()
        edited = versions.apply_edits(report, [{'title': report['sections'][0]['title'],
            'paragraphs': [{'original_index': 0, 'heading': '1.1 备案文件', 'text': '人工修订后的内容。'}, {'heading': '1.1 备案文件', 'text': '新增补充说明。'}],
            'tables': [{'headers': ['文件', '数量'], 'rows': [['备案', '2']]}]}])
        paragraphs = edited['sections'][0]['paragraphs']
        self.assertEqual(paragraphs[0]['evidence_ids'], ['real'])
        self.assertTrue(paragraphs[0]['human_edited'])
        self.assertEqual(paragraphs[1]['evidence_ids'], [])
        self.assertEqual(edited['sections'][0]['tables'][0]['rows'][0][1], '2')
        self.assertEqual(report['sections'][0]['tables'][0]['rows'][0][1], '1')

    def test_failed_export_does_not_replace_current_or_erase_history(self):
        report = sample_report()
        export = lambda r,p: write_docx(r, {}, p)
        first = versions.commit(self.root, report, export)
        original = (self.root / 'report.docx').read_bytes()
        def fail(r,p): raise ValueError('渲染失败')
        with self.assertRaises(ValueError): versions.commit(self.root, report, fail)
        self.assertEqual((self.root / 'report.docx').read_bytes(), original)
        self.assertEqual([v['id'] for v in versions.history(self.root)], [first['id']])
        self.assertFalse(list((self.root / 'versions').glob('.pending-*')))

    def test_selective_regeneration_keeps_unselected_chapter_exactly(self):
        profile = {'sha256': 'template', 'headings': [{'text': '1 设计依据', 'level': 1}, {'text': '2 建设项目概况', 'level': 1}]}
        previous = sample_report()
        second = {'title': '2 建设项目概况', 'subheadings': [], 'paragraphs': [{'text': '原稿应保留', 'evidence_ids': ['old']}], 'tables': [], 'missing': [], 'review': []}
        previous['sections'].append(second)
        previous['evidence'].append({'id': 'old', 'text': '旧依据', 'source': 'old.txt', 'locator': 'paragraph[1]', 'offset': 0})
        reply = {'paragraphs': [{'heading': '1 设计依据', 'text': '已根据新增文件修订。', 'evidence_ids': ['new']}], 'tables': [], 'missing': [], 'review': []}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            result = pipeline.generate(profile, {'chunks': [{'id': 'new', 'text': '设计依据 新文件'}]}, [], True, model={'name': '测试'}, previous=previous, chapter_ids=['1'], instructions='补充新依据')
        self.assertEqual(result['sections'][1], second)
        self.assertIn('old', {e['id'] for e in result['evidence']})

    def test_word_omits_debug_lines_and_empty_subheadings(self):
        report = sample_report()
        path = self.root / 'out.docx'
        write_docx(report, {}, path)
        with zipfile.ZipFile(path) as archive:
            xml = archive.read('word/document.xml').decode()
            ET.fromstring(xml)
        for unwanted in ('证据编号', 'real', '请人工核对', '缺少原件', '1.2 未编写的空标题'):
            self.assertNotIn(unwanted, xml)
        self.assertIn('原件.txt', versions.review_html(report))
        self.assertIn('缺少原件', versions.review_html(report))

    def test_first_generation_can_start_with_one_chapter_and_marks_rest_pending(self):
        profile = {'sha256': 'template', 'headings': [
            {'text': '1 设计依据', 'level': 1}, {'text': '1.1 法规', 'level': 2},
            {'text': '2 项目概况', 'level': 1}]}
        evidence = {'id': 'e1', 'text': '项目依据文件编号 ABC-1。', 'source': '依据.txt', 'locator': 'paragraph[1]', 'offset': 0}
        reply = {'paragraphs': [{'heading': '1.1 法规', 'text': '项目采用依据文件 ABC-1 作为设计依据。', 'evidence_ids': ['e1']}],
                 'tables': [], 'missing': [], 'review': []}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            report = pipeline.generate(profile, {'chunks': [evidence]}, [], True, model={'name': '测试'}, chapter_ids=['1'])
        self.assertEqual(report['status'], 'in_progress')
        self.assertEqual(report['updated_chapters'], ['1'])
        self.assertEqual(report['sections'][1]['generation_status'], 'not_generated')
        output = self.root / 'first-chapter.docx'
        write_docx(report, {}, output)
        with zipfile.ZipFile(output) as archive:
            xml = archive.read('word/document.xml').decode()
        self.assertIn('本章尚未生成', xml)
        self.assertIn('项目采用依据文件 ABC-1', xml)

    def test_failed_or_unapproved_legacy_chapters_are_not_exported_as_body(self):
        report = sample_report()
        report['sections'][0].update({'generation_status': 'failed', 'needs_rewrite': True,
                                      'generation_error': '引用校验失败'})
        report['sections'][0]['paragraphs'][0]['text'] = '资料摘录：绝不能出现在本次导出的旧正文。'
        output = self.root / 'failed.docx'
        write_docx(report, {}, output)
        with zipfile.ZipFile(output) as archive:
            xml = archive.read('word/document.xml').decode()
        self.assertIn('本章未通过生成检查', xml)
        self.assertNotIn('绝不能出现在本次导出的旧正文', xml)

    def test_missing_evidence_marks_old_chapter_failed_and_hides_it_from_word(self):
        profile = {'sha256': 'template', 'headings': [
            {'text': '1 设计依据', 'level': 1}, {'text': '2 项目概况', 'level': 1}]}
        previous = sample_report()
        previous['sections'][0]['paragraphs'][0]['text'] = '旧版内容不能假装成新写的正文。'
        previous['sections'].append({'title': '2 项目概况', 'paragraphs': [], 'tables': [], 'missing': [], 'review': []})
        evidence = {'id': 'e2', 'text': '项目概况核实信息编号 XYZ-2。', 'source': '概况.txt', 'locator': 'paragraph[1]', 'offset': 0}
        reply = {'paragraphs': [{'heading': '2 项目概况', 'text': '项目概况依据核实信息 XYZ-2 编写。', 'evidence_ids': ['e2']}],
                 'tables': [], 'missing': [], 'review': []}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            result = pipeline.generate(profile, {'chunks': [evidence]}, [], True, model={'name': '测试'},
                                       previous=previous, chapter_ids=['1', '2'])
        self.assertEqual(result['sections'][0]['generation_status'], 'failed')
        output = self.root / 'missing-evidence.docx'
        write_docx(result, {}, output)
        with zipfile.ZipFile(output) as archive:
            xml = archive.read('word/document.xml').decode()
        self.assertIn('本章未通过生成检查', xml)
        self.assertNotIn('旧版内容不能假装成新写的正文', xml)

    def test_materials_advisor_returns_validated_concrete_requests(self):
        answer = {'requests': [{'priority': '必须', 'subheading': '3.1 物料危险性',
            'ask': '请提供完整物料清单及各物料最大储存量和最大在线量。',
            'include': '名称、组成、浓度、形态、SDS版本、储存和在线数量。',
            'reason': '用于确认物料危险特性并支持后续辨识。', 'examples': ['物料清单', '现行SDS']}],
            'can_draft_now': False, 'note': '补齐关键物料信息后可继续。'}
        with patch('safety_report.pipeline.complete_json', return_value=answer) as call:
            result = pipeline.plan_missing_materials('3 危险源分析',
                {'subheadings': ['3.1 物料危险性'], 'missing': ['缺少物料和数量'], 'review': []},
                [{'id': 'e1', 'source': '目录.docx', 'locator': 'p1', 'text': '本报告包含物料危险性分析。'}],
                {'name': 'local-test'})
        self.assertFalse(result['can_draft_now'])
        self.assertEqual(result['requests'][0]['priority'], '必须')
        self.assertIn('existing_evidence', call.call_args.args[1])

    def test_custom_chapters_can_be_added_removed_and_selectively_rewritten(self):
        previous = sample_report()
        previous['sections'].append({'title': '2 项目概况', 'paragraphs': [], 'tables': [], 'missing': [], 'review': []})
        with_custom = versions.apply_edits(previous, [], add_chapter='项目特殊风险补充分析')
        custom = with_custom['sections'][-1]
        self.assertTrue(custom['custom'])
        self.assertFalse(with_custom['quality_checked'])
        evidence = {'id': 'ec', 'text': '项目特殊风险补充资料编号 SR-5。', 'source': '补充资料.txt', 'locator': '段落1', 'offset': 0}
        reply = {'paragraphs': [{'heading': custom['title'], 'text': '本节依据补充资料 SR-5 对项目特殊风险作说明。', 'evidence_ids': ['ec']}],
                 'tables': [], 'missing': [], 'review': []}
        profile = {'sha256': 'template', 'headings': [{'text': '1 设计依据', 'level': 1}, {'text': '2 项目概况', 'level': 1}]}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            updated = pipeline.generate(profile, {'chunks': [evidence]}, [], True, model={'name': '测试'},
                previous=with_custom, chapter_ids=[custom['id']])
        self.assertEqual(updated['sections'][-1]['id'], custom['id'])
        removed = versions.apply_edits(updated, [], delete_chapter_ids=[custom['id']])
        self.assertFalse(any(s.get('id') == custom['id'] for s in removed['sections']))

    def test_user_supplement_answers_become_chapter_scoped_reviewable_evidence(self):
        profile = {'sha256': 'template', 'headings': [{'text': '1 设计依据', 'level': 1}]}
        answer = '备案日期为2023年5月，已由建设单位提供备案证明原件核实。'
        evidence_id = 'user-supplement-' + hashlib.sha256(('1\0' + answer).encode()).hexdigest()[:20]
        reply = {'paragraphs': [{'heading': '1 设计依据', 'text': '本项目依据已核实的备案证明开展设计。', 'evidence_ids': [evidence_id]}],
                 'tables': [], 'missing': [], 'review': ['用户补充的备案日期需与原件复核。']}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            report = pipeline.generate(profile, {'chunks': []}, [], True, model={'name': '测试'},
                chapter_ids=['1'], supplement_answers=answer, supplement_chapter='1')
        source = next(item for item in report['evidence'] if item['id'] == evidence_id)
        self.assertIn('待核实', source['source'])
        self.assertEqual(source['locator'], '资料补充顾问答复')

    def test_approved_knowledge_is_retrieved_separately_from_project_evidence(self):
        profile = {'sha256': 'template', 'headings': [{'text': '1 设计依据', 'level': 1}]}
        project_fact = {'id': 'project-fact', 'text': '项目备案编号 ABC-1。', 'source': '备案文件.docx',
                        'locator': 'page[1]', 'offset': 0}
        kb_rule = {'id': 'kb-rule', 'text': '审核通过的通用规则：核对设计依据适用范围。',
                   'source': '知识库：设计依据审核规则', 'locator': '审核版本 v1', 'corpus': 'approved_knowledge',
                   'knowledge_status': 'approved'}
        reply = {'paragraphs': [{'heading': '1 设计依据', 'text': '本项目备案编号为 ABC-1，并按经审核的通用规则核对适用范围。',
                                 'evidence_ids': ['project-fact', 'kb-rule']}],
                 'tables': [], 'missing': [], 'review': []}
        with patch('safety_report.pipeline.complete_json', return_value=reply) as complete:
            result = pipeline.generate(profile, {'chunks': [project_fact]}, [], True, model={'name': '测试'},
                chapter_ids=['1'], knowledge_retriever=lambda query, limit: [kb_rule])
        sent = complete.call_args.args[1]
        self.assertTrue(any(item.get('corpus') == 'approved_knowledge' for item in sent['evidence']))
        self.assertIn('kb-rule', {e['id'] for e in result['evidence']})

    def test_decided_measure_adoption_records_enter_chapter_four_evidence(self):
        profile = {'sha256': 'template', 'headings': [{'text': '4 安全对策措施采纳情况', 'level': 1}]}
        project_fact = {'id': 'project-fact', 'text': '综合分析报告提出设置围堰。', 'source': '综合分析报告.docx',
                        'locator': 'page[12]', 'offset': 0}
        measure = {'id': 'measure-m1-r1', 'text': '建议原文：设置围堰。\n采纳状态：adopted\n设计落实：图纸 Z-03 设置围堰。',
                   'source': '综合分析报告.docx', 'locator': 'page[12]', 'corpus': 'project_evidence',
                   'evidence_type': 'measure_adoption', 'disposition': 'adopted'}
        reply = {'paragraphs': [{'heading': '4 安全对策措施采纳情况', 'text': '结合前期建议，设计在 Z-03 图纸中配置了相应的液体围护设施。',
                                 'evidence_ids': ['project-fact', 'measure-m1-r1']}],
                 'tables': [], 'missing': [], 'review': []}
        class FakeIndex:
            client = None
            semantic_error = None
            def __init__(self, chunks, path=None): self.chunks = chunks
            def search(self, query, limit=10): return self.chunks[:limit]
            def close(self): pass
        with patch('safety_report.pipeline.HybridEvidenceIndex', FakeIndex), \
             patch('safety_report.pipeline.complete_json', return_value=reply) as complete:
            result = pipeline.generate(profile, {'chunks': [project_fact]}, [], True, model={'name': '测试'},
                chapter_ids=['4'], measure_evidence=[measure])
        self.assertTrue(any(e['id'] == 'measure-m1-r1' for e in result['evidence']))
        self.assertTrue(any(e.get('evidence_type') == 'measure_adoption' for e in complete.call_args.args[1]['evidence']))

    def test_agent_followup_query_can_add_approved_knowledge_to_report_snapshot(self):
        profile={'sha256':'template','headings':[{'text':'1 设计依据','level':1}]}
        fact={'id':'e1','text':'项目取得备案文件 A-1。','source':'备案.txt','locator':'第1段','offset':0}
        rule={'id':'kb-rule-extra','text':'经审核的通用设计要求。','source':'知识库：编制规则',
              'locator':'审核版本 v1','corpus':'approved_knowledge'}
        class FakeIndex:
            client=None;semantic_error=None
            def __init__(self, chunks, path=None): self.chunks=chunks
            def search(self, query, limit=10): return self.chunks[:limit]
            def close(self): pass
        def knowledge(query, limit=5):
            return [rule] if query=='精准条款' else []
        def complete(system, payload, model, **kwargs):
            if '资料规划 Agent' in system:
                return {'queries':['精准条款']}
            return {'paragraphs':[{'heading':'1 设计依据','text':'设计文件结合备案信息和经审核的通用编制要求组织。',
                                   'evidence_ids':['e1','kb-rule-extra']}],
                    'tables':[],'missing':[],'review':[]}
        with patch('safety_report.pipeline.HybridEvidenceIndex',FakeIndex), \
             patch('safety_report.pipeline.complete_json',side_effect=complete):
            result=pipeline.generate(profile,{'chunks':[fact]},[],True,model={'name':'测试'},
                                     chapter_ids=['1'],knowledge_retriever=knowledge)
        self.assertIn('kb-rule-extra',{item['id'] for item in result['evidence']})

    def test_professionally_reviewed_calculation_is_traceable_chapter_evidence(self):
        profile = {'sha256': 'template', 'headings': [{'text': '3 危险分析', 'level': 1}]}
        project_fact = {'id': 'project-fact', 'text': '消防设计说明给出设计流量。', 'source': '消防设计说明.docx',
                        'locator': 'page[8]', 'offset': 0}
        calc = {'id': 'calculation-c1-r1', 'text': '核准公式和复核结果。',
                'source': '专业分析计算台账：消防用水量核算', 'locator': '审核版本 v1',
                'corpus': 'project_evidence', 'evidence_type': 'professional_calculation',
                'calculation_status': 'reviewed', 'reviewed_by': '工程师甲'}
        reply = {'paragraphs': [{'heading': '3 危险分析', 'text': '依据已复核的计算记录，结果为 20 L/s。',
                                 'evidence_ids': ['project-fact', 'calculation-c1-r1']}],
                 'tables': [], 'missing': [], 'review': []}
        class FakeIndex:
            client = None
            semantic_error = None
            def __init__(self, chunks, path=None): self.chunks = chunks
            def search(self, query, limit=10): return self.chunks[:limit]
            def close(self): pass
        with patch('safety_report.pipeline.HybridEvidenceIndex', FakeIndex), \
             patch('safety_report.pipeline.complete_json', return_value=reply) as complete:
            report = pipeline.generate(profile, {'chunks': [project_fact]}, [], True,
                model={'name': '测试'}, chapter_ids=['3'], calculation_evidence=[calc])
        self.assertIn('calculation-c1-r1', {item['id'] for item in report['evidence']})
        self.assertTrue(any(item.get('evidence_type') == 'professional_calculation'
                            for item in complete.call_args.args[1]['evidence']))

    def test_deleted_template_chapter_stays_excluded_after_regeneration(self):
        previous = sample_report()
        previous['sections'].append({'title': '2 项目概况', 'paragraphs': [], 'tables': [], 'missing': [], 'review': []})
        removed = versions.apply_edits(previous, [], delete_chapter_ids=['2'])
        evidence = {'id': 'e1', 'text': '备案文件编号 ABC-1。', 'source': '依据.txt', 'locator': '段落1', 'offset': 0}
        reply = {'paragraphs': [{'heading': '1 设计依据', 'text': '本项目设计依据包括备案文件 ABC-1。', 'evidence_ids': ['e1']}],
                 'tables': [], 'missing': [], 'review': []}
        profile = {'sha256': 'template', 'headings': [{'text': '1 设计依据', 'level': 1}, {'text': '2 项目概况', 'level': 1}]}
        with patch('safety_report.pipeline.complete_json', return_value=reply):
            regenerated = pipeline.generate(profile, {'chunks': [evidence]}, [], True, model={'name': '测试'},
                previous=removed, chapter_ids=['1'])
        self.assertEqual([s['title'] for s in regenerated['sections']], ['1 设计依据'])
        self.assertFalse(regenerated['quality_checked'])

    def test_images_and_pdf_pages_render_to_word_compatible_png(self):
        from PIL import Image
        from pypdf import PdfWriter
        (self.root/'uploads').mkdir()
        image = self.root/'uploads'/'input.jpg'
        Image.new('RGB', (300,200), '#a0c0a0').save(image)
        figure={'name':'input.jpg','stored':'input.jpg','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
        output=assets.render_file(self.root,figure)
        self.assertTrue(output.read_bytes().startswith(b'\x89PNG'))
        pdf=self.root/'uploads'/'input.pdf'
        writer=PdfWriter();writer.add_blank_page(width=400,height=300);writer.write(pdf)
        figure={'name':'input.pdf','stored':'input.pdf','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
        output=assets.render_file(self.root,figure)
        self.assertTrue(output.read_bytes().startswith(b'\x89PNG'))


class RevisionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.previous_data=server.DATA;server.DATA=Path(cls.temp.name)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=5)
        server.close_knowledge_stores(cls.temp.name)
        server.DATA=cls.previous_data;cls.temp.cleanup()

    def request(self,path,data=None,raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(self.url+path,data=body),timeout=10) as response:
            return json.load(response)

    def project(self):
        project=self.request('/api/projects',{'name':'修订测试'})
        return project['id'],'/api/projects/'+project['id']

    def test_report_type_is_bound_to_project_and_preflight_uses_correct_structure(self):
        project=self.request('/api/projects',{'name':'预案项目','report_type':'emergency_plan'})
        route='/api/projects/'+project['id']
        self.assertEqual(self.request(route)['report_type'],'emergency_plan')
        template=self.request('/api/template?report_type=emergency_plan')
        self.assertEqual(template['headings'][0]['text'],'1 总则')
        advice={'requests':[],'can_draft_now':True,'note':'测试'}
        with patch('safety_report.server.settings.resolve',return_value={'model':'mock'}), \
             patch('safety_report.server.plan_missing_materials',return_value=advice) as planner:
            result=self.request(route+'/materials-plan',{'chapter_id':'1','model_id':'mock'})
        self.assertEqual(result['chapter'],'1 总则')
        self.assertEqual(planner.call_args.kwargs['report_name'],'生产安全事故应急预案')

    def test_global_knowledge_records_are_separate_from_project_data(self):
        before=self.request('/api/knowledge')
        record=self.request('/api/knowledge',{'category':'report_rule','title':'报告核对规则',
            'content':'每个关键结论应关联证据。','source':'公司审核手册','source_url':'',
            'applicability':'安全设施设计报告','version':'v1','effective_from':'','effective_to':''})['record']
        self.assertEqual(record['status'],'draft')
        self.request('/api/knowledge/'+record['id']+'/status',{'status':'approved','reviewed_by':'审核人甲'})
        listed=self.request('/api/knowledge')
        saved=next(x for x in listed['records'] if x['id']==record['id'])
        self.assertEqual(saved['status'],'approved')
        self.assertEqual(saved['revision'],1)
        self.assertEqual(before['records'],[])

    def test_project_measure_adoption_ledger_persists_source_and_decision(self):
        _,route=self.project()
        payload={'recommendation':'建议增设可燃气体报警器。','source_file':'综合分析报告.docx',
            'source_locator':'page[8]','source_evidence_id':'','disposition':'adopted',
            'design_response':'在可燃气体风险区域设置报警器。','report_section':'4.3 检测报警','reviewed_by':'安全工程师甲'}
        saved=self.request(route+'/measures',payload)['item']
        listed=self.request(route+'/measures')['items']
        self.assertEqual(listed[0]['id'],saved['id'])
        self.assertEqual(listed[0]['source_locator'],'page[8]')

    def test_project_calculation_ledger_requires_auditable_review_before_report_use(self):
        _,route=self.project()
        draft={'kind':'fire_water','title':'消防用水量记录','status':'draft','inputs':[
            {'name':'设计流量','value':'20','unit':'L/s','source_file':'消防说明.docx','source_locator':'第 8 页','evidence_id':''}],
            'source_rule':'核准设计依据','rule_version':'2026版','rule_clause':'第 5 章',
            'formula':'经专业人员确认的公式','steps':'人工复核计算过程','result':'20','result_unit':'L/s',
            'assumptions':'适用条件','reviewer':'专业工程师甲','review_note':'已复核','report_section':'5.4 消防'}
        item=self.request(route+'/calculations',draft)['item']
        self.assertEqual(item['status'],'draft')
        self.assertEqual(self.request(route+'/calculations')['items'][0]['id'],item['id'])
        approved=self.request(route+'/calculations',{**draft,'id':item['id'],'status':'reviewed',
            'rule_validity_status':'current','rule_checked_date':'2026-11-03'})['item']
        self.assertEqual(approved['revision'],2)
        self.assertEqual(len(server.CalculationLedger(server.directory(route.split('/')[-1])/'calculations.json').report_evidence()),1)

    def test_major_hazard_calculator_saves_unapproved_traceable_result(self):
        pid,route=self.project()
        result=self.request(route+'/calculations',{'operation':'calculate_major_hazard',
            'unit_name':'原料罐区单元','unit_source_file':'总图.pdf','unit_source_locator':'第 1 页',
            'materials':[{'name':'甲物质','quantity_t':'0.5','critical_t':'1',
                'quantity_source_file':'物料清单.xlsx','quantity_source_locator':'Sheet1 第 3 行',
                'critical_source_file':'GB 18218-2018','critical_source_locator':'表 1，经专业人员核验'}]})
        self.assertEqual(result['calculation']['indicator'],'0.5')
        self.assertEqual(result['item']['status'],'draft')
        self.assertEqual(result['item']['rule_validity_status'],'unknown')
        self.assertEqual(result['item']['rule_checked_date'],'')
        self.assertEqual(result['item']['inputs'][0]['source_file'],'总图.pdf')
        ledger=server.CalculationLedger(server.directory(pid)/'calculations.json')
        self.assertEqual(ledger.report_evidence(),[])

    def test_fire_and_relief_calculations_are_saved_as_unverified_drafts(self):
        pid, route = self.project()
        value=lambda x: {'value': x, 'source_file':'设计文件.pdf', 'source_locator':'第 2 页'}
        water=self.request(route+'/calculations',{'operation':'calculate_fire_water','name':'车间火灾场景',
            'systems':[{'name':'室内消火栓','flow':value('20'),'duration':value('2')}]})
        relief=self.request(route+'/calculations',{'operation':'calculate_pressure_relief','name':'车间计算段',
            'volume':value('1000'),'coefficient':value('0.11')})
        self.assertEqual(water['calculation']['result'],'144.000')
        self.assertEqual(relief['calculation']['result'],'110.000')
        self.assertEqual(relief['item']['rule_validity_status'],'unknown')
        self.assertEqual(relief['item']['status'],'draft')
        self.assertEqual(server.CalculationLedger(server.directory(pid)/'calculations.json').report_evidence(),[])

    def test_project_files_can_keep_type_date_and_revision_metadata(self):
        pid,route=self.project()
        from urllib.parse import quote
        self.request(route+'/upload?name='+quote('综合分析报告.txt'),raw='安全建议：设置报警器。'.encode())
        state=self.request(route)
        file=state['files'][0]
        self.request(route+'/files',{'id':file['id'],'document_type':'safety_analysis','document_source':'建设单位提供',
            'document_date':'2025-03-01','document_version':'送审稿 v2'})
        updated=self.request(route)['files'][0]
        self.assertEqual(updated['document_type'],'safety_analysis')
        self.assertEqual(updated['document_source'],'建设单位提供')
        self.assertEqual(updated['document_date'],'2025-03-01')
        self.assertEqual(updated['document_version'],'送审稿 v2')

    def test_materials_plan_endpoint_only_returns_advice_and_does_not_commit_report(self):
        pid,route=self.project()
        self.request(route+'/upload?name=project.txt',raw='项目名称：测试项目\n建设单位：测试公司\n项目备案编号：AB-12'.encode())
        target=server.directory(pid);server.job(target,'analyze')
        state=self.request(route)
        for field in state['fields']: field['confirmed']=bool(field['value'])
        self.request(route+'/facts',{'fields':state['fields']})
        server.job(target,'generate',False)
        before=server.load(target/'state.json')['report_version']
        advice={'requests':[],'can_draft_now':True,'note':'现有材料可先起草。'}
        with patch('safety_report.server.settings.resolve',return_value={'model':'mock'}), \
             patch('safety_report.server.plan_missing_materials',return_value=advice):
            result=self.request(route+'/materials-plan',{'chapter_id':'1','model_id':'mock-id'})
        self.assertEqual(result['note'],advice['note'])
        self.assertEqual(server.load(target/'state.json')['report_version'],before)

    def test_preflight_can_be_cancelled_without_creating_a_report(self):
        pid, route = self.project()
        self.request(route+'/upload?name=project.txt',raw='项目名称：测试项目\n建设单位：测试公司'.encode())
        target=server.directory(pid);server.job(target,'analyze')
        started=threading.Event()
        def wait_for_cancel(chapter, section, evidence, model, cancel_event=None):
            started.set()
            if not cancel_event.wait(5):
                raise AssertionError('取消信号未到达')
            raise provider.GenerationCancelled()
        with patch('safety_report.server.settings.resolve',return_value={'model':'mock'}), \
             patch('safety_report.server.plan_missing_materials',side_effect=wait_for_cancel):
            self.request(route+'/preflight',{'chapter_ids':['1'],'model_id':'mock-id'})
            self.assertTrue(started.wait(5))
            self.assertEqual(self.request(route)['current_operation'],'preflight')
            self.request(route+'/cancel',{})
            for _ in range(100):
                state=self.request(route)
                if not state['busy']: break
                threading.Event().wait(.02)
        self.assertFalse(state['busy'])
        self.assertIsNone(state['preflight_result'])
        self.assertFalse((target/'report.docx').exists())

    def test_temp_file_does_not_abort_import_and_deduplication(self):
        pid,route=self.project()
        result=self.request(route+'/upload?name=2%23%E8%BD%A6%E9%97%B4.dwl2',raw=b'temporary')
        self.assertTrue(result['skipped'])
        self.request(route+'/upload?name=a.txt',raw='建设单位：测试公司'.encode())
        result=self.request(route+'/upload?name=again.txt',raw='建设单位：测试公司'.encode())
        self.assertTrue(result['duplicate'])
        self.assertEqual(len(self.request(route)['files']),1)

    def test_unchecked_generation_is_blocked_but_draft_is_preserved(self):
        pid,route=self.project()
        self.request(route+'/upload?name=a.txt',raw='建设单位：测试公司\n项目名称：测试项目'.encode())
        target=server.directory(pid);server.job(target,'analyze')
        (target/'report.docx').write_bytes(b'old-draft')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(route+'/generate',{'use_llm':False})
        self.assertEqual(error.exception.code,400)
        self.assertEqual((target/'report.docx').read_bytes(),b'old-draft')

    def test_append_and_manual_changes_can_create_new_version_without_reupload(self):
        pid,route=self.project()
        self.request(route+'/upload?name=a.txt',raw='建设单位：测试公司\n项目名称：测试项目'.encode())
        target=server.directory(pid);server.job(target,'analyze')
        state=self.request(route)
        for field in state['fields']:
            field['confirmed']=bool(field['value'])
        self.request(route+'/facts',{'fields':state['fields']})
        server.job(target,'generate',False)
        first=self.request(route)
        self.assertTrue(first['has_report'])
        self.assertEqual(len(first['versions']),1)
        self.request(route+'/upload?name=new.txt',raw='消防设施：新增消火栓'.encode())
        after=self.request(route)
        self.assertTrue(after['has_report'])
        self.assertTrue(after['analysis_dirty'])
        server.job(target,'analyze')
        latest=self.request(route)
        self.assertTrue(next(f for f in latest['fields'] if f['key']=='company')['confirmed'])
        report=self.request(route+'/report')['report']
        section=report['sections'][0]
        self.request(route+'/edit',{'base_version':latest['report_version'],'sections':[{'title':section['title'],'paragraphs':[{'heading':section['title'],'text':'人工补充的新段落。'}]}]})
        current=self.request(route)
        self.assertEqual(len(current['versions']),2)
        self.assertEqual(self.request(route+'/report')['report']['sections'][0]['paragraphs'][0]['text'],'人工补充的新段落。')
        with self.assertRaises(urllib.error.HTTPError):
            self.request(route+'/edit',{'base_version':latest['report_version'],'sections':[]})
        self.request(route+'/restore',{'base_version':current['report_version'],'version':first['report_version']})
        self.assertEqual(len(self.request(route)['versions']),3)

    def test_model_key_is_never_returned_by_settings_endpoints(self):
        response=self.request('/api/settings/model',{'name':'示例','provider':'custom','base_url':'https://example.test/v1','model':'test','api_key':'never-return-secret'})
        self.assertNotIn('never-return-secret',json.dumps(response))
        self.assertNotIn('never-return-secret',json.dumps(self.request('/api/settings')))


if __name__=='__main__':unittest.main()
