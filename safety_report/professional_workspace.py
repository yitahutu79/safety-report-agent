"""Cross-reference professional records; keep each calculation/measure in one ledger."""
import hashlib
import json


def target_revision(record):
    return record.get('revision',1)


def target_approved(kind,record):
    return record.get('status')=='reviewed' if kind=='calculation' else record.get('disposition') in {'adopted','partial','not_adopted','not_applicable'} and bool(record.get('reviewed_by'))


def link_record(links,source_id,kind,target_id,note,professional,calculations,measures):
    if kind not in {'calculation','measure'}:raise ValueError('请选择计算或措施记录')
    if not isinstance(note,str) or not 2<=len(note.strip())<=1000:raise ValueError('请说明引用用途（2至1000字）')
    source=next((r for r in professional if r['id']==source_id),None)
    records=calculations if kind=='calculation' else measures
    target=next((r for r in records if r['id']==target_id),None)
    if not source or not target:raise ValueError('分析或目标记录不存在，请刷新')
    key=hashlib.sha256((source_id+kind+target_id).encode()).hexdigest()[:24]
    row={'id':key,'source_id':source_id,'target_kind':kind,'target_id':target_id,
         'target_revision':target_revision(target),'note':note.strip()}
    links[:]=[r for r in links if r['id']!=key];links.append(row)
    return row


def link_views(links,professional,calculations,measures):
    result=[]
    for row in links:
        source=next((r for r in professional if r['id']==row['source_id']),None)
        records=calculations if row['target_kind']=='calculation' else measures
        target=next((r for r in records if r['id']==row['target_id']),None)
        status='记录已删除' if not source or not target else '引用版本已变化' if target_revision(target)!=row['target_revision'] else '目标待审核' if not target_approved(row['target_kind'],target) else '分析待审核' if source.get('status')!='reviewed' else '可引用'
        result.append({**row,'source_title':source.get('title','已删除') if source else '已删除',
                       'target_title':target.get('title',target.get('recommendation','')) if target else '已删除','status':status})
    return result


def apply_links_to_evidence(evidence,links,professional,calculations,measures):
    """Reference a reviewed master record, never clone or re-approve its result."""
    views=link_views(links,professional,calculations,measures)
    by_source={r['id']:r for r in professional}
    for row in views:
        if row['status']!='可引用':continue
        source=by_source[row['source_id']]
        prefix=('calculation-' if row['target_kind']=='calculation' else 'measure-')+row['target_id']
        target=next((e for e in evidence if e.get('id','').startswith(prefix)),None)
        if target:
            target.setdefault('link_purposes',[]).append({'source_professional_id':source['id'],'report_section':source['report_section'],'purpose':row['note']})
            sections=target.setdefault('linked_report_sections',[])
            if source['report_section'] not in sections:sections.append(source['report_section'])
    return views
