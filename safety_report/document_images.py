"""Local source-image catalogue and explicit report insertion using existing PDF/PIL tooling."""
import copy,hashlib,json,posixpath,zipfile,threading
from functools import wraps
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
from . import assets

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
WP='{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
V='{urn:schemas-microsoft-com:vml}'
P='{http://schemas.openxmlformats.org/package/2006/relationships}'
REVISION=1
_IMAGE_LOCK=threading.RLock()
def serialized(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        with _IMAGE_LOCK:return fn(*args,**kwargs)
    return call


def _id(file,locator):return hashlib.sha256((file['id']+file['sha256']+locator).encode()).hexdigest()[:32]


@serialized
def catalog(target,file):
    if not file.get('active',True):raise ValueError('来源文件已停用')
    path=Path(target)/'uploads'/file['stored'];suffix=path.suffix.lower()
    if suffix not in {'.docx','.pdf'}:raise ValueError('文档图片库支持Word DOCX和PDF；独立图片可在图件与位置中管理')
    cache=Path(target)/'source-images'/file['id'];cache.mkdir(parents=True,exist_ok=True);manifest=cache/'manifest.json'
    if manifest.exists():
        old=json.loads(manifest.read_text(encoding='utf-8'))
        if old.get('sha256')==file['sha256'] and old.get('revision')==REVISION:return old
    items=[];warnings=[]
    def add(locator,**data):
        items.append({'id':_id(file,locator),'source_file_id':file['id'],'source_sha256':file['sha256'],
                      'source_file':file['name'],'locator':locator,'supported':True,**data})
    if suffix=='.docx':
        from .documents import read_docx
        blocks,_=read_docx(path);known={b['locator']:b for b in blocks};heading=''
        with zipfile.ZipFile(path) as z:
            relationships={n.get('Id'):n for n in ET.fromstring(z.read('word/_rels/document.xml.rels'))} if 'word/_rels/document.xml.rels' in z.namelist() else {}
            body=ET.fromstring(z.read('word/document.xml')).find(W+'body')
            for bi,block in enumerate(body):
                origin='body['+str(bi)+']';meta=known.get(origin,{})
                if meta.get('level') in (1,2,3):heading=meta['text']
                following=known.get('body['+str(bi+1)+']',{}).get('text','')
                import re
                caption=following if re.match(r'^图\s*\d',following) else ''
                nodes=list(block.iter(W+'drawing'))+list(block.iter(W+'pict'))
                for ni,node in enumerate(nodes):
                    blip=node.find('.//'+A+'blip');vml=node.find('.//'+V+'imagedata')
                    rid=blip.get(R+'embed') if blip is not None else vml.get(R+'id') if vml is not None else None
                    rel=relationships.get(rid)
                    if rel is None or rel.get('TargetMode')=='External' or not rel.get('Type','').endswith('/image'):
                        warnings.append(origin+'：绘图不是独立内嵌位图或引用外链；可转PDF使用原页。');continue
                    resource=rel.get('Target','');resource=posixpath.normpath(resource.lstrip('/') if resource.startswith('/') else 'word/'+resource)
                    if resource.startswith('../') or resource not in z.namelist():warnings.append(origin+'：图片资源无效');continue
                    ext=Path(resource).suffix.lower();supported=ext in assets.RASTER
                    docpr=node.find('.//'+WP+'docPr');alt=(docpr.get('descr') or docpr.get('title') or '') if docpr is not None else ''
                    crop=node.find('.//'+A+'srcRect');transform=node.find('.//'+A+'xfrm')
                    add(origin+'/image['+str(ni+1)+']',kind='image',format='docx',resource=resource,
                        caption=(caption or alt or '文档图片 '+str(len(items)+1))[:160],source_heading=heading,supported=supported,
                        warning='' if supported else '该矢量/特殊图片暂不能独立转换，请转PDF使用原页',
                        crop=dict(crop.attrib) if crop is not None else {},transform=dict(transform.attrib) if transform is not None else {})
    else:
        from pypdf import PdfReader
        reader=PdfReader(path)
        for pi,page in enumerate(reader.pages,1):
            try:
                keys=page.images.keys()
                for ii,key in enumerate(keys,1):add('page['+str(pi)+']/image['+str(ii)+']',kind='image',format='pdf',page=pi,resource=key,caption='第'+str(pi)+'页图片 '+str(ii),source_heading='',warning='内嵌位图可能是组合图的一部分；完整图文请选原页。')
            except Exception as exc:warnings.append('第'+str(pi)+'页图片识别失败（'+type(exc).__name__+'），仍可使用原页。')
            add('page['+str(pi)+']',kind='page',format='pdf',page=pi,caption='第'+str(pi)+'页原图',source_heading='')
    result={'sha256':file['sha256'],'revision':REVISION,'items':items,'warnings':list(dict.fromkeys(warnings))}
    pending=cache/'manifest.tmp';pending.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(manifest);return result


def find(target,files,file_id,asset_id):
    file=next((f for f in files if f['id']==file_id and f.get('active',True)),None)
    if not file:raise ValueError('来源文件不存在或已停用')
    item=next((i for i in catalog(target,file)['items'] if i['id']==asset_id),None)
    if not item:raise ValueError('来源图片不存在或版本已变化')
    return file,item


@serialized
def render(target,file,item,thumbnail=False):
    from PIL import Image,ImageOps
    if not item.get('supported'):raise ValueError(item.get('warning','图片暂不能转换'))
    if item['source_sha256']!=file['sha256']:raise ValueError('来源图片版本已变化')
    folder=Path(target)/'source-images'/file['id'];folder.mkdir(parents=True,exist_ok=True)
    output=folder/(item['id']+('-thumb' if thumbnail else '')+'.png')
    if output.exists():return output
    if thumbnail:
        full=render(target,file,item,False)
        with Image.open(full) as image:
            image.thumbnail((480,360));image.save(output)
        return output
    if item['kind']=='page':
        source=assets.render_file(target,file,item['page']);output.write_bytes(source.read_bytes());return output
    path=Path(target)/'uploads'/file['stored']
    if item['format']=='docx':
        with zipfile.ZipFile(path) as z:data=z.read(item['resource'])
    else:
        from pypdf import PdfReader
        key=item['resource'];key=tuple(key) if isinstance(key,list) else key
        data=PdfReader(path).pages[item['page']-1].images[key].data
    Image.MAX_IMAGE_PIXELS=60_000_000
    with Image.open(BytesIO(data)) as original:
        if original.width*original.height>60_000_000:raise ValueError('图片像素过大，请缩小后重新上传')
        image=ImageOps.exif_transpose(original).convert('RGBA')
        crop=item.get('crop',{})
        if crop:
            l,t,r,b=[int(crop.get(k,0))/100000 for k in ('l','t','r','b')]
            box=(max(0,round(image.width*l)),max(0,round(image.height*t)),min(image.width,round(image.width*(1-r))),min(image.height,round(image.height*(1-b))))
            if box[2]<=box[0] or box[3]<=box[1]:raise ValueError('原图裁切参数无效，请使用原页')
            image=image.crop(box)
        transform=item.get('transform',{})
        if transform.get('flipH') in {'1','true'}:image=ImageOps.mirror(image)
        if transform.get('flipV') in {'1','true'}:image=ImageOps.flip(image)
        if transform.get('rot'):image=image.rotate(-int(transform['rot'])/60000,expand=True)
        image.thumbnail((4000,4000));background=Image.new('RGB',image.size,'white');background.paste(image,mask=image.getchannel('A'));background.save(output)
    return output


def insert(report,item,data):
    import uuid
    from .pipeline import section_identity
    result=copy.deepcopy(report);section=next((s for s in result['sections'] if section_identity(s)==data.get('section_id')),None)
    if not section:raise ValueError('请选择当前报告章节')
    heading=data.get('heading',section['title'])
    if heading not in [section['title']]+section.get('subheadings',[]):raise ValueError('小节已变化，请重新选择')
    caption=data.get('caption',item['caption'])
    if not isinstance(caption,str) or not 1<=len(caption.strip())<=160:raise ValueError('请填写1至160字图题')
    from .content_order import paragraph_anchor,next_insertion_order
    anchor=paragraph_anchor(section,heading,data.get('paragraph_index'),data.get('paragraph_text'))
    eid='source-image-'+item['id']
    replacement=data.get('replace_figure_id')
    if replacement:
        matches=[f for s in result['sections'] for f in s.get('figures',[]) if f['id']==replacement]
        if len(matches)!=1:raise ValueError('需要调整的图件已变化，请刷新')
        for s in result['sections']:s['figures']=[f for f in s.get('figures',[]) if f['id']!=replacement]
    figure={'id':replacement or uuid.uuid4().hex,'asset_id':item['id'],'source_file_id':item['source_file_id'],'source_sha256':item['source_sha256'],
            'source_file':item['source_file'],'source_locator':item['locator'],'caption':caption.strip(),'heading':heading,'insertion_order':next_insertion_order(section),'evidence_ids':[eid],**anchor}
    section.setdefault('figures',[]).append(figure)
    if not any(e['id']==eid for e in result.setdefault('evidence',[])):result['evidence'].append({'id':eid,'source':item['source_file'],'sha256':item['source_sha256'],
        'source_file_id':item['source_file_id'],'locator':item['locator'],'text':'来源图件：'+item['source_file']+' '+item['locator'],'corpus':'project_evidence','evidence_type':'source_image','original_verified':False})
    result['updated_chapters']=[data['section_id']];return result


def collect(target,report,files):
    from .pipeline import section_identity
    result=[]
    for section in report.get('sections',[]):
        for figure in section.get('figures',[]):
            file,item=find(target,files,figure['source_file_id'],figure['asset_id'])
            if figure['source_sha256']!=file['sha256']:raise ValueError('已插入图片的来源版本已变化，请重新选择')
            location={'section_id':section_identity(section),'heading':figure['heading']}
            if 'paragraph_index' in figure:location.update({k:figure[k] for k in ('paragraph_index','paragraph_hash')})
            result.append({'path':str(render(target,file,item)),'caption':figure['caption'],'source':'','placement':location,'source_image':True,'document_figure_id':figure['id']})
    return result
