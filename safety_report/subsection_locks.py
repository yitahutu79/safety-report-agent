"""User-confirmed subsection locks, independent of downloadable report versions."""
import hashlib,json
from .pipeline import section_identity


def content(report,chapter,heading):
    section=next((s for s in (report or {}).get('sections',[]) if section_identity(s)==chapter),None)
    if not section or heading not in section.get('subheadings',[]):return None
    return {'paragraphs':[{k:p.get(k) for k in ('heading','text')} for p in section.get('paragraphs',[]) if p.get('heading',section['title'])==heading],
            'tables':[{k:t.get(k) for k in ('heading','caption','headers','rows')} for t in section.get('tables',[]) if t.get('heading',section['title'])==heading]}


def set_lock(report,workflow,chapter,heading,locked):
    data=content(report,chapter,heading)
    if data is None:raise ValueError('小节不存在，请刷新')
    if locked and not(data['paragraphs'] or data['tables']):raise ValueError('该小节还没有正文或表格，暂不能确认锁定')
    workflow.setdefault('subsections',{}).setdefault(chapter,{})[heading]={'locked':locked,'content_hash':hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def assert_scope(workflow,chapter_ids,scope):
    for chapter in chapter_ids or []:
        locked=[h for h,r in workflow.get('subsections',{}).get(chapter,{}).items() if r.get('locked')]
        if any(scope is None or h in scope.get(chapter,[]) for h in locked):raise ValueError('所选范围含已锁定小节，请解锁或只选择未锁定小节')


def assert_unchanged(before,after,workflow):
    for chapter,records in workflow.get('subsections',{}).items():
        for heading,record in records.items():
            if record.get('locked') and content(before,chapter,heading)!=content(after,chapter,heading):raise ValueError('小节“'+heading+'”已锁定，请先解锁')
