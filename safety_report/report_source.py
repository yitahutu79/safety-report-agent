"""Deterministic reuse of a report explicitly selected by the user as this project's source."""
import hashlib
import re


def confirmed_sources(files):
    return [{'id':f['id'],'name':f['name'],'sha256':f['sha256']} for f in files
            if f.get('active',True) and f.get('report_source_confirmed') is True and f.get('role') in {'source','reference'}]


def provided_report_draft(analysis,headings):
    normalized={re.sub(r'\s+','',h):h for h in headings}
    sources={f['sha256']:f for f in analysis.get('confirmed_report_sources',[])}
    paragraphs=[];tables=[];evidence=[];covered=set();origins=[]
    for doc in analysis.get('documents',[])+analysis.get('reference_documents',[]):
        file=sources.get(doc.get('sha256'))
        if not file:continue
        current=None;matched=set()
        for block_order,block in enumerate(doc.get('blocks',[])):
            if block.get('level') in (1,2,3):
                current=normalized.get(re.sub(r'\s+','',block['text']))
                if current:matched.add(current)
                continue
            if not current or current in covered or not block.get('text','').strip():continue
            eid='report-source-'+hashlib.sha256((file['sha256']+block['locator']).encode()).hexdigest()[:24]
            ref={'id':eid,'source':file['name'],'sha256':file['sha256'],'source_file_id':file['id'],
                 'locator':block['locator'],'text':block['text'],'heading':current,'corpus':'project_evidence',
                 'evidence_type':'user_confirmed_report','report_reuse_authorized':True,'original_verified':False}
            evidence.append(ref)
            if block['kind']=='table':
                if block.get('table_has_objects'):raise ValueError('原表包含图片或嵌套表，请转换为PDF并通过原件附录保留完整内容')
                rows=block.get('rows',[])
                if rows:
                    width=max(len(row) for row in rows);rows=[list(row)+['']*(width-len(row)) for row in rows]
                    caption='原报告表格'
                    if paragraphs and paragraphs[-1]['heading']==current and re.match(r'^表\s*\d',paragraphs[-1]['text']):caption=paragraphs.pop()['text']
                    step=len(rows) if block.get('table_layout') else 300
                    for start in range(1,max(2,len(rows)),max(1,step)):
                        tables.append({'heading':current,'caption':caption+('（续）' if start>1 else ''),'headers':rows[0],
                                       'rows':rows[start:start+step],'source_order':block_order,'evidence_ids':[eid],'report_source_reused':True,
                                       **({'source_table_layout':block['table_layout']} if block.get('table_layout') else {})})
            else:paragraphs.append({'heading':current,'text':block['text'],'source_order':block_order,'evidence_ids':[eid],'report_source_reused':True})
        covered.update(matched);origins.append(file['name'])
    return {'paragraphs':paragraphs,'tables':tables,'missing':[],
            'review':['按用户确认的已有报告复用；原件真实性、法规现行性和结论适用性仍由专业人员核验。'] if covered else [],
            'covered_headings':[h for h in headings if h in covered],'evidence':evidence,
            'source_reuse_records':[{'source':e['source'],'locator':e['locator'],'heading':e['heading'],'evidence_id':e['id']} for e in evidence],
            'agent_trace':[{'agent':'已确认报告复用工具','status':'按对应标题原样组装正文和表格，未调用写作模型'}] if covered else []}


def exact_report_reuse(paragraph,evidence):
    ids=set(paragraph.get('evidence_ids',[]))
    return any(e.get('id') in ids and e.get('report_reuse_authorized') is True
               and e.get('heading')==paragraph.get('heading') and e.get('text')==paragraph.get('text') for e in evidence)
