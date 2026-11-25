"""Resolve attachment lists to local originals; never invent missing attachments or use a model."""
import hashlib,json,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from . import assets,document_images

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ENTRY=re.compile(r'^(附件|附图)\s*([0-9一二三四五六七八九十]+)\s*[:：、.．]?\s*(.+)$')

def appendix_section(section):
    return bool(re.match(r'^\s*(?:\d+[.、\s]*)?(?:附件|附录|附图)(?:\s|$|清单)',section.get('title','')))

def canonical(value):
    value=re.sub(r'^\d+(?=[^\d#])','',value.strip())
    value=re.sub(r'[\s\W_]+','',value).lower()
    groups=[('安全设施一览表','安全设施清单'),('建设项目区域位置图','区域位置图','地理位置图','建设项目地理位置图'),('建设单位企业营业执照','建设单位营业执照','企业营业执照','营业执照'),('建设项目登记备案证明','建设项目备案证明','山东省建设项目备案证明','备案证明'),('化学品安全技术说明书','危险物料msds','msds','化学品msds','安全技术说明书'),('总平面布置图','总图')]
    for group in groups:
        if value in group:return group[0]
    return value


def entries(report):
    result=[]
    for section in report.get('sections',[]):
        if not appendix_section(section):continue
        for paragraph in section.get('paragraphs',[]):
            for line in paragraph.get('text','').splitlines():
                match=ENTRY.fullmatch(line.strip())
                if match and len(line)<180:
                    title=line.strip();key=canonical(match[3]);ident=hashlib.sha256(title.encode()).hexdigest()[:20]
                    if not any(x['id']==ident for x in result):result.append({'id':ident,'title':title,'key':key,'section_title':section['title']})
    return result


def _file_assets(target,file):
    suffix=Path(file['stored']).suffix.lower()
    common={'file_id':file['id'],'source':file['name'],'sha256':file['sha256']}
    if suffix=='.pdf':
        from pypdf import PdfReader
        return [{**common,'kind':'page','page':i+1} for i in range(len(PdfReader(Path(target)/'uploads'/file['stored']).pages))]
    if suffix in assets.RASTER:return [{**common,'kind':'page','page':1}]
    return []


def _word_ranges(target,file):
    from .table_reuse import source_tables
    with zipfile.ZipFile(Path(target)/'uploads'/file['stored']) as z:body=list(ET.fromstring(z.read('word/document.xml')).find(W+'body'))
    headings=[]
    for index,node in enumerate(body):
        text=''.join(n.text or '' for n in node.iter(W+'t')).strip();match=ENTRY.fullmatch(text)
        if match and len(text)<180:headings.append((index,text,canonical(match[3])))
    if not headings:return []
    catalogue=document_images.catalog(target,file);tables={t['source_locator']:t for t in source_tables(target,[file])}
    pictures={}
    for item in catalogue['items']:pictures.setdefault(item['locator'].split('/')[0],[]).append(item)
    result=[];common={'file_id':file['id'],'source':file['name'],'sha256':file['sha256']}
    for hi,(start,title,key) in enumerate(headings):
        end=headings[hi+1][0] if hi+1<len(headings) else len(body);parts=[];warnings=[]
        # A list entry followed by another list entry has no actual content; skip it.
        for bi in range(start,end):
            loc='body['+str(bi)+']';node=body[bi];images=pictures.get(loc,[])
            if loc in tables:
                table=tables[loc]
                if table.get('reuse_supported',True):parts.append({**common,'kind':'table','locator':loc,'table':{k:table[k] for k in ('caption','headers','rows','source_table_layout')}})
                else:warnings.append(title+'：原表含复杂对象，需PDF原页以完整保留')
            for image in images:
                if image.get('supported'):parts.append({**common,'kind':'image','locator':image['locator'],'asset_id':image['id']})
                else:warnings.append(title+'：含不能独立还原的绘图，请核对或提供PDF原页')
            if any(w.startswith(loc+'：') for w in catalogue['warnings']):warnings.append(title+'：含组合绘图，独立位图不能保证保留全部叠加元素，请核对原件')
            text=''.join(n.text or '' for n in node.iter(W+'t')).strip()
            if bi>start and node.tag==W+'p' and not images and text and not re.match(r'^(表\s*\d|附图|附件)',text):parts.append({**common,'kind':'text','locator':loc,'text':text})
        if any(p['kind'] in {'table','image'} for p in parts):result.append({'key':key,'title':title,'assets':parts,'warnings':list(dict.fromkeys(warnings)),'source_file_id':file['id'],'source_locator':'body['+str(start)+']'})
    return result


def _analysed_pages(target,files):
    path=Path(target)/'analysis.json'
    if not path.exists():return {}
    try:chunks=json.loads(path.read_text()).get('chunks',[])
    except (ValueError,OSError):return {}
    pdfs={(f['name'],f['sha256']):f for f in files if Path(f['stored']).suffix.lower()=='.pdf'};titles={}
    for chunk in chunks:
        file=pdfs.get((chunk.get('source'),chunk.get('sha256')));match=re.fullmatch(r'page\[(\d+)\]',chunk.get('locator',''))
        if not file or not match:continue
        page=int(match[1])
        for line in chunk.get('text','').splitlines():
            line=line.strip()
            if '图' not in line or not 4<=len(line)<=100:continue
            key=canonical(line);entry={'file_id':file['id'],'source':file['name'],'sha256':file['sha256'],'kind':'page','page':page,'match_text':line}
            byfile=titles.setdefault(key,{}).setdefault(file['id'],{})
            byfile[page]=entry
    return titles


def build(target,report,files):
    active=[f for f in files if f.get('active',True) and f.get('role')!='reference' and f.get('appendix_mode',None)!=''];requested=entries(report);word=[];warnings=[]
    if requested:
        for file in active:
            if Path(file['stored']).suffix.lower()=='.docx':
                try:word.extend(_word_ranges(target,file))
                except Exception as exc:warnings.append(file['name']+'：附录识别失败（'+type(exc).__name__+'），请核对原件')
    page_titles=_analysed_pages(target,active)
    items=[];used=set()
    for entry in requested:
        item={**entry,'status':'missing','assets':[],'warnings':[]};matches=[f for f in active if canonical(Path(f['name']).stem)==entry['key']]
        title_matches=page_titles.get(entry['key'],{})
        if len(title_matches)==1:
            pages=next(iter(title_matches.values()));item['assets']=[pages[n] for n in sorted(pages)];used.add(item['assets'][0]['file_id'])
        elif len(title_matches)>1:item.update(status='ambiguous',warnings=['多个PDF包含同名图纸，请确认来源版本'])
        elif len(matches)==1:
            try:item['assets']=_file_assets(target,matches[0])
            except Exception as exc:item['warnings'].append('原件读取失败（'+type(exc).__name__+'）')
            if item['assets']:used.add(matches[0]['id'])
        elif len(matches)>1:item.update(status='ambiguous',warnings=['存在多个同名或同类原件，请核对使用版本'])
        if not item['assets'] and item['status']!='ambiguous':
            candidates=[w for w in word if w['key']==entry['key']]
            # Only the last actual attachment range in each file can match a repeated list title.
            candidates=list({w['source_file_id']:w for w in candidates}.values())
            if len(candidates)==1:item.update(assets=candidates[0]['assets'],warnings=candidates[0]['warnings'])
            elif len(candidates)>1:item.update(status='ambiguous',warnings=['多个Word原件包含此附件，请确认来源版本'])
        if item['assets']:item['status']='review' if item['warnings'] else 'ready'
        if not item['assets'] and not item['warnings']:item['warnings']=['没有找到能够明确对应的原件；清单文字不代表已附入文件']
        item['source_files']=list(dict.fromkeys(a['source'] for a in item['assets']));items.append(item)
    # Explicit original-appendix choices remain authoritative, including documents absent from the list.
    for file in active:
        if file.get('appendix_mode') and file['id'] not in used:
            try:parts=_file_assets(target,file)
            except Exception as exc:parts=[];warnings.append(file['name']+'：原件读取失败（'+type(exc).__name__+'）')
            if parts:items.append({'id':'file-'+file['id'],'title':file.get('caption') or file['name'],'key':'','section_title':'','status':'ready','assets':parts,'warnings':[],'source_files':[file['name']]});used.add(file['id'])
    return {'items':items,'warnings':warnings,'matched':sum(bool(x['assets']) for x in items),'unresolved':sum(not x['assets'] for x in items),'whole_file_ids':sorted(used)}


def collect(target,plan,files):
    byid={f['id']:f for f in files if f.get('active',True)};result=[]
    for item in plan['items']:
        for index,part in enumerate(item['assets'],1):
            file=byid.get(part['file_id'])
            if not file or file['sha256']!=part['sha256']:raise ValueError(item['title']+'：附件来源版本已变化，请重新组稿')
            base={'caption':item['title'],'attachment_title':item['title'],'source':file['name'],'original_appendix':True,'appendix_file_id':file['id'],'original_page':index,'original_page_count':len(item['assets']),'placement':{}}
            if part['kind']=='table':base['appendix_table']=part['table']
            elif part['kind']=='text':base['appendix_text']=part['text']
            elif part['kind']=='image':
                _,image=document_images.find(target,files,file['id'],part['asset_id']);base['path']=str(document_images.render(target,file,image))
            else:base['path']=str(assets.render_file(target,file,part['page']))
            result.append(base)
    return result
