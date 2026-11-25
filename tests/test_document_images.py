import copy,json,zipfile,threading,urllib.request,urllib.error
from io import BytesIO
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest
from PIL import Image
from pypdf import PdfWriter
from safety_report import document_images as images,server,versions,assets
from safety_report.subsection_locks import set_lock,assert_unchanged

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
WP='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'


def make_docx(path,external=False):
    image=BytesIO();Image.new('RGB',(120,80),'red').save(image,format='PNG')
    drawing='<w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="示意图"/><a:graphic><a:blip r:embed="rId1"/><a:srcRect l="25000"/></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    document='<w:document xmlns:w="'+W+'" xmlns:a="'+A+'" xmlns:r="'+R+'" xmlns:wp="'+WP+'"><w:body><w:p><w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:r><w:t>1.1 工艺</w:t></w:r></w:p>'+drawing+'<w:p><w:r><w:t>图1 工艺示意图</w:t></w:r></w:p>'+drawing+'</w:body></w:document>'
    mode=' TargetMode="External"' if external else ''
    rel='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="'+R+'/image" Target="'+('https://example.invalid/private.png' if external else 'media/image1.png')+'"'+mode+'/></Relationships>'
    with zipfile.ZipFile(path,'w') as z:z.writestr('word/document.xml',document);z.writestr('word/_rels/document.xml.rels',rel);z.writestr('word/media/image1.png',image.getvalue())


def file(name='source.docx'):
    return {'id':'f1','name':name,'stored':name,'sha256':'hash','role':'source','active':True,'size':1,'renderable':name.endswith('.pdf')}


def report():
    return {'confirmed_fields':[],'sections':[{'id':'1','title':'1 概况','subheadings':['1.1 工艺','1.2 建筑'],'paragraphs':[{'heading':'1.1 工艺','text':'图前的工艺说明。','evidence_ids':[]},{'heading':'1.2 建筑','text':'后面的小节。','evidence_ids':[]}],'tables':[],'missing':[],'review':[]}],'evidence':[]}


def test_word_catalog_preserves_occurrences_and_caption_and_crop(tmp_path):
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx');f=file();catalog=images.catalog(tmp_path,f)
    assert len(catalog['items'])==2 and len({i['id'] for i in catalog['items']})==2
    item=catalog['items'][0];assert item['caption']=='图1 工艺示意图' and item['locator']=='body[1]/image[1]'
    png=images.render(tmp_path,f,item);assert Image.open(png).size==(90,80)
    assert images.render(tmp_path,f,item,True).exists()
    assert images.catalog(tmp_path,f)==catalog
    with pytest.raises(ValueError):images.find(tmp_path,[{**f,'active':False}],f['id'],item['id'])
    with pytest.raises(ValueError):images.find(tmp_path,[{**f,'sha256':'new'}],f['id'],item['id'])


def test_external_word_images_are_not_fetched(tmp_path):
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx',True)
    catalog=images.catalog(tmp_path,file());assert not catalog['items'] and catalog['warnings']


def test_pdf_embedded_images_and_vector_original_page_fallback(tmp_path):
    (tmp_path/'uploads').mkdir();Image.new('RGB',(120,80),'green').save(tmp_path/'uploads'/'image.pdf',format='PDF')
    f=file('image.pdf');catalog=images.catalog(tmp_path,f)
    assert {'image','page'}<={i['kind'] for i in catalog['items']}
    for item in catalog['items']:assert images.render(tmp_path,f,item).exists()
    writer=PdfWriter();writer.add_blank_page(200,300);writer.write(tmp_path/'uploads'/'vector.pdf')
    page=images.catalog(tmp_path,{**file('vector.pdf'),'id':'vector'})['items']
    assert len(page)==1 and page[0]['kind']=='page'


def test_insert_move_and_export_matches_paragraph_anchor_and_subsection(tmp_path):
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx');f=file();item=images.catalog(tmp_path,f)['items'][0];old=report()
    data={'section_id':'1','heading':'1.1 工艺','paragraph_index':0,'paragraph_text':'图前的工艺说明。','caption':'工艺流程图'}
    result=images.insert(old,item,data);assert not old['sections'][0].get('figures')
    figures=assets.resolve_figure_placements(result,images.collect(tmp_path,result,[f]))[0]
    out=tmp_path/'out.docx';server.write_docx(result,{},out,figures)
    with zipfile.ZipFile(out) as z:
        xml=z.read('word/document.xml').decode();assert xml.index('图前的工艺说明。')<xml.index('工艺流程图')<xml.index('后面的小节。')
        assert len([n for n in z.namelist() if n.startswith('word/media/')])==1
    fid=result['sections'][0]['figures'][0]['id']
    moved=images.insert(result,item,{'section_id':'1','heading':'1.2 建筑','caption':'建筑示意图','replace_figure_id':fid})
    assert len(moved['sections'][0]['figures'])==1 and moved['sections'][0]['figures'][0]['id']==fid
    assert moved['sections'][0]['figures'][0]['heading']=='1.2 建筑'
    with pytest.raises(ValueError):images.insert(old,item,{**data,'paragraph_text':'旧段落已修改。'})
    workflow={};set_lock(old,workflow,'1','1.1 工艺',True)
    with pytest.raises(ValueError):assert_unchanged(old,result,workflow)
    with pytest.raises(ValueError):images.collect(tmp_path,result,[{**f,'active':False}])


def test_stale_paragraph_moves_to_appendix_with_warning_without_losing_picture(tmp_path):
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx');f=file();item=images.catalog(tmp_path,f)['items'][0]
    result=images.insert(report(),item,{'section_id':'1','heading':'1.1 工艺','caption':'示意图','paragraph_index':0,'paragraph_text':'图前的工艺说明。'})
    result['sections'][0]['paragraphs'][0]['text']='新段落'
    resolved,warnings=assets.resolve_figure_placements(result,images.collect(tmp_path,result,[f]))
    assert warnings and resolved[0]['placement']=={} and Path(resolved[0]['path']).exists()


def test_subsection_end_image_exports_before_next_heading(tmp_path):
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx');f=file();item=images.catalog(tmp_path,f)['items'][0]
    result=images.insert(report(),item,{'section_id':'1','heading':'1.1 工艺','caption':'小节插图'})
    out=tmp_path/'out.docx';server.write_docx(result,{},out,images.collect(tmp_path,result,[f]))
    with zipfile.ZipFile(out) as z:
        xml=z.read('word/document.xml').decode();assert xml.index('图前的工艺说明。')<xml.index('小节插图')<xml.index('1.2 建筑')


def test_image_http_preview_insert_move_remove_stays_in_working_copy(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def req(path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body),timeout=5) as r:return json.load(r)
    try:
        pid=req('/api/projects',{'name':'文档插图隔离回归'})['id'];target=tmp_path/pid;route='/api/projects/'+pid;make_docx(target/'uploads'/'source.docx');f=file()
        old=report();meta=versions.commit(target,old,lambda r,p:server.write_docx(r,{},p));server.state_update(target,files=[f],report_version=meta['id'])
        data=req(route+'/source-images?file_id=f1');assert data['total']==2
        item=data['items'][0]
        with urllib.request.urlopen(base+route+'/source-images/'+item['id']+'/preview?file_id=f1&thumb=1') as r:assert r.read().startswith(b'\x89PNG')
        payload={'base_version':meta['id'],'working_revision':0,'file_id':'f1','asset_id':item['id'],'section_id':'1','heading':'1.1 工艺','caption':'选用图'}
        req(route+'/insert-source-image',payload);assert len(versions.history(target))==1
        draft=req(route+'/report')['report'];fig=draft['sections'][0]['figures'][0]
        with pytest.raises(urllib.error.HTTPError):req(route+'/insert-source-image',payload)
        req(route+'/insert-source-image',{**payload,'working_revision':1,'replace_figure_id':fig['id'],'heading':'1.2 建筑'})
        draft=req(route+'/report')['report'];assert len(draft['sections'][0]['figures'])==1 and draft['sections'][0]['figures'][0]['heading']=='1.2 建筑'
        req(route+'/remove-source-image',{'base_version':meta['id'],'working_revision':2,'section_id':'1','figure_id':fig['id']})
        assert not req(route+'/report')['report']['sections'][0]['figures'] and len(versions.history(target))==1
    finally:http.shutdown();http.server_close();thread.join(timeout=5)


def test_chapter_regeneration_preserves_user_inserted_figures(monkeypatch):
    from safety_report import pipeline
    class Index:
        client=None;semantic_error='离线'
        def __init__(self,*args,**kwargs):pass
        def search(self,*args,**kwargs):return []
        def close(self):pass
    monkeypatch.setattr(pipeline,'HybridEvidenceIndex',Index)
    old=report();old['template_sha256']='t';old['sections'][0]['figures']=[{'id':'chosen','heading':'1.1 工艺','asset_id':'asset','caption':'用户保留的工艺图'}]
    profile={'sha256':'t','headings':[{'text':'1 概况','level':1,'subheadings':['1.1 工艺','1.2 建筑']}]}
    result=pipeline.generate(profile,{'chunks':[]},[],False,previous=old,chapter_ids=['1'])
    assert result['sections'][0]['figures']==old['sections'][0]['figures']


def test_picture_only_subsection_can_be_confirmed_without_inventing_text():
    r=report();r['sections'][0]['paragraphs']=[];r['sections'][0]['figures']=[{'id':'picture','heading':'1.1 工艺','caption':'工艺示意图'}]
    workflow={};set_lock(r,workflow,'1','1.1 工艺',True)
    assert workflow['subsections']['1']['1.1 工艺']['locked']


def test_picture_and_table_are_between_paragraphs_in_same_subsection(tmp_path):
    from safety_report.content_order import paragraph_anchor
    (tmp_path/'uploads').mkdir();make_docx(tmp_path/'uploads'/'source.docx');f=file();item=images.catalog(tmp_path,f)['items'][0]
    old=report();section=old['sections'][0];section['paragraphs'].insert(1,{'heading':'1.1 工艺','text':'图后的工艺解释。','evidence_ids':[]})
    result=images.insert(old,item,{'section_id':'1','heading':'1.1 工艺','caption':'段中工艺图','paragraph_index':0,'paragraph_text':'图前的工艺说明。'})
    result['sections'][0]['tables']=[{'heading':'1.1 工艺','caption':'段中设备表','headers':['设备'],'rows':[['印刷机']], 'insertion_order':2,**paragraph_anchor(result['sections'][0],'1.1 工艺',0,'图前的工艺说明。')}]
    figures=assets.resolve_figure_placements(result,images.collect(tmp_path,result,[f]))[0]
    out=tmp_path/'inline.docx';server.write_docx(result,{},out,figures)
    with zipfile.ZipFile(out) as z:xml=z.read('word/document.xml').decode()
    assert xml.index('图前的工艺说明。')<xml.index('段中工艺图')<xml.index('段中设备表')<xml.index('图后的工艺解释。')<xml.index('后面的小节。')
