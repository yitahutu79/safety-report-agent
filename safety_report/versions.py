import copy
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import secrets
import shutil


def version_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(4)


def version_directory(target, ident):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{8}', ident):
        raise ValueError('版本编号无效')
    path = Path(target) / 'versions' / ident
    if not (path / 'meta.json').exists():
        raise ValueError('报告版本不存在')
    return path


def history(target):
    result = []
    for path in (Path(target) / 'versions').glob('*/meta.json'):
        try:
            result.append(json.loads(path.read_text()))
        except (ValueError, OSError):
            continue
    return sorted(result, key=lambda r: r['created_at'], reverse=True)


def load_report(target, ident=None):
    directory = version_directory(target, ident) if ident else Path(target)
    path = directory / 'report.json'
    return json.loads(path.read_text()) if path.exists() else None


def audit(report):
    return {'unconfirmed_fields': report.get('unconfirmed_fields', []),
        'chapters': [{'title': s['title'], 'missing': s.get('missing', []), 'review': s.get('review', [])} for s in report['sections']],
        'structure_changes': report.get('structure_changes', []),
        'figure_warnings': report.get('figure_warnings', []), 'generation_errors': report.get('generation_errors', []),
        'readability_review': '已检查摘录标记、表格原文混排和段落与引用来源的相似度；仍需人工审阅表达逻辑与专业内容' if report.get('quality_checked') else '未通过智能正文可读性检查',
        'editorial_plan': [{'title': section['title'], 'source': section.get('editorial_plan_source', 'model'), 'items': section.get('editorial_plan', [])}
                           for section in report['sections'] if section.get('editorial_plan')],
        'quality_review': report.get('quality_review', {'overall': 'not_run', 'checks': [], 'counts': {'pass': 0, 'warning': 0, 'fail': 0}}),
        'layout_review': 'Word/PDF 逐页版式待人工验收',
        'evidence_review': '编号有效不等于语义得到证明，事实与技术结论需核对'}


def review_html(report):
    review = audit(report)
    evidence = {e['id']: e for e in report.get('evidence', [])}
    parts = ['<h1>报告核对清单</h1><p>这份清单与正文分开保存。请核查缺失资料、技术结论和最终排版。</p>', '<p>' + escape(review['readability_review']) + '</p>']
    if review['unconfirmed_fields']:
        parts.append('<p>基本信息待补充：' + escape('、'.join(review['unconfirmed_fields'])) + '</p>')
    quality = review.get('quality_review', {})
    if quality.get('checks'):
        parts.append('<h2>一期质量检查</h2><p>' + escape(quality.get('note', '自动检查结果')) +
                     ' 通过：' + str(quality.get('counts', {}).get('pass', 0)) +
                     '；待核对：' + str(quality.get('counts', {}).get('warning', 0)) +
                     '；未通过：' + str(quality.get('counts', {}).get('fail', 0)) + '</p><ul>')
        labels = {'pass': '通过', 'warning': '待核对', 'fail': '未通过'}
        for check in quality['checks']:
            parts.append('<li><b>' + escape(labels.get(check.get('status'), check.get('status', '')) + ' · ' + check.get('title', '')) + '</b>：' + escape(check.get('detail', '')) + '</li>')
        parts.append('</ul>')
    if review['structure_changes']:
        parts.append('<h2>章节结构变更</h2><ul>' + ''.join('<li>' + escape(item) + '</li>' for item in review['structure_changes']) + '</ul>')
    for section in review['chapters']:
        parts.append('<h2>' + escape(section['title']) + '</h2><ul>')
        parts.extend('<li>' + escape(s) + '</li>' for s in section['missing'] + section['review'])
        parts.append('</ul>')
    if review['editorial_plan']:
        parts.append('<h2>资料筛选与编辑记录</h2><p>正文中的内容经过主题筛选和归并；以下记录列出主要取舍，完整证据出处见下方。若记录来自正文引用，它只表示证据使用情况，不代表模型说明了全部省略原因。</p>')
        labels = {'use': '采用并整理', 'omit': '省略', 'verify': '待核对'}
        for section in review['editorial_plan']:
            source_note = '（模型编辑记录）' if section['source'] == 'model' else '（根据正文引用汇总）'
            parts.append('<h3>' + escape(section['title'] + source_note) + '</h3><ul>')
            for item in section['items']:
                label = labels.get(item.get('decision'), '编辑处理')
                if section['source'] == 'citations' and item.get('decision') == 'omit':
                    label = '未直接引用'
                refs = [evidence[eid]['source'] + ' ' + evidence[eid]['locator'] for eid in item.get('evidence_ids', []) if eid in evidence]
                source_note = '（资料：' + '；'.join(refs) + '）' if refs else ''
                parts.append('<li><b>' + escape(label) + ' · ' + escape(item.get('topic', '')) + '</b>：' + escape(item.get('summary', '') + source_note) + '</li>')
            parts.append('</ul>')
    parts.extend('<p>' + escape(s) + '</p>' for s in review['figure_warnings'])
    parts.append('<h2>资料出处</h2>')
    for section in report['sections']:
        for index, item in enumerate(section.get('paragraphs', []) + section.get('tables', []), 1):
            refs = [evidence[eid] for eid in item.get('evidence_ids', []) if eid in evidence]
            parts.append('<p><b>' + escape(section['title']) + f' · 内容{index}</b><br>' + '<br>'.join(escape(e['source'] + ' ' + e['locator']) for e in refs) + ('人工编辑内容' if item.get('human_edited') else '') + '</p>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>报告核对清单</title><style>body{max-width:900px;margin:40px auto;padding:0 24px;font:15px/1.9 sans-serif;color:#203b33}h1{font-size:26px}h2{font-size:19px;margin-top:32px}li,p{overflow-wrap:anywhere}</style>' + ''.join(parts) + '</html>'


def commit(target, report, export, kind='generation', description=''):
    target = Path(target)
    ident = version_id()
    temp = target / 'versions' / ('.pending-' + ident)
    temp.mkdir(parents=True)
    try:
        export(report, temp / 'report.docx')
        (temp / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (temp / 'review.json').write_text(json.dumps(audit(report), ensure_ascii=False, indent=2))
        (temp / 'review.html').write_text(review_html(report))
        meta = {'id': ident, 'created_at': datetime.now(timezone.utc).isoformat(), 'kind': kind,
                'description': description[:200], 'mode': report.get('mode', 'legacy'), 'model_name': report.get('model_name', ''),
                'updated_chapters': report.get('updated_chapters', []), 'status': report.get('status', 'draft')}
        (temp / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        final = target / 'versions' / ident
        temp.rename(final)
        for name in ('report.docx', 'report.json', 'review.json', 'review.html'):
            pending = target / ('.' + name + '.tmp')
            shutil.copyfile(final / name, pending)
            pending.replace(target / name)
        return meta
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def preserve_legacy(target):
    target = Path(target)
    if history(target) or not (target / 'report.json').exists():
        return
    ident = version_id()
    folder = target / 'versions' / ident
    folder.mkdir(parents=True)
    for name in ('report.json', 'report.docx', 'review.json', 'review.html'):
        if (target / name).exists():
            shutil.copyfile(target / name, folder / name)
    report = load_report(target)
    if not (folder / 'review.html').exists():
        (folder / 'review.html').write_text(review_html(report))
    (folder / 'meta.json').write_text(json.dumps({'id': ident, 'created_at': datetime.now(timezone.utc).isoformat(),
        'kind': 'legacy', 'description': '升级前的原始草稿（保留）', 'mode': report.get('mode', 'legacy'),
        'model_name': '', 'updated_chapters': [], 'status': 'draft'}, ensure_ascii=False, indent=2))


def apply_edits(report, changed_sections, add_chapter=None, delete_chapter_ids=None):
    if not report:
        raise ValueError('请先生成一版草稿')
    if not isinstance(changed_sections, list) or (not changed_sections and add_chapter is None and not delete_chapter_ids):
        raise ValueError('没有需要保存的章节')
    result = copy.deepcopy(report)
    available = {s['title']: s for s in result['sections']}
    changed = set()
    for edit in changed_sections:
        if not isinstance(edit, dict) or edit.get('title') not in available:
            raise ValueError('编辑章节与当前报告不一致，请刷新页面')
        section = available[edit['title']]
        paragraphs = edit.get('paragraphs')
        if not isinstance(paragraphs, list) or len(paragraphs) > 300:
            raise ValueError('段落格式不正确或过多')
        valid_headings = [section['title']] + section.get('subheadings', [])
        old = section.get('paragraphs', [])
        updated = []
        for index, item in enumerate(paragraphs):
            if not isinstance(item, dict) or not isinstance(item.get('text'), str) or len(item['text']) > 30000 or item.get('heading', section['title']) not in valid_headings:
                raise ValueError('段落内容或所属标题不正确')
            value = item['text'].strip()
            if not value:
                continue
            original_index = item.get('original_index')
            original = old[original_index] if isinstance(original_index, int) and 0 <= original_index < len(old) else {}
            updated.append({**original, 'heading': item.get('heading', section['title']), 'text': value,
                            'evidence_ids': original.get('evidence_ids', []),
                            'human_edited': original.get('human_edited', False) or value != original.get('text')})
        section['paragraphs'] = updated
        if 'tables' in edit:
            tables = edit['tables']
            originals = section.get('tables', [])
            if not isinstance(tables, list) or len(tables) != len(originals):
                raise ValueError('表格结构与当前章节不一致')
            revised_tables = []
            for original, table in zip(originals, tables):
                if not isinstance(table, dict) or not isinstance(table.get('headers'), list) or not table['headers'] or len(table['headers']) > 16:
                    raise ValueError('表头格式不正确')
                width = len(table['headers'])
                rows = table.get('rows')
                if not isinstance(rows, list) or len(rows) > 300 or any(not isinstance(row, list) or len(row) != width for row in rows):
                    raise ValueError('表格行列格式不正确')
                if not all(isinstance(cell, str) and len(cell) <= 10000 for row in [table['headers']] + rows for cell in row):
                    raise ValueError('表格内容必须是长度合理的文本')
                revised_tables.append({**original, 'headers': table['headers'], 'rows': rows,
                    'human_edited': original.get('human_edited', False) or table['headers'] != original['headers'] or rows != original['rows']})
            section['tables'] = revised_tables
        changed.add(section.get('id') or (re.match(r'\d+', section['title']).group() if re.match(r'\d+', section['title']) else ''))
    if add_chapter is not None:
        if not isinstance(add_chapter, str) or not 2 <= len(add_chapter.strip()) <= 120:
            raise ValueError('新增章节标题须为 2 到 120 个字符')
        title = add_chapter.strip()
        if any(section['title'].casefold() == title.casefold() for section in result['sections']):
            raise ValueError('当前报告已存在同名章节')
        import secrets
        ident = 'custom-' + secrets.token_hex(8)
        result['sections'].append({'id': ident, 'title': title, 'custom': True, 'subheadings': [],
                                   'paragraphs': [], 'tables': [], 'missing': ['本章尚无正文，请添加内容或选择本章让模型编写。'],
                                   'review': ['用户新增的自定义章节，需确认是否符合本项目报告结构。']})
        changed.add(ident)
        result.setdefault('structure_changes', []).append('新增自定义章节：' + title)
    delete_chapter_ids = delete_chapter_ids or []
    if not isinstance(delete_chapter_ids, list) or len(delete_chapter_ids) > len(result['sections']):
        raise ValueError('删除章节列表格式不正确')
    if delete_chapter_ids:
        identities = {section.get('id') or (re.match(r'\d+', section['title']).group() if re.match(r'\d+', section['title']) else ''): section
                      for section in result['sections']}
        if any(ident not in identities for ident in delete_chapter_ids):
            raise ValueError('要删除的章节已不存在，请刷新页面')
        if len(result['sections']) - len(set(delete_chapter_ids)) < 1:
            raise ValueError('报告至少需要保留一个章节')
        deleted_template_ids = {ident for ident in delete_chapter_ids if ident.isdigit()}
        result['excluded_chapters'] = sorted(set(result.get('excluded_chapters', [])) | deleted_template_ids)
        result['sections'] = [section for section in result['sections']
                              if (section.get('id') or (re.match(r'\d+', section['title']).group() if re.match(r'\d+', section['title']) else '')) not in set(delete_chapter_ids)]
        result.setdefault('structure_changes', []).extend('删除章节：' + identities[ident]['title'] for ident in delete_chapter_ids)
    if add_chapter is not None or delete_chapter_ids:
        result['quality_checked'] = False
        result['status'] = 'in_progress'
    result['updated_chapters'] = sorted(changed)
    result['instructions'] = '使用者在页面编辑并保存章节'
    return result
