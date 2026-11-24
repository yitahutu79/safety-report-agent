import io
import json
import threading
import zipfile
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
from safety_report import server
from safety_report.report_template import parse_report_template, validate_headings
from safety_report.word import write_docx

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def template_bytes():
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:
        z.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:pPr><w:pStyle w:val="H1"/></w:pPr><w:r><w:t>1 项目资料</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="H2"/></w:pPr><w:r><w:t>1.1 工程范围</w:t></w:r></w:p>
        <w:p><w:r><w:t>原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。原项目内容不得作为新项目事实。</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="H1"/></w:pPr><w:r><w:t>9 其他资料</w:t></w:r></w:p>
        <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:left="1800" w:right="1200" w:bottom="1440"/></w:sectPr></w:body></w:document>''')
        z.writestr('word/styles.xml','''<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:eastAsia="仿宋"/><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:styleId="H1"><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="32"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="H2"><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style></w:styles>''')
    return data.getvalue()


def test_template_directory_and_export_style_without_source_content(tmp_path):
    template=tmp_path/'template.docx';template.write_bytes(template_bytes())
    profile=parse_report_template(template)
    assert [h['text'] for h in profile['headings']]==['1 项目资料','1.1 工程范围','9 其他资料']
    from safety_report.report_template import approved_reuse_evidence
    assert profile['body_blocks'] and not approved_reuse_evidence(profile)
    report={'confirmed_fields':[],'structure_confirmed':True,'sections':[{'title':'1 项目资料','subheadings':['1.1 工程范围'],'paragraphs':[{'heading':'1.1 工程范围','text':'当前项目正文'}],'tables':[]}]}
    output=tmp_path/'report.docx';write_docx(report,profile,output)
    with zipfile.ZipFile(output) as z:
        doc=ET.fromstring(z.read('word/document.xml'));styles=ET.fromstring(z.read('word/styles.xml'))
        assert doc.find('.//w:pgSz',NS).get('{'+NS['w']+'}w')=='12240'
        normal=next(s for s in styles.findall('w:style',NS) if s.get('{'+NS['w']+'}styleId')=='Normal')
        assert normal.find('w:rPr/w:rFonts',NS).get('{'+NS['w']+'}eastAsia')=='仿宋'
        assert '原项目内容' not in z.read('word/document.xml').decode()


def test_template_upload_preview_apply_reset_and_report_preservation(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None,raw=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as response:return json.load(response)
    try:
        pid=req('/api/projects',{'name':'模板回归'})['id'];route='/api/projects/'+pid;target=tmp_path/pid
        old={'sections':[],'template_sha256':'old-template'};server.save(target/'report.json',old)
        default=req('/api/template?project_id='+pid)
        candidate=req(route+'/template-upload?name=template.docx',raw=template_bytes())['candidate']
        assert req('/api/template?project_id='+pid)==default  # Preview alone does not apply.
        assert req(route)['files']==[]
        with pytest.raises(urllib.error.HTTPError):req(route+'/template-apply',{'sha256':'stale','headings':candidate['headings']})
        req(route+'/template-apply',{'sha256':candidate['sha256'],'headings':candidate['headings']})
        assert req('/api/template?project_id='+pid)['headings']==candidate['headings']
        assert server.template_compatible_report(target) is None
        assert server.load(target/'report.json')==old
        state=req(route);assert state['report_template']['name']=='template.docx'
        server.state_update(target,busy=True)
        with pytest.raises(urllib.error.HTTPError):req(route+'/template-reset',{})
        server.state_update(target,busy=False)
        req(route+'/template-reset',{})
        assert req('/api/template?project_id='+pid)==default
        assert server.load(target/'report.json')==old
    finally:
        http.shutdown();http.server_close();thread.join(timeout=5)


def test_template_rejects_duplicate_or_unparented_headings():
    with pytest.raises(ValueError):validate_headings([{'text':'1.1 子节','level':2}])
    with pytest.raises(ValueError):validate_headings([{'text':'1 一','level':1},{'text':'1 二','level':1}])
