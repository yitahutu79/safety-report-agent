"""Report block order: subsection-local paragraphs, tables and anchored pictures."""
import hashlib,re


def in_scope(heading,scope):
    if not scope or heading==scope:return True
    parent=re.match(r'^\d+(?:\.\d+)*',scope);child=re.match(r'^\d+(?:\.\d+)*',heading)
    return bool(parent and child and child.group().startswith(parent.group()+'.'))


def paragraph_anchor(section,heading,index,text):
    if index is None:return {}
    matches=[i for i,p in enumerate(section.get('paragraphs',[])) if p.get('text')==text and p.get('heading',section['title'])==heading]
    if len(matches)!=1:raise ValueError('选定段落已修改、重复或移动，请重新选择插入位置')
    return {'paragraph_index':matches[0],'paragraph_text':text,'paragraph_hash':hashlib.sha256(text.encode()).hexdigest()}


def next_insertion_order(section):
    return max([0]+[x.get('insertion_order',0) for x in section.get('tables',[])+section.get('figures',[]) if type(x.get('insertion_order',0)) is int])+1


def order_content(section,scope=''):
    paragraphs=section.get('paragraphs',[]);items=[]
    for kind,key in (('paragraph','paragraphs'),('table','tables'),('figure','figures')):
        for index,item in enumerate(section.get(key,[])):items.append({'kind':kind,'index':index,'heading':item.get('heading',section['title']),'item':item})
    headings=list(dict.fromkeys([section['title']]+section.get('subheadings',[])+[x['heading'] for x in items]));result=[]
    def manual_key(x):
        value=x['item'].get('insertion_order',0)
        return value if type(value) is int else 0
    def source_key(x):
        value=x['item'].get('source_order')
        return value if type(value) is int else float('inf')
    def event(x,stale=False):return {'kind':x['kind'],'index':x['index'],'heading':x['heading'],'stale':stale}
    for heading in headings:
        if not in_scope(heading,scope):continue
        group=[x for x in items if x['heading']==heading]
        if not group:continue
        result.append({'kind':'heading','heading':heading})
        base=[];anchored={};end=[]
        for x in group:
            item=x['item'];anchor=item.get('paragraph_text')
            if x['kind']!='paragraph' and anchor is not None:
                matches=[i for i,p in enumerate(paragraphs) if p.get('text')==anchor and p.get('heading',section['title'])==heading]
                if len(matches)==1:anchored.setdefault(matches[0],[]).append(x)
                else:end.append((x,True))
            elif x['kind']=='figure' or (x['kind']=='table' and 'insertion_order' in item):end.append((x,False))
            else:base.append(x)
        for x in sorted(base,key=source_key):
            result.append(event(x))
            if x['kind']=='paragraph':result.extend(event(a) for a in sorted(anchored.get(x['index'],[]),key=manual_key))
        result.extend(event(x,stale) for x,stale in sorted(end,key=lambda p:manual_key(p[0])))
    return result
