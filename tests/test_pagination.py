import subprocess,zipfile
from pathlib import Path
import pytest
from pypdf import PdfWriter
from safety_report import pagination as p,versions
from safety_report.word import write_docx


def test_engine_unavailable_does_not_claim_computed_pages(tmp_path,monkeypatch):
    monkeypatch.setattr(p,'find_engine',lambda:None)
    source=tmp_path/'in.docx';source.write_bytes(b'original')
    result=p.paginate(source,force=True);assert result['status']=='unavailable' and not result.get('page_count')
    with pytest.raises(ValueError,match='排版组件'):p.paginate(source,required=True,force=True)
    assert source.read_bytes()==b'original'


@pytest.mark.parametrize('failure',['timeout','process','no_output','invalid_word'])
def test_renderer_failure_preserves_original_file(tmp_path,monkeypatch,failure):
    source=tmp_path/'in.docx';source.write_bytes(b'original');monkeypatch.setattr(p,'find_engine',lambda:'/engine/soffice')
    def run(command,env,timeout):
        if '--terminate_after_init' in command:return
        if failure=='timeout':raise subprocess.TimeoutExpired(command,timeout)
        if failure=='process':raise subprocess.CalledProcessError(1,command)
        if failure=='invalid_word':
            profile=Path(command[1].split('file://')[1]);root=profile.parent
            (root/'paginated.docx').write_bytes(b'broken');(root/'report.pdf').write_bytes(b'broken');(root/'result.txt').write_text('OK 2')
    monkeypatch.setattr(p,'_run',run)
    with pytest.raises((ValueError,zipfile.BadZipFile)):p.paginate(source,force=True)
    assert source.read_bytes()==b'original' and not source.with_suffix('.pdf').exists()


def test_actual_pdf_page_count_controls_metadata_and_macro_security_unchanged(tmp_path,monkeypatch):
    source=tmp_path/'in.docx';source.write_bytes(b'original');monkeypatch.setattr(p,'find_engine',lambda:'/engine/soffice')
    def run(command,env,timeout):
        if '--terminate_after_init' in command:return
        profile=Path(command[1].split('file://')[1]);root=profile.parent
        code=(profile/'user/basic/Standard/Pagination.xba').read_text()
        assert 'ShowOnlineLayout=False' in code and 'DocumentIndexes' in code and 'MacroExecutionMode' in code
        assert 'MacroSecurityLevel' not in code and 'python' not in ' '.join(command).lower()
        with zipfile.ZipFile(root/'paginated.docx','w') as z:z.writestr('word/document.xml','<document/>')
        writer=PdfWriter()
        for _ in range(3):writer.add_blank_page(200,300)
        writer.write(root/'report.pdf');(root/'result.txt').write_text('OK 999')
    monkeypatch.setattr(p,'_run',run);result=p.paginate(source,force=True)
    assert result['page_count']==3 and result['toc_updated'] and source.with_suffix('.pdf').exists()
    assert zipfile.is_zipfile(source)


def test_word_requests_print_layout_and_uses_dynamic_footer_fields(tmp_path):
    report={'confirmed_fields':[],'sections':[]};out=tmp_path/'out.docx';write_docx(report,{},out)
    with zipfile.ZipFile(out) as z:
        assert '<w:view w:val="print"' in z.read('word/settings.xml').decode()
        footer=z.read('word/footer1.xml').decode();assert ' PAGE ' in footer and ' NUMPAGES ' in footer
        assert 'rFooter' in z.read('word/document.xml').decode()


def test_version_publishes_matching_pdf_and_removes_stale_pdf(tmp_path):
    import json
    (tmp_path/'state.json').write_text(json.dumps({'report_version':''}));report={'confirmed_fields':[],'sections':[]}
    def export(r,out):write_docx(r,{},out);out.with_suffix('.pdf').write_bytes(b'new PDF')
    first=versions.commit(tmp_path,report,export)
    assert (tmp_path/'versions'/first['id']/'report.pdf').read_bytes()==b'new PDF'
    assert (tmp_path/'report.pdf').read_bytes()==b'new PDF'
    versions.commit(tmp_path,report,lambda r,out:write_docx(r,{},out))
    assert not (tmp_path/'report.pdf').exists()


def test_office_output_retains_cached_toc_and_explicit_print_view(tmp_path):
    source=tmp_path/'rendered.docx'
    with zipfile.ZipFile(source,'w') as z:
        z.writestr('word/settings.xml','<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:updateFields w:val="true"/></w:settings>')
        z.writestr('word/document.xml','cached TOC page 17')
    p._finish_docx_view(source)
    with zipfile.ZipFile(source) as z:
        settings=z.read('word/settings.xml').decode()
        assert '<w:view w:val="print"/>' in settings and '<w:updateFields w:val="false"/>' in settings
        assert z.read('word/document.xml')==b'cached TOC page 17'
