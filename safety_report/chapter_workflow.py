"""Human chapter approval, dependency warnings and deterministic assembly checks."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from .pipeline import section_identity


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def section_digest(section):
    return digest({k:section.get(k) for k in ('title','subheadings','paragraphs','tables','figures','missing','review','generation_status','generation_error','needs_rewrite')})


def dependency_snapshot(state, section=None, report=None):
    files=[{k:f.get(k) for k in ('id','name','sha256','active','role','document_date','document_version')} for f in state.get('files',[])]
    selected=files
    if section is not None and report is not None:
        ids={i for p in section.get('paragraphs',[])+section.get('tables',[])+section.get('figures',[]) for i in p.get('evidence_ids',[])}
        refs=[e for e in report.get('evidence',[]) if e.get('id') in ids and e.get('corpus')!='reviewed_template']
        names={e.get('source') for e in refs};hashes={e.get('sha256') for e in refs if e.get('sha256')}
        if names or hashes:selected=[f for f in files if f.get('name') in names or f.get('sha256') in hashes]
    return {'fields':digest([{k:f.get(k) for k in ('key','value','confirmed')} for f in state.get('fields',[])]),
            'files':digest(selected),'all_files':digest(files),
            'template':digest(state.get('report_template')), 'revision':state.get('data_revision',0)}


def workflow_view(report,state,workflow):
    result={}
    for section in (report or {}).get('sections',[]):
        ident=section_identity(section);record=workflow.get('chapters',{}).get(ident,{})
        deps=dependency_snapshot(state,section,report)
        locked=record.get('locked') is True
        warnings=[]
        if locked:
            if record.get('content_hash')!=section_digest(section):warnings.append('章节内容与确认版本不同，请重新审核')
            old=record.get('dependencies',{})
            if old.get('fields')!=deps['fields']:warnings.append('项目基础数据已变化，需复核本章采用的数据')
            if old.get('files')!=deps['files']:warnings.append('项目资料或版本已变化，需复核本章来源')
            if old.get('template')!=deps['template']:warnings.append('模板或复用规则已变化，需复核本章')
            if not warnings and old.get('all_files')==deps['all_files'] and old.get('revision')!=deps['revision']:warnings.append('专业台账或项目记录已更新，请复核是否影响本章')
        complete=bool(section.get('paragraphs') or section.get('tables')) and not(section.get('needs_rewrite') or section.get('generation_error') or section.get('generation_status') in {'not_generated','failed'})
        status='需复核' if warnings else '已确认锁定' if locked else '待确认' if complete else '未完成'
        result[ident]={'locked':locked,'status':status,'warnings':warnings,'confirmed_at':record.get('confirmed_at','')}
    return result


def set_chapter_approval(report,state,workflow,ident,locked):
    section=next((s for s in report['sections'] if section_identity(s)==ident),None)
    if not section:raise ValueError('章节不存在')
    if locked and (not(section.get('paragraphs') or section.get('tables')) or section.get('needs_rewrite') or section.get('generation_error') or section.get('generation_status') in {'not_generated','failed'}):raise ValueError('章节尚未完成，不能确认锁定')
    chapters=workflow.setdefault('chapters',{})
    chapters[ident]={'locked':locked,'content_hash':section_digest(section),
                     'dependencies':dependency_snapshot(state,section,report),'confirmed_at':datetime.now(timezone.utc).isoformat() if locked else ''}


def assert_unlocked(workflow,ids):
    locked=[i for i in ids if workflow.get('chapters',{}).get(i,{}).get('locked')]
    if locked:raise ValueError('以下章节已锁定，请先解锁再修改：'+ '、'.join(locked))


def ordered_report(report,workflow):
    result=copy.deepcopy(report);order=workflow.get('order',[])
    positions={v:i for i,v in enumerate(order)}
    result['sections'].sort(key=lambda s:positions.get(section_identity(s),len(positions)))
    return result


def assembly_checks(report,state,workflow,profile,quality):
    blockers=[];warnings=[];sections=(report or {}).get('sections',[])
    view=workflow_view(report,state,workflow)
    import re
    expected={h.get('id') or re.match(r'\d+',h['text']).group() for h in profile['headings'] if h['level']==1}
    excluded=set((report or {}).get('excluded_chapters',[]));expected-=excluded
    if excluded:warnings.append('存在人工删除的模板章节，请复核报告结构完整性：'+'、'.join(sorted(excluded)))
    actual={section_identity(s) for s in sections}
    if not sections:blockers.append('尚无报告章节')
    if (report or {}).get('mode') in {'outline','evidence_outline'}:blockers.append('当前仍为编写提纲，不能作为完整正文组稿')
    if expected-actual:blockers.append('缺少模板主章节：'+ '、'.join(sorted(expected-actual)))
    if report and report.get('template_sha256')!=profile['sha256']:blockers.append('当前草稿与已应用模板不同，请按新模板生成')
    for field in state.get('fields',[]):
        if field.get('value') and not field.get('confirmed'):blockers.append('基础数据尚未核对：'+field.get('label',field.get('key','字段')))
        if field.get('key') in {'company','project'} and not field.get('value'):blockers.append('缺少关键基础数据：'+field.get('label',field['key']))
    if state.get('analysis_dirty'):blockers.append('资料变化后尚未重新读取')
    numbered=[int(re.match(r'\d+',s['title']).group()) for s in ordered_report(report or {'sections':[]},workflow)['sections'] if re.match(r'\d+',s['title'])]
    if numbered!=sorted(numbered):warnings.append('当前章节排序与原编号顺序不同，请复核标题编号、表图编号及交叉引用；系统未自动改写这些编号')
    evidence={e['id'] for e in (report or {}).get('evidence',[])}
    for s in sections:
        v=view[section_identity(s)];title=s['title']
        if v['status']=='未完成':blockers.append(title+'：尚未完成')
        if not v['locked']:blockers.append(title+'：尚未确认锁定')
        blockers.extend(title+'：'+msg for msg in v['warnings'])
        blockers.extend(title+'：待补充 '+str(m) for m in s.get('missing',[]))
        warnings.extend(title+'：'+str(m) for m in s.get('review',[]))
        for item in s.get('paragraphs',[])+s.get('tables',[])+s.get('figures',[]):
            if not item.get('evidence_ids') or any(e not in evidence for e in item.get('evidence_ids',[])):blockers.append(title+'：正文存在缺失或失效的来源引用')
    for check in quality.get('checks',[]):
        if check.get('status')=='fail':blockers.append(check['title']+'：'+check.get('detail',''))
        elif check.get('status')=='warning':warnings.append(check['title']+'：'+check.get('detail',''))
    return {'can_assemble':not blockers,'blockers':list(dict.fromkeys(blockers)),
            'warnings':list(dict.fromkeys(warnings)), 'chapters':view,
            'note':'组稿检查不调用模型；已确认章节直接合并。仍须专业人员完成最终审核。'}
