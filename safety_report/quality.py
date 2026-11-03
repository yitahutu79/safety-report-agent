"""Deterministic completeness and traceability checks for report review packets."""
import re
from datetime import date

def _identity(section):
    ident = section.get('id')
    if ident:
        return str(ident)
    title = section.get('title', '')
    return title.split(maxsplit=1)[0].rstrip('.') if title[:1].isdigit() else ''


def review_report(report, project_state, measures=(), calculations=()):
    evidence = {item.get('id'): item for item in report.get('evidence', []) if item.get('id')}
    sections = report.get('sections', [])
    text_by_section = {}
    refs_by_section = {}
    for section in sections:
        number = _identity(section)
        text_parts, refs = [], set()
        for item in section.get('paragraphs', []) + section.get('tables', []):
            if item.get('text'):
                text_parts.append(item.get('text', ''))
            text_parts.append(' '.join(map(str, item.get('headers', []))))
            text_parts.extend(' '.join(map(str, row)) for row in item.get('rows', []))
            refs.update(item.get('evidence_ids', []))
        text_by_section[number] = '\n'.join(text_parts)
        refs_by_section[number] = refs

    checks = []
    def add(key, title, status, detail, count=None):
        checks.append({'key': key, 'title': title, 'status': status, 'detail': detail,
                       **({'count': count} if count is not None else {})})

    unconfirmed = list(report.get('unconfirmed_fields', []))
    if unconfirmed:
        add('confirmed_facts', '关键项目事实核对', 'warning', '以下字段未确认或缺失：' + '、'.join(unconfirmed), len(unconfirmed))
    else:
        add('confirmed_facts', '关键项目事实核对', 'pass', '报告记录中没有未确认字段。')

    conflicts = [f.get('label', f.get('key', '未命名字段')) for f in project_state.get('fields', []) if f.get('conflict')]
    if conflicts:
        add('source_conflicts', '资料冲突', 'fail', '存在尚未消解的候选冲突：' + '、'.join(conflicts), len(conflicts))
    else:
        add('source_conflicts', '资料冲突', 'pass', '项目字段中未标记待处理的冲突。')

    report_text = '\n'.join(text_by_section.values())
    contradictory_values = []
    critical_keys = {'company', 'project', 'address', 'capacity', 'investment', 'area', 'nature'}
    for field in project_state.get('fields', []):
        if field.get('key') not in critical_keys or not field.get('value'):
            continue
        for candidate in field.get('candidates', []):
            value = candidate.get('value', '').strip()
            if value and value != field['value'] and len(value) >= 3 and value in report_text:
                contradictory_values.append(field.get('label', field['key']) + '：正文出现未选候选“' + value[:80] + '”')
    if contradictory_values:
        add('cross_chapter_consistency', '报告前后关键信息一致性', 'warning', '报告正文出现与已确认字段不同的资料候选，可能是引用历史/对比内容，也可能是冲突未消解：' + '；'.join(dict.fromkeys(contradictory_values[:12])), len(contradictory_values))
    else:
        add('cross_chapter_consistency', '报告前后关键信息一致性', 'pass', '未发现正文复现已知的未选项目名称、地点、规模或建设属性候选。')

    unresolved = []
    missing_locations = []
    uncited_content = []
    for section in sections:
        for item in section.get('paragraphs', []) + section.get('tables', []):
            content = item.get('text', '') or ' '.join(map(str, item.get('headers', []))) + ' '.join(
                ' '.join(map(str, row)) for row in item.get('rows', []))
            if content.strip() and not item.get('evidence_ids'):
                uncited_content.append(section.get('title', '未命名章节'))
            for ident in item.get('evidence_ids', []):
                source = evidence.get(ident)
                if not source:
                    unresolved.append(ident)
                elif not source.get('source') or not source.get('locator'):
                    missing_locations.append(ident)
    if unresolved:
        add('citations', '正文证据引用', 'fail', '以下引用无法在版本证据快照中找到：' + '、'.join(unresolved[:20]), len(unresolved))
    elif missing_locations:
        add('citations', '正文证据引用', 'warning', '部分来源缺少文件名或定位：' + '、'.join(missing_locations[:20]), len(missing_locations))
    else:
        add('citations', '正文证据引用', 'pass', '正文引用均能解析到本版本证据快照及来源定位。')
    if uncited_content:
        add('uncited_content', '无来源正文内容', 'warning', '以下章节存在未绑定证据的段落或表格（可能是人工新增内容）：' + '、'.join(dict.fromkeys(uncited_content)), len(uncited_content))
    else:
        add('uncited_content', '无来源正文内容', 'pass', '正文段落和表格均关联了证据。')

    pending_sections = [s.get('title', '') for s in sections if s.get('generation_status') in {'failed', 'not_generated'}]
    missing_sections = [s.get('title', '') for s in sections if s.get('missing')]
    if pending_sections:
        add('chapter_completion', '章节完整性', 'fail', '未完成或生成失败：' + '、'.join(pending_sections), len(pending_sections))
    elif missing_sections:
        add('chapter_completion', '章节完整性', 'warning', '有待补充信息的章节：' + '、'.join(missing_sections), len(missing_sections))
    else:
        add('chapter_completion', '章节完整性', 'pass', '章节没有登记待补充信息。')

    measure_gaps = []
    pending_measure_count = sum(item.get('disposition') == 'pending' for item in measures)
    for item in measures:
        if item.get('disposition') == 'pending':
            continue
        ident = 'measure-' + item.get('id', '') + '-r' + str(item.get('revision', 1))
        if not any(ident in refs for refs in refs_by_section.values()):
            measure_gaps.append(item.get('recommendation', item.get('id', ''))[:80])
    if measure_gaps:
        add('measure_adoption', '安全措施承接', 'warning', '已决定的措施尚未在当前报告正文中引用：' + '；'.join(measure_gaps[:12]), len(measure_gaps))
    else:
        add('measure_adoption', '安全措施承接', 'pass', '已决定的措施均已在当前报告中关联，或台账暂无已决定项。')
    if pending_measure_count:
        add('pending_measures', '待确认安全措施', 'warning', f'安全措施台账还有 {pending_measure_count} 条待确认候选，尚不能作为已采纳内容。', pending_measure_count)
    else:
        add('pending_measures', '待确认安全措施', 'pass', '没有待确认措施候选。')

    calc_gaps = []
    for item in calculations:
        if item.get('status') != 'reviewed':
            continue
        ident = 'calculation-' + item.get('id', '') + '-r' + str(item.get('revision', 1))
        target = {'3', '5', '6'}
        if not any(ident in refs_by_section.get(section, set()) for section in target):
            calc_gaps.append(item.get('title', item.get('id', '')))
    if calc_gaps:
        add('calculation_traceability', '分析计算追溯', 'warning', '已复核计算尚未在第 3、5 或 6 章引用：' + '、'.join(calc_gaps[:12]), len(calc_gaps))
    else:
        add('calculation_traceability', '分析计算追溯', 'pass', '已复核计算均已被相关章节引用，或尚无已复核计算。')
    unreviewed_calculations = [item for item in calculations if item.get('status') != 'reviewed']
    if unreviewed_calculations:
        add('pending_calculations', '待复核分析计算', 'warning',
            '计算台账有未复核或未通过记录：' + '、'.join(item.get('title', '') for item in unreviewed_calculations[:12]),
            len(unreviewed_calculations))
    else:
        add('pending_calculations', '待复核分析计算', 'pass', '没有待复核分析/计算记录。')

    drawing_gaps = []
    for file in project_state.get('files', []):
        if file.get('active', True) and file.get('document_type') == 'drawing' and (not file.get('document_version') or not file.get('document_date')):
            drawing_gaps.append(file.get('name', '未命名图纸'))
    if drawing_gaps:
        add('drawing_revision', '专业图纸版本', 'warning', '以下图纸未登记日期或版次：' + '、'.join(drawing_gaps[:20]), len(drawing_gaps))
    else:
        add('drawing_revision', '专业图纸版本', 'pass', '已登记为专业图纸的活动文件均有日期和版次。')

    has_current_full_draft = (report.get('source_revision') == project_state.get('data_revision', 0)
                              and report.get('status') == 'draft'
                              and not report.get('generation_errors'))
    if (project_state.get('source_changes_pending') or project_state.get('report_outdated')) and not has_current_full_draft:
        add('source_freshness', '报告与项目资料同步', 'warning', '项目资料或信息在当前报告生成后发生变化；应修订受影响章节。')
    else:
        add('source_freshness', '报告与项目资料同步', 'pass', '项目当前没有标记为待纳入报告的资料变更。')

    regulatory_unknown = [item.get('source', item.get('id', '')) for item in evidence.values()
                          if item.get('corpus') == 'approved_knowledge' and item.get('category') == 'regulation'
                          and item.get('validity_status') != 'current']
    standard_pattern = re.compile(r'\b(?:GB(?:/T)?|AQ|HG(?:/T)?|SH(?:/T)?|JGJ|GBZ)\s*[-—]?\s*\d{3,6}(?:\.\d+)?(?:[-—]\d{4})?', re.I)
    def source_current(item):
        if item.get('corpus') == 'approved_knowledge' and item.get('category') == 'regulation':
            return item.get('validity_status') == 'current'
        if item.get('evidence_type') == 'professional_calculation' and standard_pattern.search(item.get('text', '')):
            if item.get('rule_validity_status') != 'current' or not item.get('rule_checked_date'):
                return False
            try:
                age = (date.today() - date.fromisoformat(item['rule_checked_date'])).days
                return 0 <= age <= 365
            except ValueError:
                return False
        return False
    regulatory_unknown.extend(item.get('source', item.get('id', '')) for item in evidence.values()
                              if item.get('evidence_type') == 'professional_calculation'
                              and standard_pattern.search(item.get('text', '')) and not source_current(item))
    cited_standard_refs = []
    for section in sections:
        body = text_by_section.get(_identity(section), '')
        codes = standard_pattern.findall(body)
        if not codes:
            continue
        cited = [evidence.get(ident, {}) for ident in refs_by_section.get(_identity(section), set())]
        current_law_refs = [item for item in cited if source_current(item)]
        if not current_law_refs:
            cited_standard_refs.extend(f'{section.get("title", "")}: {code}' for code in codes)
    if regulatory_unknown:
        add('regulation_validity', '法规标准有效性', 'fail', '报告引用了有效状态未确认为现行的知识库法规：' + '、'.join(regulatory_unknown[:12]), len(regulatory_unknown))
    elif cited_standard_refs:
        add('regulation_validity', '法规标准有效性', 'warning', '以下标准编号未关联到有效状态为现行的审核知识库条目，须人工核对适用版本：' + '；'.join(dict.fromkeys(cited_standard_refs[:20])), len(cited_standard_refs))
    else:
        add('regulation_validity', '法规标准有效性', 'pass', '知识库引用法规均标记为现行，正文未发现缺少有效知识依据的标准编号；项目文件中的法规仍须人工核验。')

    counts = {status: sum(check['status'] == status for check in checks) for status in ('pass', 'warning', 'fail')}
    return {'checks': checks, 'counts': counts,
            'overall': 'needs_review' if counts['warning'] or counts['fail'] else 'clear',
            'note': '自动检查用于定位问题，不等同于专业结论或最终验收。'}
