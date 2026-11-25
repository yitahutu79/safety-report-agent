import json,zipfile
from pathlib import Path
from PIL import Image
import pytest
from safety_report import report_appendices as a
from safety_report.word import write_docx

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def file(name='MSDS.pdf',ident='a'):
    return {'id':ident,'name':name,'stored':name,'sha256':'hash-'+ident,'active':True,'role':'source'}

def report(*titles):
    return {'confirmed_fields':[],'evidence':[],'sections':[{'id':'7','title':'7 附件','paragraphs':[{'text':t,'heading':'7 附件'} for t in titles],'subheadings':[],'tables':[],'missing':[],'review':[]}]}

def pdf(path,pages=2):
    from pypdf import PdfWriter
    writer=PdfWriter()
    for _ in range(pages):writer.add_blank_page(200,300)
    writer.write(path)


def test_all_original_pdf_pages_and_no_inactive_or_reference(tmp_path):
    (tmp_path/'uploads').mkdir();pdf(tmp_path/'uploads/MSDS.pdf',25);f=file()
    plan=a.build(tmp_path,report('附件5 化学品安全技术说明书'),[f])
    assert plan['matched']==1 and len(plan['items'][0]['assets'])==25
    assert [x['page'] for x in plan['items'][0]['assets']]==list(range(1,26))
    assert a.build(tmp_path,report('附件5 化学品安全技术说明书'),[{**f,'active':False}])['unresolved']==1
    assert a.build(tmp_path,report('附件5 化学品安全技术说明书'),[{**f,'role':'reference'}])['unresolved']==1
    assert a.build(tmp_path,report('附件5 化学品安全技术说明书'),[{**f,'appendix_mode':''}])['unresolved']==1


def test_page_titles_use_existing_exact_hash_analysis_and_correct_page(tmp_path):
    (tmp_path/'uploads').mkdir();pdf(tmp_path/'uploads/1总图.pdf',3);f=file('1总图.pdf')
    chunks=[{'source':f['name'],'sha256':f['sha256'],'locator':f'page[{n}]','text':title} for n,title in enumerate(['周边关系图','总平面布置图','厂区消防设施布置图'],1)]
    (tmp_path/'analysis.json').write_text(json.dumps({'chunks':chunks}))
    r=report('附图1 周边关系图','附图2 总平面布置图','附图3 厂区消防设施布置图');p=a.build(tmp_path,r,[f])
    assert p['matched']==3 and [x['assets'][0]['page'] for x in p['items']]==[1,2,3]
    assert all(len(x['assets'])==1 for x in p['items'])
    p=a.build(tmp_path,report('附图1 周边关系图'),[{**f,'sha256':'new'}]);assert p['unresolved']==1
    assert a.canonical('1#车间消防图')!=a.canonical('2#车间消防图')


def test_ambiguous_versions_not_silently_chosen(tmp_path):
    p=a.build(tmp_path,report('附件3 企业营业执照'),[file('营业执照.png','one'),file('企业营业执照.jpg','two')])
    assert p['items'][0]['status']=='ambiguous' and not p['items'][0]['assets']


def test_word_attachment_table_and_image_are_not_just_list_text(tmp_path):
    (tmp_path/'uploads').mkdir();image=tmp_path/'uploads/原图.png';Image.new('RGB',(100,80),'white').save(image)
    xml=f'<w:document xmlns:w="{W}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><w:body><w:p><w:r><w:t>附件1 安全设施一览表</w:t></w:r></w:p><w:tbl><w:tblGrid><w:gridCol w:w="1000"/></w:tblGrid><w:tr><w:tc><w:p><w:r><w:t>设施</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>防护罩</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>附件3 建设单位营业执照</w:t></w:r></w:p><w:p><w:r><w:drawing><a:blip r:embed="r1"/></w:drawing></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(tmp_path/'uploads/报告.docx','w') as z:
        z.writestr('word/document.xml',xml);z.writestr('word/media/img.png',image.read_bytes());z.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/img.png"/></Relationships>')
    f=file('报告.docx');r=report('附件1 安全设施一览表','附件3 建设单位企业营业执照');plan=a.build(tmp_path,r,[f])
    assert plan['matched']==2 and [x['assets'][0]['kind'] for x in plan['items']]==['table','image']
    figures=a.collect(tmp_path,plan,[f]);out=tmp_path/'out.docx';write_docx(r,{},out,figures)
    with zipfile.ZipFile(out) as z:
        text=z.read('word/document.xml').decode();assert '<w:tbl>' in text and '防护罩' in text
        assert len([n for n in z.namelist() if n.startswith('word/media/')])==1
    with pytest.raises(ValueError):a.collect(tmp_path,plan,[{**f,'sha256':'changed'}])


def test_explicit_appendix_setting_works_without_list_and_deduplicates(tmp_path):
    (tmp_path/'uploads').mkdir();pdf(tmp_path/'uploads/MSDS.pdf');f={**file(),'appendix_mode':'original_and_extract'}
    assert len(a.build(tmp_path,report('附件5 化学品安全技术说明书'),[f])['items'])==1
    assert len(a.build(tmp_path,report(),[f])['items'])==1
