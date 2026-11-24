from unittest.mock import patch,Mock
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image
from safety_report import assets,server
from safety_report.ocr import ordered_ocr_text
from safety_report.word import write_docx
from safety_report.project_intake import automatic_candidates
from safety_report.structured_data import report_evidence


def test_ocr_spatial_order_keeps_left_label_before_right_value():
    def box(x,y):return [[x,y],[x+90,y],[x+90,y+15],[x,y+15]]
    assert ordered_ocr_text(['易燃液体 类别2','警示词','危险','GHS类别','紧急情况概述'],[box(300,60),box(10,100),box(300,101),box(10,60),box(10,20)]).splitlines()==['紧急情况概述','GHS类别    易燃液体 类别2','警示词    危险']


def test_original_appendix_keeps_every_page_beyond_figure_limit(tmp_path):
    image=tmp_path/'page.png';Image.new('RGB',(200,300),'white').save(image)
    file={'id':'sds','stored':'sds.pdf','sha256':'h','name':'SDS.pdf','appendix_mode':'original','pages':'1','include':True,'figure_placement':{'section_id':'1'}}
    reader=Mock();reader.pages=[object() for _ in range(24)]
    with patch('pypdf.PdfReader',return_value=reader),patch('safety_report.assets.render_file',return_value=image) as render:
        pages=assets.collect_original_appendices(tmp_path,[file])
        assert len(pages)==24 and [p['original_page'] for p in pages]==list(range(1,25))
        assert render.call_count==24 and all(p['placement']=={} for p in pages)
        assert not assets.collect_figures(tmp_path,[file])[0]
        assert not assets.collect_original_appendices(tmp_path,[{**file,'active':False}])
    out=tmp_path/'report.docx'
    write_docx({'confirmed_fields':[],'sections':[]}, {},out,pages)
    with zipfile.ZipFile(out) as z:
        doc=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        assert len(doc.findall('.//w:drawing',ns))==24
        assert len(doc.findall('.//w:br[@w:type="page"]',ns))==24
        assert len([n for n in z.namelist() if n.startswith('word/media/')])==24
        assert all(z.read(n)==image.read_bytes() for n in z.namelist() if n.startswith('word/media/'))
        assert '附录' in ''.join(doc.itertext())


def test_appendix_only_does_not_become_structured_evidence():
    f={'id':'f','stored':'s.pdf','name':'s.pdf','sha256':'h','role':'source','appendix_mode':'original'}
    assert not server.is_text_source(f)
    assert automatic_candidates({'chunks':[{'id':'e','sha256':'h','locator':'p1','text':'GB 50016-2014 建筑设计防火规范'}]},[f])[0]==[]
    assert report_evidence([{'id':'r','status':'reviewed','file_id':'f','source_sha256':'h'}],[f])==[]
    assert server.is_text_source({**f,'appendix_mode':'original_and_extract'})


def test_pdf_prefers_layout_over_content_stream_order(tmp_path):
    from safety_report.documents import parse_file
    p=tmp_path/'source.pdf';p.write_bytes(b'test')
    page=Mock();page.extract_text.return_value='紧急情况概述：高度易燃。\nGHS危险性类别：易燃液体类别2。'*2
    with patch('pypdf.PdfReader',return_value=Mock(pages=[page])):
        parsed=parse_file(p)
    page.extract_text.assert_called_once_with(extraction_mode='layout',layout_mode_space_vertically=False)
    assert parsed['blocks'][0]['text'].startswith('紧急情况概述')
