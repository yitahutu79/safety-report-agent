"""Edit existing report headings without moving or rewriting their factual content."""
import copy
import re
from .pipeline import section_identity
from .report_template import validate_headings


def edit_chapter_outline(report,chapter_id,title,subheadings,delete_content=False):
    if not report:raise ValueError('请先生成草稿，再编辑现有目录')
    result=copy.deepcopy(report)
    section=next((s for s in result['sections'] if section_identity(s)==chapter_id),None)
    if not section:raise ValueError('章节不存在')
    if not isinstance(title,str) or not 2<=len(title.strip())<=180 or '\n' in title:raise ValueError('主章节标题须为2至180字')
    title=title.strip()
    old_title=section['title'];number=re.match(r'\d+',old_title)
    if number and (not re.match(r'\d+',title) or re.match(r'\d+',title).group()!=number.group()):raise ValueError('请保留主章节编号，只修改标题文字；章节顺序使用上移/下移调整')
    if not isinstance(subheadings,list) or len(subheadings)>150:raise ValueError('小节目录格式无效，最多150项')
    old=list(section.get('subheadings',[]));mapping={old_title:title};seen=set();new=[]
    for row in subheadings:
        if not isinstance(row,dict) or not isinstance(row.get('text'),str) or not isinstance(row.get('original',''),str):raise ValueError('小节标题格式无效')
        original=row.get('original','');text=row['text'].strip()
        if original and (original not in old or original in seen):raise ValueError('小节原始标题不存在或重复，请刷新')
        if original:seen.add(original);mapping[original]=text
        new.append(text)
    if number:
        headings=[{'text':title,'level':1}]+[{'text':t,'level':len(re.match(r'\d+(?:\.\d+)*',t).group().split('.')) if re.match(r'\d+(?:\.\d+)*',t) else 0} for t in new]
        validate_headings(headings)
        if any(not t.startswith(number.group()+'.') for t in new):raise ValueError('小节编号须归属于当前主章节')
    elif len(set(new))!=len(new) or any(not t or len(t)>180 for t in new):raise ValueError('小节标题无效或重复')
    used={p.get('heading',old_title) for p in section.get('paragraphs',[])+section.get('tables',[])+section.get('figures',[])}
    removed=set(old)-seen
    if removed & used and not delete_content:raise ValueError('以下小节仍有正文或表格，请先将内容移到其他小节再删除：'+'、'.join(removed & used))
    if any(s is not section and s['title']==title for s in result['sections']):raise ValueError('主章节标题重复')
    if delete_content:
        for key in ('paragraphs','tables','figures','template_reuse_records'):
            section[key]=[item for item in section.get(key,[]) if item.get('heading') not in removed]
    section['title']=title;section['subheadings']=new
    for item in section.get('paragraphs',[])+section.get('tables',[])+section.get('figures',[]):
        item['heading']=mapping.get(item.get('heading',old_title),item.get('heading',title))
    for record in section.get('template_reuse_records',[]):record['heading']=mapping.get(record['heading'],record['heading'])
    cited={i for p in section.get('paragraphs',[]) for i in p.get('evidence_ids',[])}
    for e in result.get('evidence',[]):
        if e.get('id') in cited and e.get('corpus')=='reviewed_template':e['heading']=mapping.get(e.get('heading'),e.get('heading'))
    result.setdefault('structure_changes',[]).append('目录编辑：'+old_title+' → '+title+'；小节标题/顺序已人工调整，文内编号和交叉引用需校对')
    result['quality_checked']=False
    result['updated_chapters']=[chapter_id]
    return result,mapping


def outline_profile(report):
    headings=[]
    for s in report['sections']:
        ident=section_identity(s);h={'text':s['title'],'level':1,'subheadings':s.get('subheadings',[])}
        if s.get('custom'):h['id']=ident
        headings.append(h)
        for t in s.get('subheadings',[]):
            m=re.match(r'\d+(?:\.\d+)*',t)
            headings.append({'text':t,'level':len(m.group().split('.')) if m else 2})
    return {'headings':headings}


def outline_report(profile):
    sections=[]
    for h in profile['headings']:
        if h['level']==1:
            section={'title':h['text'],'subheadings':[],'paragraphs':[],'tables':[],'missing':[],'review':[],
                     'generation_status':'not_generated','needs_rewrite':True}
            if h.get('id'):section.update(id=h['id'],custom=True)
            sections.append(section)
        elif sections:sections[-1]['subheadings'].append(h['text'])
    return {'sections':sections}


def change_outline(report,data):
    operation=data.get('operation','edit');ident=data.get('chapter_id')
    if operation=='edit':return edit_chapter_outline(report,ident,data.get('title'),data.get('subheadings'),data.get('delete_content') is True)
    result=copy.deepcopy(report);sections=result['sections']
    if operation=='add':
        title=data.get('title')
        validate_headings([{'text':title,'level':1}])
        number=re.match(r'\d+',title).group()
        if any(re.match(r'\d+',s['title']) and re.match(r'\d+',s['title']).group()==number for s in sections):raise ValueError('主章节编号已存在，请使用未占用编号')
        sections.append({'title':title,'subheadings':[],'paragraphs':[],'tables':[],'missing':[],
                         'review':[],'generation_status':'not_generated','needs_rewrite':True})
        result['updated_chapters']=[number]
        result['excluded_chapters']=[i for i in result.get('excluded_chapters',[]) if i!=number]
    elif operation=='delete':
        section=next((s for s in sections if section_identity(s)==ident),None)
        if not section:raise ValueError('章节不存在')
        if len(sections)<=1:raise ValueError('至少保留一个主章节')
        if (section.get('paragraphs') or section.get('tables')) and data.get('delete_content') is not True:raise ValueError('该章含正文或表格，请确认同时删除内容；历史版本仍保留')
        sections.remove(section);result['updated_chapters']=[ident]
        result['generation_errors']=[e for e in result.get('generation_errors',[]) if e.get('title')!=section['title']]
        result['excluded_chapters']=sorted(set(result.get('excluded_chapters',[]))|{ident})
    else:raise ValueError('目录操作无效')
    result['quality_checked']=False;result['status']='in_progress'
    result.setdefault('structure_changes',[]).append('人工目录调整：'+operation+'；需核对章节编号、图件位置与交叉引用')
    return result,{}
