"""生成独立的 Word 草稿，不复制旧报告的正文、页眉、图片或作者信息。"""
import re
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def paragraph(text, style="Normal"):
    text = ''.join(c for c in text if c in '\t\n\r' or ord(c) >= 32)
    runs = "".join('<w:r><w:t xml:space="preserve">' + escape(line) + '</w:t></w:r>' + ('<w:r><w:br/></w:r>' if i < len(text.splitlines()) - 1 else '')
                   for i, line in enumerate(text.splitlines() or [""]))
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'


def table(headers, rows, total_width=9184):
    count = max(1, len(headers))
    width = total_width // count
    borders = ''.join(f'<w:{edge} w:val="single" w:sz="4" w:color="D9D9D9"/>' for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    result = f'<w:tbl><w:tblPr><w:tblW w:w="{total_width}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders><w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
    result += ''.join(f'<w:gridCol w:w="{width}"/>' for _ in headers) + '</w:tblGrid>'
    for index, row in enumerate([headers] + rows):
        result += '<w:tr>' + ('<w:trPr><w:tblHeader/></w:trPr>' if index == 0 else '')
        for value in row:
            result += f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:vAlign w:val="center"/>'
            if index == 0:
                result += '<w:shd w:fill="E9EDF2"/>'
            result += '</w:tcPr>' + paragraph(str(value), 'TableText') + '</w:tc>'
        result += '</w:tr>'
    return result + '</w:tbl>' + paragraph('')


def image_paragraph(rid, index, width, height):
    cx = 5_500_000
    cy = int(cx * height / width)
    if cy > 7_500_000:
        cx = int(cx * 7_500_000 / cy)
        cy = 7_500_000
    return f'''<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
    <wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>
    <wp:docPr id="{index}" name="报告图件{index}" descr="项目图件"/>
    <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>
    <pic:nvPicPr><pic:cNvPr id="{index}" name="图件{index}"/><pic:cNvPicPr/></pic:nvPicPr>
    <pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
    <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>
    </wp:inline></w:drawing></w:r></w:p>'''


def write_docx(report, profile, path, figures=()):
    fields = report['confirmed_fields']
    project = next((f['value'] for f in fields if f['label'] == '项目名称'), '建设项目')
    company = next((f['value'] for f in fields if f['label'] == '建设单位'), '')
    outline = report.get('mode') in {'outline', 'evidence_outline'}
    report_name = report.get('report_name', profile.get('report_name', '安全设施设计报告'))
    title = project + report_name + ('编写提纲' if outline else '')
    parts = [paragraph(title, 'Title')]
    if company:
        parts.append(paragraph(company, 'Subtitle'))
    parts.append(paragraph('编写提纲' if outline else '编制草稿', 'Subtitle'))
    if not report.get('structure_confirmed', True):
        parts.append(paragraph('本报告采用待双方确认的试用章节结构，须由专业人员核对目录、内容及适用要求。', 'Subtitle'))
    parts.append(paragraph('目录', 'TOCHeading'))
    parts.append('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>请在 Word 中更新目录</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    for section in report['sections']:
        parts.append(paragraph(section['title'], 'Heading1'))
        if section.get('generation_status') == 'not_generated':
            parts.append(paragraph('本章尚未生成。请在工作台按章补写后，再导出完整报告。'))
            continue
        if section.get('generation_status') == 'failed' or section.get('needs_rewrite') or section.get('generation_error'):
            parts.append(paragraph('本章未通过生成检查，本次导出不包含旧版正文。请在工作台单独重试本章；失败信息见核对清单。'))
            continue
        all_items = [('paragraph', p) for p in section.get('paragraphs', [])] + [('table', t) for t in section.get('tables', [])]
        filled = {item.get('heading', section['title']) for _, item in all_items}
        visible = set(filled)
        # 只显示有正文的子节及其父级，避免一百多个空标题和占位句。
        for heading in section.get('subheadings', []):
            number = re.match(r'\d+(?:\.\d+)*', heading)
            if number and any(re.match(rf"^{re.escape(number.group())}\.\d", child) for child in filled):
                visible.add(heading)
        for heading in [section['title']] + section.get('subheadings', []):
            if heading != section['title']:
                if heading not in visible:
                    continue
                match = re.match(r'\d+(?:\.\d+)*', heading)
                level = len(match.group().split('.')) if match else 2
                parts.append(paragraph(heading, 'Heading' + str(min(level, 3))))
            for kind, item in all_items:
                if item.get('heading', section['title']) != heading:
                    continue
                if kind == 'paragraph':
                    parts.append(paragraph(item['text']))
                else:
                    parts.append(paragraph(item['caption'], 'Caption'))
                    parts.append(table(item['headers'], item['rows']))
        if not all_items:
            parts.append(paragraph('本章尚待补充项目资料。'))
    # 缺失项、审阅意见和证据追溯在独立 review.html / JSON 中呈现，不穿插正文。
    relationships = [f'<Relationship Id="rStyles" Type="{R}/styles" Target="styles.xml"/>', f'<Relationship Id="rSettings" Type="{R}/settings" Target="settings.xml"/>']
    image_files = []
    if figures:
        parts.append(paragraph('项目图件', 'Heading1'))
    for index, figure in enumerate(figures, 1):
        image_path = Path(figure['path'])
        data = image_path.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            continue
        width, height = struct.unpack('>II', data[16:24])
        rid = f'rImage{index}'
        image_files.append((f'word/media/image{index}.png', data))
        relationships.append(f'<Relationship Id="{rid}" Type="{R}/image" Target="media/image{index}.png"/>')
        parts += [paragraph(figure['caption'], 'Caption'), image_paragraph(rid, index, width, height)]
        if figure.get('source'):
            parts.append(paragraph(figure['source'], 'Evidence'))
    first_section = (profile.get('sections') or [{}])[0]
    size = first_section.get('pgSz', {'w': '11905', 'h': '16838'})
    margins = first_section.get('pgMar', {'top': '1417', 'right': '1134', 'bottom': '1134', 'left': '1587'})
    attrs = lambda values: ' '.join(f'w:{escape(k)}="{escape(str(v))}"' for k, v in values.items())
    parts.append(f'<w:sectPr><w:pgSz {attrs(size)}/><w:pgMar {attrs(margins)}/></w:sectPr>')
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>{''.join(parts)}</w:body></w:document>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="28"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line="360" w:lineRule="auto" w:after="100"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:ind w:firstLine="560"/></w:pPr></w:style>'''
    for sid, name, points in [('Title', 'Title', 22), ('Subtitle', 'Subtitle', 12), ('Heading1', 'heading 1', 16), ('Heading2', 'heading 2', 16), ('Heading3', 'heading 3', 14), ('Caption', 'caption', 12), ('Evidence', 'Evidence', 9), ('TableText', 'TableText', 10), ('TOCHeading', 'TOC Heading', 16)]:
        outline = f'<w:outlineLvl w:val="{int(sid[-1]) - 1}"/>' if sid.startswith('Heading') else ''
        keep = '<w:keepNext/>' if outline or sid == 'Caption' else ''
        bold = '<w:b/>' if outline or sid == 'Title' else ''
        styles += f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:pPr>{outline}{keep}<w:ind w:firstLine="0"/><w:spacing w:before="160" w:after="120"/></w:pPr><w:rPr>{bold}<w:color w:val="000000"/><w:sz w:val="{points * 2}"/></w:rPr></w:style>'
    styles += '</w:styles>'
    content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/></Types>'''
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rDoc" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', document)
        archive.writestr('word/styles.xml', styles)
        archive.writestr('word/settings.xml', f'<w:settings xmlns:w="{W}"><w:updateFields w:val="true"/></w:settings>')
        archive.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(relationships) + '</Relationships>')
        for name, data in image_files:
            archive.writestr(name, data)
