from unittest.mock import patch

from safety_report.documents import parse_file


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
