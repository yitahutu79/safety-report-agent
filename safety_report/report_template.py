"""Project-local report templates: structural/style data only, never project facts."""
import copy
import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from .documents import read_docx, W, NS

# Copy only self-contained formatting properties; no relationships, fields or macros.
P_PROPS = {'jc','spacing','ind','keepNext','keepLines','pageBreakBefore','widowControl','contextualSpacing'}
R_PROPS = {'rFonts','sz','szCs','b','bCs','i','iCs','color','kern'}


def safe_properties(node, allowed, tag):
    dest=ET.Element(W+tag)
    if node is not None:
        for child in node:
            if child.tag.removeprefix(W) in allowed:
                # Properties only, never carry content or external references.
                clean=ET.SubElement(dest,child.tag)
                clean.attrib.update({k:v for k,v in child.attrib.items() if k.startswith(W)})
    return dest


def parse_report_template(path):
    blocks, info=read_docx(path)
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('word/document.xml'))
        styles_root=ET.fromstring(z.read('word/styles.xml')) if 'word/styles.xml' in z.namelist() else ET.Element(W+'styles')
    style_nodes={s.get(W+'styleId'):s for s in styles_root.findall('w:style',NS)}
    body=list(root.find('w:body',NS))
    headings=[]; seen=set();samples={}
    for b in blocks:
        if b['kind']!='paragraph':continue
        text=b['text'];level=b.get('level');sid=b.get('style_id','')
        # TOC entries may use heading-like formatting; never ingest their cached text.
        if 'toc' in sid.lower() or '目录' in b.get('style_name',''):continue
        if level and 1<=level<=3 and re.match(r'^\d+(?:\.\d+)*\s*[^\d.\s]',text) and len(text)<=180:
            number=re.match(r'\d+(?:\.\d+)*',text).group()
            if number not in seen:
                headings.append({'text':text,'level':level});seen.add(number)
                samples.setdefault('Heading'+str(level),(sid,body[int(re.search(r'\d+',b['locator']).group())]))
        elif not level and len(text)>=100 and not re.match(r'^(?:图|表|附)',text):
            samples.setdefault('Normal',(sid,body[int(re.search(r'\d+',b['locator']).group())]))
    validate_headings(headings)
    table_schemas=[]; current_heading=''; caption=''
    heading_texts={h['text'] for h in headings}
    for block in blocks:
        if block['kind']=='paragraph':
            if block['text'] in heading_texts:current_heading=block['text']
            if re.match(r'^表\s*\d',block['text']):caption=block['text'][:180]
        elif block.get('rows') and current_heading:
            table_schemas.append({'heading':current_heading,'caption':caption,'headers':[str(v)[:120] for v in block['rows'][0][:20]]})
            caption=''
    formats={}
    defaults=styles_root.find('w:docDefaults',NS)
    for role, (sid, paragraph) in samples.items():
        p=ET.Element(W+'pPr');r=ET.Element(W+'rPr')
        def merge(dest,source,allowed):
            for prop in safe_properties(source,allowed,'unused'):
                existing=dest.find(prop.tag)
                if existing is not None:dest.remove(existing)
                dest.append(copy.deepcopy(prop))
        if defaults is not None:
            merge(p,defaults.find('w:pPrDefault/w:pPr',NS),P_PROPS)
            merge(r,defaults.find('w:rPrDefault/w:rPr',NS),R_PROPS)
        chain=[];current=sid
        while current in style_nodes and current not in chain:
            chain.append(current);parent=style_nodes[current].find('w:basedOn',NS)
            current=parent.get(W+'val') if parent is not None else ''
        for key in reversed(chain):
            merge(p,style_nodes[key].find('w:pPr',NS),P_PROPS)
            merge(r,style_nodes[key].find('w:rPr',NS),R_PROPS)
        merge(p,paragraph.find('w:pPr',NS),P_PROPS)
        first=paragraph.find('w:r/w:rPr',NS)
        merge(r,first,R_PROPS)
        formats[role]={'pPr':ET.tostring(p,encoding='unicode'),'rPr':ET.tostring(r,encoding='unicode')}
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'headings':headings,
            'sections':info['sections'][:1],'paragraph_formats':formats,'table_schemas':table_schemas[:100],
            'body_blocks':extract_body_blocks(blocks,headings,hashlib.sha256(path.read_bytes()).hexdigest()),'content_revision':0,
            'table_count':sum(b['kind']=='table' for b in blocks),'image_resources':info['image_resources'],
            'limitations':['采用首个分节的纸张和页边距及可识别的正文/标题样式；复杂封面、多分节、页眉页脚和原表格布局暂不复刻。',
                           '模板正文须单独审核适用性后才能复用；图片及原项目事实不自动带入新报告。']}


def validate_headings(headings):
    if not isinstance(headings,list) or not 1<=len(headings)<=200:raise ValueError('模板需包含1至200个章节标题；请用 Word 标题样式设置章节')
    numbers=set();parents=set()
    for h in headings:
        if not isinstance(h,dict) or h.get('level') not in (1,2,3) or not isinstance(h.get('text'),str):raise ValueError('章节格式无效')
        text=h['text'];m=re.match(r'^(\d+(?:\.\d+)*)\s*[^\d.\s]',text)
        if not m or len(text)>180 or '\n' in text:raise ValueError('标题须采用1、1.1、1.1.1等编号，最多180字')
        num=m.group(1)
        if len(num.split('.'))!=h['level'] or num in numbers:raise ValueError('标题层级与编号不一致，或编号重复')
        if '.' in num and num.rsplit('.',1)[0] not in numbers:raise ValueError('子标题前缺少对应父标题')
        numbers.add(num)
        if h['level']==1:parents.add(num)
    if not parents:raise ValueError('模板未识别出主章节，请使用 Word 标题1样式')


def apply_paragraph_formats(styles_xml, formats):
    root=ET.fromstring(styles_xml)
    for style in root.findall('w:style',NS):
        role=style.get(W+'styleId');fmt=formats.get(role)
        if role not in {'Normal','Heading1','Heading2','Heading3'} or not fmt:continue
        for key,allowed in [('pPr',P_PROPS),('rPr',R_PROPS)]:
            node=style.find('w:'+key,NS)
            if node is None:node=ET.SubElement(style,W+key)
            incoming=safe_properties(ET.fromstring(fmt[key]),allowed,key)
            for prop in incoming:
                old=node.find(prop.tag)
                if old is not None:node.remove(old)
                node.append(copy.deepcopy(prop))
    return ET.tostring(root,encoding='unicode')


def reuse_risks(text):
    """Conservative flags, not a professional applicability assessment."""
    patterns = [(r'本项目|该项目|本公司|该公司|有限公司|本厂|该厂','项目主体或项目现状'),
                (r'GB\s*[/T]*\s*\d|AQ\s*[/T]*\s*\d|主席令|公告|令第|实施日期|20\d{2}年','法规标准或日期'),
                (r'\d+(?:\.\d+)?\s*(?:万元|万吨|吨/年|m[²³23]|MPa|kV|V|mA|Ω|欧姆|℃|台|米)|图\s*\d|表\s*\d','参数或图表编号'),
                (r'符合.{0,20}(?:要求|规定|标准)|不构成重大危险源|已(?:安装|落实|建成|验收)','专业结论或完成状态')]
    return [label for pattern,label in patterns if re.search(pattern,text,re.I)]


def extract_body_blocks(blocks, headings, digest):
    current=''; result=[];titles={h['text'] for h in headings}
    for b in blocks:
        if b['kind']!='paragraph':continue
        if b['text'] in titles:current=b['text'];continue
        if not current or 'toc' in b.get('style_id','').lower() or re.match(r'^[图表]\s*\d',b['text']):continue
        text=b['text']
        if not 15<=len(text)<=12000:continue
        result.append({'id':'tpl-'+hashlib.sha256((digest+b['locator']).encode()).hexdigest()[:20],
                       'heading':current,'locator':b['locator'],'original_text':text,'text':text,
                       'decision':'reference','reviewed':False,'applicability':'','risks':reuse_risks(text)})
    return result


def review_body_block(profile, data):
    blocks=profile.get('body_blocks',[])
    block=next((b for b in blocks if b['id']==data.get('id')),None)
    if not block:raise ValueError('模板段落不存在，请刷新')
    if data.get('expected_revision')!=profile.get('content_revision',0):raise ValueError('模板正文已更新，请刷新后再审核')
    decision=data.get('decision');text=data.get('text');applicability=data.get('applicability','')
    if decision not in {'direct','adapt','reference','exclude'} or not isinstance(text,str) or not 1<=len(text.strip())<=12000:raise ValueError('段落复用方式或正文无效')
    if not isinstance(applicability,str) or len(applicability)>1000:raise ValueError('适用条件最多1000字')
    if decision in {'direct','adapt'} and (data.get('applicability_confirmed') is not True or not applicability.strip()):raise ValueError('请填写适用条件，并确认已核对当前项目适用性')
    risks=reuse_risks(text)
    if decision=='direct' and risks:raise ValueError('段落含'+ '、'.join(risks)+'，请按项目调整后审核，或选择结合项目改写')
    block.update(text=text.strip(),decision=decision,reviewed=decision in {'direct','adapt'},
                 applicability=applicability.strip(),risks=risks)
    profile['content_revision']=profile.get('content_revision',0)+1
    return block


def approved_reuse_evidence(profile, headings=None):
    result=[]
    for b in profile.get('body_blocks',[]):
        if headings is not None and b['heading'] not in headings:continue
        if not b.get('reviewed') or b.get('decision') not in {'direct','adapt'} or not b.get('applicability'):continue
        if b['decision']=='direct' and reuse_risks(b['text']):continue
        digest=hashlib.sha256(b['text'].encode()).hexdigest()[:12]
        result.append({'id':b['id']+'-'+digest,'text':b['text'],'source':b.get('source_file') or '报告模板：'+profile.get('name','模板'),
                       'locator':b['locator'],'heading':b['heading'],'corpus':'reviewed_template',
                       'reuse_decision':b['decision'],'reuse_reviewed':True,'applicability':b['applicability'],
                       'source_template_sha256':b.get('source_sha256') or profile.get('source_sha256',profile['sha256'])})
    return result


def exact_approved_reuse(paragraph,evidence):
    ids=set(paragraph.get('evidence_ids',[]))
    return any(e.get('id') in ids and e.get('corpus')=='reviewed_template' and e.get('reuse_reviewed') is True
               and e.get('reuse_decision')=='direct' and e.get('applicability') and not reuse_risks(e.get('text',''))
               and e.get('heading')==paragraph.get('heading') and e.get('text','').strip()==paragraph.get('text','').strip()
               for e in evidence)


def insert_approved_fixed_text(draft,evidence):
    """Assemble human-approved fixed paragraphs deterministically, without rewriting."""
    approved=[e for e in evidence if e.get('reuse_decision')=='direct'
              and exact_approved_reuse({'text':e['text'],'heading':e['heading'],'evidence_ids':[e['id']]},[e])]
    fixed_ids={e['id'] for e in approved}
    # Model paragraphs citing only fixed text are replaced by the approved original.
    paragraphs=[p for p in draft.get('paragraphs',[]) if not(p.get('evidence_ids') and set(p['evidence_ids'])<=fixed_ids)]
    for e in reversed(approved):
        if any(p.get('heading')==e['heading'] and p.get('text')==e['text'] for p in paragraphs):continue
        item={'heading':e['heading'],'text':e['text'],'evidence_ids':[e['id']]}
        position=next((i for i,p in enumerate(paragraphs) if p.get('heading')==e['heading']),len(paragraphs))
        paragraphs.insert(position,item)
    draft['paragraphs']=paragraphs
    draft['template_reuse_records']=[{'evidence_id':e['id'],'heading':e['heading'],'source':e['source'],
                                      'locator':e['locator'],'applicability':e['applicability'],
                                      'method':'人工审核后原文组装，未调用模型改写'} for e in approved]
    return draft
