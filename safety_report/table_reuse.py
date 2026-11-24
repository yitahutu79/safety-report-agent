"""Native Word table geometry and explicit, source-linked table reuse; no model calls."""
import copy
import hashlib
import json
from pathlib import Path

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TABLE_PARSER_REVISION=1


def read_table(element):
    grid=[int(c.get(W+'w','1')) for c in element.findall(W+'tblGrid/'+W+'gridCol')]
    cells=[];rows=[];active={};header_rows=0
    for ri,row in enumerate(element.findall(W+'tr')):
        if row.find(W+'trPr/'+W+'tblHeader') is not None and header_rows==ri:header_rows+=1
        before=row.find(W+'trPr/'+W+'gridBefore');col=int(before.get(W+'val','0')) if before is not None else 0
        values=['']*col;following={}
        for cell in row.findall(W+'tc'):
            span=cell.find(W+'tcPr/'+W+'gridSpan');span=int(span.get(W+'val','1')) if span is not None else 1
            if not 1<=span<=256:raise ValueError('表格合并列数异常')
            merge=cell.find(W+'tcPr/'+W+'vMerge')
            continuation=merge is not None and merge.get(W+'val','continue')!='restart'
            text='\n'.join(''.join(n.text or '' for n in p.iter(W+'t')) for p in cell.findall(W+'p')).strip()
            anchor=active.get(col) if continuation else None
            if anchor is not None and anchor['colspan']==span:
                anchor['rowspan']+=1;text=anchor['text'];current=anchor
            else:
                current={'row':ri,'col':col,'rowspan':1,'colspan':span,'text':text};cells.append(current)
            values.extend([text]*span)
            if merge is not None:
                for c in range(col,col+span):following[c]=current
            col+=span
        active=following;rows.append(values)
    width=max([len(grid)]+[len(r) for r in rows])
    rows=[r+['']*(width-len(r)) for r in rows]
    if len(grid)!=width:grid=[1]*width
    return rows,{'version':TABLE_PARSER_REVISION,'grid':grid,'cells':cells,'header_rows':max(1,header_rows),'row_count':len(rows)}


def compatible_layout(table):
    layout=table.get('source_table_layout');matrix=[table.get('headers',[])]+table.get('rows',[])
    if not isinstance(layout,dict) or layout.get('row_count')!=len(matrix) or not layout.get('grid'):return None
    width=len(layout['grid'])
    if any(len(row)!=width for row in matrix) or len(matrix)*width>100000:return None
    if any(type(w) is not int or w<0 for w in layout['grid']):return None
    if not isinstance(layout.get('cells'),list):return None
    occupied=set()
    for cell in layout['cells']:
        if not isinstance(cell,dict) or any(type(cell.get(k)) is not int for k in ('row','col','rowspan','colspan')):return None
        r,c,rs,cs=(cell[k] for k in ('row','col','rowspan','colspan'))
        if min(r,c)<0 or min(rs,cs)<1 or r+rs>len(matrix) or c+cs>width:return None
        for rr in range(r,r+rs):
            for cc in range(c,c+cs):
                if (rr,cc) in occupied:return None
                occupied.add((rr,cc))
    return layout


def synchronize_merged_edits(original,updated):
    layout=compatible_layout(original)
    if not layout or len(updated['rows'])!=len(original['rows']) or len(updated['headers'])!=len(original['headers']):
        updated.pop('source_table_layout',None);return updated
    old=[original['headers']]+original['rows'];new=[updated['headers']]+updated['rows']
    for cell in layout['cells']:
        r,c=cell['row'],cell['col'];text=new[r][c]
        for rr in range(r,r+cell['rowspan']):
            for cc in range(c,c+cell['colspan']):
                if (rr,cc)==(r,c):continue
                if new[rr][cc] not in {old[rr][cc],text}:raise ValueError('合并单元格存在不同修改，请在合并格左上角编辑')
                new[rr][cc]=text
    return updated


def source_tables(target,files,file_id=None):
    from .documents import read_docx
    result=[]
    for file in files:
        if not file.get('active',True) or file.get('role') not in {'source','reference'} or Path(file['name']).suffix.lower()!='.docx' or (file_id and file['id']!=file_id):continue
        blocks,_=read_docx(Path(target)/'uploads'/file['stored']);heading='';caption=''
        for block in blocks:
            if block.get('level') in (1,2,3):heading=block['text'];caption=''
            elif block['kind']=='paragraph':
                import re
                caption=block['text'] if re.match(r'^表\s*\d',block['text']) else ''
            elif block['kind']=='table' and block.get('rows'):
                content_hash=hashlib.sha256(json.dumps([block['rows'],block.get('table_layout')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                result.append({'id':file['id']+':'+block['locator'],'source_file_id':file['id'],'source_file':file['name'],
                    'source_sha256':file['sha256'],'source_locator':block['locator'],'source_heading':heading,
                    'source_table_hash':content_hash,'reuse_supported':not block.get('table_has_objects',False),'caption':caption or heading+' 原表','headers':block['rows'][0],
                    'rows':block['rows'][1:],'source_table_layout':block.get('table_layout'),'text':block['text']})
                caption=''
    return result


def insert_source_table(report,item,section_id,heading):
    from .pipeline import section_identity
    if not item.get('reuse_supported',True):raise ValueError('原表含图片、嵌套表或嵌入对象，请转换为PDF，通过原件附录保留，避免丢失内容')
    result=copy.deepcopy(report);section=next((s for s in result['sections'] if section_identity(s)==section_id),None)
    if not section or heading not in [section['title']]+section.get('subheadings',[]):raise ValueError('请选择当前报告的有效小节')
    if any(t.get('source_table_id')==item['id'] and t.get('heading')==heading for t in section.get('tables',[])):raise ValueError('本小节已经复用了这张原表，请直接编辑现有表格')
    eid='source-table-'+hashlib.sha256((item['id']+item['source_table_hash']).encode()).hexdigest()[:24]
    table={k:copy.deepcopy(item[k]) for k in ('caption','headers','rows','source_table_layout')}
    table.update(heading=heading,evidence_ids=[eid],source_table_id=item['id'],source_table_hash=item['source_table_hash'],report_source_reused=True,
                 source_file=item['source_file'],source_locator=item['source_locator'])
    refs={e['id']:e for e in result.get('evidence',[])}
    previous=next((t for t in section.get('tables',[]) if t.get('report_source_reused') and not t.get('source_table_id') and t.get('heading')==heading and len(t.get('evidence_ids',[]))==1 and any(refs.get(e,{}).get('source')==item['source_file'] and refs.get(e,{}).get('locator')==item['source_locator'] for e in t['evidence_ids'])),None)
    if previous is not None:
        if previous.get('human_edited'):raise ValueError('已有同来源表格经过人工修改，请保留其修改后再决定是否使用原表')
        section['tables'][section['tables'].index(previous)]=table
    else:section.setdefault('tables',[]).append(table)
    evidence={'id':eid,'source':item['source_file'],'sha256':item['source_sha256'],
        'source_file_id':item['source_file_id'],'locator':item['source_locator'],'text':item['text'],'corpus':'project_evidence',
        'evidence_type':'user_confirmed_source_table','original_verified':False,'report_reuse_authorized':True}
    if not any(e['id']==eid for e in result.setdefault('evidence',[])):result['evidence'].append(evidence)
    section['human_edited']=True
    result['updated_chapters']=[section_id]
    result['quality_checked']=False
    # Adding a table does not complete an otherwise ungenerated chapter.
    return result
