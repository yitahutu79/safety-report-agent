import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer

from safety_report import server
from safety_report.documents import read_docx, inspect_template, parse_file, retrieve, W
from safety_report.pipeline import analyze, generate, validate_section
from safety_report.word import write_docx
from safety_report.visuals import draw_flow


def fixture_docx(path):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', f'<w:document xmlns:w="{W[1:-1]}"><w:body><w:p><w:pPr><w:pStyle w:val="toc"/></w:pPr><w:r><w:t>1 设计依据1</w:t></w:r></w:p><w:p><w:pPr><w:pStyle w:val="h"/></w:pPr><w:r><w:t>1 设计依据</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>企业名称</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>测试公司</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:sectPr><w:pgSz w:w="11905" w:h="16838"/></w:sectPr></w:body></w:document>')
        archive.writestr('word/styles.xml', f'<w:styles xmlns:w="{W[1:-1]}"><w:style w:styleId="h"><w:name w:val="标题"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style><w:style w:styleId="toc"><w:name w:val="toc 1"/></w:style></w:styles>')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_template_excludes_toc_and_preserves_table(self):
        path = self.root / 'reference.docx'
        fixture_docx(path)
        profile = inspect_template(path)
        self.assertEqual([h['text'] for h in profile['headings']], ['1 设计依据'])
        self.assertEqual(profile['table_count'], 1)
        self.assertEqual(read_docx(path)[0][-1]['rows'], [['企业名称', '测试公司']])

    def test_conflicting_values_require_manual_choice(self):
        a, b = self.root / 'a.txt', self.root / 'b.txt'
        a.write_text('建设单位：甲公司\n生产规模：100吨/年', encoding='utf-8')
        b.write_text('建设单位：乙公司\n生产规模：200吨/年', encoding='utf-8')
        analysis = analyze([a, b])
        field = analysis['fields'][0]
        self.assertTrue(field['conflict'])
        self.assertEqual(field['value'], '')
        self.assertFalse(field['confirmed'])
        self.assertEqual(len(field['candidates']), 2)

    def test_evidence_ids_are_reproducible(self):
        path = self.root / '资料.txt'
        path.write_text('建设单位：测试公司', encoding='utf-8')
        self.assertEqual(parse_file(path)['chunks'], parse_file(path)['chunks'])

    def test_pdf_recovers_complex_page_and_keeps_readable_pages(self):
        path = self.root / '图纸.pdf'
        path.write_bytes(b'fixture')
        reader = Mock()
        reader.pages = [
            Mock(extract_text=Mock(return_value='首页正文' * 10)),
            Mock(extract_text=Mock(side_effect=ValueError('complex page'))),
            Mock(extract_text=Mock(side_effect=ValueError('unreadable page'))),
            Mock(extract_text=Mock(return_value='末页正文' * 10)),
        ]
        with patch('pypdf.PdfReader', return_value=reader), patch(
            'safety_report.documents._extract_pdf_page_with_pdfium',
            side_effect=['恢复的第二页正文' * 10, ValueError('fallback also failed')],
        ) as fallback:
            result = parse_file(path)

        self.assertEqual([call.args for call in fallback.call_args_list], [(path, 1), (path, 2)])
        self.assertEqual([chunk['locator'] for chunk in result['chunks']], ['page[1]', 'page[2]', 'page[4]'])
        self.assertIn('恢复的第二页正文', result['chunks'][1]['text'])
        self.assertTrue(any('第 2 页已用备用解析器恢复文字' in warning for warning in result['warnings']))
        self.assertTrue(any('第 3 页文本提取失败' in warning for warning in result['warnings']))

    def test_irrelevant_evidence_is_not_selected(self):
        self.assertEqual(retrieve([{'text': 'ABC', 'id': 'x'}], '消防用水'), [])

    def test_unknown_and_empty_citations_are_rejected(self):
        for ids in (['invented'], []):
            with self.assertRaises(ValueError):
                validate_section({'paragraphs': [{'text': '符合要求', 'evidence_ids': ids}], 'tables': [], 'missing': [], 'review': []}, [{'id': 'real'}])

    def test_ragged_model_tables_are_rejected(self):
        result = {'paragraphs': [], 'tables': [{'caption': '设备', 'headers': ['设备', '数量'], 'rows': [['A']], 'evidence_ids': ['real']}], 'missing': [], 'review': []}
        with self.assertRaises(ValueError):
            validate_section(result, [{'id': 'real'}])

    def test_offline_generation_does_not_assert_final_conclusion(self):
        profile = {'headings': [{'text': '1 设计依据', 'level': 1}], 'sha256': 'template'}
        report = generate(profile, {'chunks': []}, [], False)
        self.assertEqual(report['status'], 'draft')
        self.assertTrue(report['sections'][0]['missing'])
        self.assertEqual(report['sections'][0]['paragraphs'], [])

    def test_word_xml_escapes_and_retains_evidence(self):
        report = {'confirmed_fields': [{'label': '项目名称', 'value': '甲&乙<项目>'}], 'mode': 'llm',
                  'sections': [{'title': '1 设计依据', 'subheadings': ['1.1 批复文件'], 'paragraphs': [{'text': '原始事实<内容>', 'evidence_ids': ['e1']}], 'tables': [{'caption': '表1', 'headers': ['名称', '数量'], 'rows': [['A&B', '1']], 'evidence_ids': ['e1']}], 'missing': [], 'review': ['待审核']}],
                  'evidence': [{'id': 'e1', 'source': 'input.txt', 'locator': 'paragraph[1]', 'offset': 0}]}
        path = self.root / 'report.docx'
        write_docx(report, {'sections': []}, path)
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(('.xml', '.rels')):
                    ET.fromstring(archive.read(name))
            self.assertNotIn('证据编号', archive.read('word/document.xml').decode())
            self.assertNotIn('e1', archive.read('word/document.xml').decode())
            self.assertIn('w:tblHeader', archive.read('word/document.xml').decode())
            self.assertNotIn('word/header1.xml', archive.namelist())

    def test_model_sections_are_grounded_and_routed_to_template(self):
        profile = {'headings': [{'text': '2 建设项目概况', 'level': 1}, {'text': '2.1 建设单位', 'level': 2}], 'sha256': 'template'}
        evidence = [{'id': 'e1', 'text': '建设单位：测试公司', 'source': 'input.txt', 'locator': 'paragraph[1]'}]
        response = {'paragraphs': [{'heading': '2.1 建设单位', 'text': '建设单位为测试公司。', 'evidence_ids': ['e1']}], 'tables': [], 'missing': [], 'review': []}
        with patch('safety_report.pipeline.complete_json', return_value=response), \
             patch('safety_report.agent_graph.ReviewerAgent.run', return_value={'review': []}):
            report = generate(profile, {'chunks': evidence}, [], True)
        self.assertEqual(report['sections'][0]['paragraphs'][0]['heading'], '2.1 建设单位')
        response['paragraphs'][0]['heading'] = '虚构章节'
        with patch('safety_report.pipeline.complete_json', return_value=response), self.assertRaises(ValueError):
            generate(profile, {'chunks': evidence}, [], True)

    def test_flow_input_and_xml_injection(self):
        with self.assertRaises(ValueError):
            draw_flow(['只有一步'], self.root)
        with patch.dict(os.environ, {'CJK_FONT': '/not-a-font'}):
            draw_flow(['A<script>', 'B&步骤'], self.root)
        ET.fromstring((self.root / 'flow.svg').read_text(encoding='utf-8'))
        self.assertNotIn('<script>', (self.root / 'flow.svg').read_text(encoding='utf-8'))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_data = server.DATA
        server.DATA = Path(cls.temp.name)
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=5)
        server.close_knowledge_stores(cls.temp.name)
        server.DATA = cls.old_data
        cls.temp.cleanup()

    def request(self, path, data=None, headers=None, raw=None):
        encoded = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.url + path, data=encoded, headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)

    def test_password_protects_projects(self):
        with patch.dict(os.environ, {'APP_PASSWORD': 'test-only-password'}):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request('/api/projects')
            self.assertEqual(ctx.exception.code, 401)

    def test_cross_origin_writes_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/projects', {'name': '跨站项目'}, {'Origin': 'https://other.example'})
        self.assertEqual(ctx.exception.code, 403)

    def test_project_upload_and_analyze_isolation(self):
        with patch.dict(os.environ, {'APP_PASSWORD': ''}):
            _, project = self.request('/api/projects', {'name': '测试项目'})
            pid = project['id']
            _, other = self.request('/api/projects', {'name': '另一个项目'})
            self.request(f'/api/projects/{pid}/upload?name=test.txt', raw='建设单位：测试公司'.encode())
            _, result = self.request(f'/api/projects/{pid}')
            self.assertEqual(len(result['files']), 1)
            _, result2 = self.request(f'/api/projects/{other["id"]}')
            self.assertEqual(result2['files'], [])
            # HTTP 端点使用同一解析流程；同步执行以确定性检查结果。
            server.job(server.directory(pid), 'analyze')
            _, result = self.request(f'/api/projects/{pid}')
            self.assertEqual(result['fields'][0]['value'], '测试公司')
            self.assertGreater(result['chunk_count'], 0)

    def test_upload_preserves_old_reports_and_marks_update(self):
        with patch.dict(os.environ, {'APP_PASSWORD': ''}):
            _, project = self.request('/api/projects', {'name': '防止旧报告'})
            target = server.directory(project['id'])
            (target / 'report.docx').write_bytes(b'old')
            self.request(f'/api/projects/{project["id"]}/upload?name=input.txt', raw=b'new content')
            self.assertEqual((target / 'report.docx').read_bytes(), b'old')
            self.assertTrue(server.load(target / 'state.json')['report_outdated'])

    def test_download_allowlist_blocks_project_internal_files(self):
        with patch.dict(os.environ, {'APP_PASSWORD': ''}):
            _, project = self.request('/api/projects', {'name': '内部文件'})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request(f'/api/projects/{project["id"]}/download/state.json')
            self.assertEqual(ctx.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
