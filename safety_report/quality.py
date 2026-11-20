"""Deterministic completeness and traceability checks for report review packets."""
import re
from datetime import date

def _identity(section):
    ident = section.get('id')
    if ident:
        return str(ident)
    title = section.get('title', '')
    return title.split(maxsplit=1)[0].rstrip('.') if title[:1].isdigit() else ''


def review_report(report, project_state, measures=(), calculations=(), professional_records=()):
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
    source_dumps = [s.get('title', '') for s in sections
                    if any(re.search(r'(?:资料|原文|内容)\s*摘录\s*[:：]?', p.get('text', ''))
                           for p in s.get('paragraphs', []))]
    if source_dumps:
        add('source_dump', '存量正文摘录检查', 'fail',
            '以下章节仍有资料摘录标记，不能视为完成的报告正文：' + '、'.join(source_dumps), len(source_dumps))
    else:
        add('source_dump', '存量正文摘录检查', 'pass', '未检测到显式摘录标记；不代表语义或专业质量已审核通过。')

    # Only compare explicitly named development zones, not every company or address:
    # landlords, suppliers and registration addresses may legitimately differ.
    address = next((f.get('value', '') for f in project_state.get('fields', [])
                    if f.get('key') == 'address' and f.get('confirmed')), '')
    zone_pattern = r'[\u4e00-\u9fff]{2,12}?(?:经济技术开发区|经济开发区|高新技术产业开发区)'
    expected_zones = re.findall(zone_pattern, address)
    zone_mismatches = []
    if expected_zones:
        for location in re.findall(r'本项目(?:位于|建设地点为|建设地址为)([^，。；\n]{2,100})', report_text):
            for zone in re.findall(zone_pattern, location):
                if not any(zone.endswith(expected) or expected.endswith(zone) for expected in expected_zones):
                    zone_mismatches.append(zone)
    if zone_mismatches:
        add('project_location_scope', '项目场址表述核对', 'warning',
            '正文以本项目名义描述了不同的开发区名称：' + '、'.join(dict.fromkeys(zone_mismatches)) +
            '；请核实是否混入其他项目资料，名称差异本身不直接证明不同地点。', len(zone_mismatches))

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
        add('chapter_completion', '章节完整性', 'warning', '章节未登记缺项；空缺项清单不能证明内容完整，须对照确认的目录及事实清单复核。')

    measure_gaps = []
    pending_measure_count = sum(item.get('disposition') == 'pending' for item in measures)
    for item in measures:
        if item.get('disposition') == 'pending':
            continue
        ident = 'measure-' + item.get('id', '') + '-r' + str(item.get('revision', 1))
        if not any(ident in refs for refs in refs_by_section.values()):
            measure_gaps.append(item.get('recommendation', item.get('id', ''))[:80])
    analysis_source_present = any(f.get('active', True) and f.get('document_type') == 'safety_analysis'
                                  for f in project_state.get('files', []))
    if measure_gaps:
        add('measure_adoption', '安全措施承接', 'warning', '已决定的措施尚未在当前报告正文中引用：' + '；'.join(measure_gaps[:12]), len(measure_gaps))
    elif analysis_source_present and not measures:
        add('measure_adoption', '安全措施承接', 'warning', '已登记综合分析报告，但措施台账为空；请提取并逐条核对安全建议。')
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

    # These are workflow prompts, not a claim that every category applies to every project.
    from .professional_workflow import WORKFLOWS
    report_type = report.get('report_type', project_state.get('report_type', 'facility_design'))
    kinds = WORKFLOWS.get(report_type, {})
    confirmed_kinds = {item.get('kind') for item in professional_records if item.get('status') == 'reviewed'}
    absent = [name for kind, (name, _) in kinds.items() if kind not in confirmed_kinds]
    pending = [item.get('title', '') for item in professional_records if item.get('status') != 'reviewed']
    unreferenced = [item.get('title', '') for item in professional_records if item.get('status') == 'reviewed'
                    and not any(('professional-' + item.get('id', '') + '-r' + str(item.get('revision', 1))) in refs for refs in refs_by_section.values())]
    details = []
    if absent:
        details.append('以下工作尚无已复核记录，请结合项目判断是否适用：' + '、'.join(absent))
    from .workflow_schema import SCHEMAS
    incomplete = []
    for item in professional_records:
        if item.get('status') != 'reviewed':
            continue
        fields = SCHEMAS.get(report_type, {}).get(item.get('kind'), [])
        missing = [field['label'] for field in fields if field.get('required') and not item.get('details', {}).get(field['key'])]
        if missing:
            incomplete.append(item.get('title', '') + '（缺少：' + '、'.join(missing) + '）')
    if incomplete:
        details.append('已复核记录的专业分项待补全：' + '；'.join(incomplete[:12]))
    from datetime import date as _date
    regulatory_uncertain = []
    for item in professional_records:
        if item.get('kind') != 'regulatory':
            continue
        d = item.get('details', {})
        try:
            age = (_date.today() - _date.fromisoformat(d.get('checked_date', ''))).days
        except (ValueError, TypeError):
            age = -1
        if item.get('status') != 'reviewed' or d.get('decision') == '待确认' or not d.get('decision') or d.get('validity') != '现行' or not 0 <= age <= 365:
            regulatory_uncertain.append(item.get('title', '未命名依据'))
    if regulatory_uncertain:
        details.append('法规适用性、有效状态或核验时效待确认：' + '、'.join(regulatory_uncertain[:12]))
    open_rectifications = [item.get('title', '') for item in professional_records
        if report_type in {'acceptance_evaluation', 'worktrade_current_evaluation', 'dual_prevention'} and item.get('kind') == 'rectification'
        and item.get('details', {}).get('progress') != '复查通过']
    if open_rectifications:
        details.append('整改尚未记录为复查通过：' + '、'.join(open_rectifications[:12]))
    if pending:
        details.append('待处理记录：' + '、'.join(pending[:12]))
    if unreferenced:
        details.append('已复核但报告尚未引用：' + '、'.join(unreferenced[:12]))
    add('professional_workflow', '专业工作记录与承接', 'warning' if details else 'pass',
        '；'.join(details) if details else '所登记的专业工作记录已复核并关联；仍须专业人员核实完整性。')

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
        if item.get('evidence_type') == 'regulatory_applicability':
            try:
                age = (date.today() - date.fromisoformat(item.get('rule_checked_date', ''))).days
            except (ValueError, TypeError):
                return False
            return (item.get('rule_validity_status') == '现行' and item.get('project_applicability') == '适用' and 0 <= age <= 365)
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
    # Matching codes and a human project decision are necessary, not sufficient, for applicability.
    def code_key(value):
        return re.sub(r'[\s—-]+', '', value).upper()
    report_codes = {code_key(code): code for code in standard_pattern.findall(report_text)}
    project_applicability = set()
    for item in professional_records:
        if item.get('kind') != 'regulatory' or item.get('status') != 'reviewed':
            continue
        d = item.get('details', {})
        try:
            age = (date.today() - date.fromisoformat(d.get('checked_date', ''))).days
        except (ValueError, TypeError):
            continue
        if d.get('decision') != '适用' or d.get('validity') != '现行' or not 0 <= age <= 365:
            continue
        project_applicability.update(code_key(code) for code in standard_pattern.findall(d.get('rule', '')))
    absent_project_checks = [value for key, value in report_codes.items() if key not in project_applicability]
    if absent_project_checks:
        add('regulation_applicability', '本项目法规适用性', 'warning',
            '正文提及以下标准，尚无同编号、现行且已复核的本项目适用性记录：' + '、'.join(absent_project_checks[:20]))
    elif not report_codes:
        add('regulation_applicability', '本项目法规适用性', 'warning',
            '未从正文识别到标准编号；请人工核对法规清单、适用范围和可能遗漏。')
    else:
        add('regulation_applicability', '本项目法规适用性', 'pass',
            '正文识别出的标准编号均有已复核的本项目适用性记录；仍需复核具体条款和可能遗漏。')

    cited_standard_refs = []
    for section in sections:
        body = text_by_section.get(_identity(section), '')
        codes = standard_pattern.findall(body)
        if not codes:
            continue
        cited = [evidence.get(ident, {}) for ident in refs_by_section.get(_identity(section), set())]
        def normalize_code(code):
            return re.sub(r'[\s—-]+', '', code).upper()
        for code in codes:
            matching = [item for item in cited if source_current(item) and normalize_code(code) in
                        {normalize_code(found) for found in standard_pattern.findall(' '.join(str(item.get(key, '')) for key in ('text', 'source', 'source_document', 'locator')))}]
            if not matching:
                cited_standard_refs.append(f'{section.get("title", "")}: {code}')
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
