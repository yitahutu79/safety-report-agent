import hashlib
from unittest.mock import Mock, patch

from safety_report.documents import parse_file
from safety_report.pipeline import analyze


def test_pdf_failed_page_does_not_discard_other_pages(tmp_path):
    path = tmp_path / 'test.pdf'
    path.write_bytes(b'fixture')
    class Page:
        def __init__(self, value): self.value = value
        def extract_text(self):
            if isinstance(self.value, Exception):
                raise self.value
            return self.value
    class Reader:
        def __init__(self, path):
            self.pages = [Page('测试资料正文' * 10), Page(ValueError('too complex')), Page('下一页资料正文' * 10)]
    with patch('pypdf.PdfReader', Reader):
        result = parse_file(path)
    assert [block['locator'] for block in result['blocks']] == ['page[1]', 'page[3]']
    assert len(result['chunks']) == 2
    assert any('第 2 页文本提取失败' in warning for warning in result['warnings'])


def test_ocr_reprocesses_cached_scan_and_recovers_candidate_fields(tmp_path):
    path = tmp_path / '备案.pdf'
    path.write_bytes(b'fixture')
    old_document = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'file': path.name, 'chunks': []}
    reader = Mock()
    reader.pages = [Mock(extract_text=lambda: ''), Mock(extract_text=lambda: '可直接提取的项目说明' * 5)]
    recognized = '山东省建设项目备案证明\n单位名称\n测试工程有限公司\n项目名称\n先进制造产业园一期建设项目'

    with patch('pypdf.PdfReader', return_value=reader), patch(
        'safety_report.documents.recognize_pdf_page', return_value=recognized
    ) as ocr:
        result = analyze([path], {'documents': [old_document]})
        refreshed = analyze([path], result)

    ocr.assert_called_once_with(path, 0)
    assert result['documents'][0]['ocr_pages'] == [1]
    assert refreshed['reused_documents'] == 1
    assert [chunk['locator'] for chunk in result['chunks']] == ['page[1]', 'page[2]']
    fields = {field['key']: field for field in result['fields']}
    assert fields['company']['value'] == '测试工程有限公司'
    assert fields['project']['value'] == '先进制造产业园一期建设项目'
    assert not fields['company']['confirmed']
    assert fields['project']['candidates'][0]['method'] == 'ocr'
