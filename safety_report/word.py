"""按当前编辑内容生成独立Word草稿，图件仅使用用户明确选入的来源。"""
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


def table(headers, rows, total_width=9184, layout=None):
    if layout:
        from .table_reuse import compatible_layout
        if compatible_layout({'headers':headers,'rows':rows,'source_table_layout':layout}):return native_table(headers,rows,layout,total_width)
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


def image_paragraph(rid, index, width, height, max_width=5_500_000, max_height=7_500_000):
    cx = max_width
    cy = int(cx * height / width)
    if cy > max_height:
        cx = int(cx * max_height / cy)
        cy = max_height
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
    profile = {**profile, **report.get('template_format', {})}
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
    from .pipeline import section_identity
    relationships = [f'<Relationship Id="rStyles" Type="{R}/styles" Target="styles.xml"/>', f'<Relationship Id="rSettings" Type="{R}/settings" Target="settings.xml"/>']
    image_files = []
    rendered_figures = []
    source_rendered = {}
    original_pages=[]
    section_format=(profile.get('sections') or [{}])[0]
    page_size=section_format.get('pgSz',{'w':'11905','h':'16838'})
    page_margins=section_format.get('pgMar',{'top':'1417','right':'1134','bottom':'1134','left':'1587'})
    available_width=(int(page_size.get('w',11905))-int(page_margins.get('left',1587))-int(page_margins.get('right',1134)))*635
    available_height=(int(page_size.get('h',16838))-int(page_margins.get('top',1417))-int(page_margins.get('bottom',1134))-600)*635
    for index, figure in enumerate(figures, 1):
        if figure.get('appendix_table') or figure.get('appendix_text'):
            original_pages.append((figure,None));continue
        data = Path(figure['path']).read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            continue
        width, height = struct.unpack('>II', data[16:24])
        rid = f'rImage{index}'
        image_files.append((f'word/media/image{index}.png', data))
        relationships.append(f'<Relationship Id="{rid}" Type="{R}/image" Target="media/image{index}.png"/>')
        if figure.get('original_appendix'):
            original_pages.append((figure,image_paragraph(rid,index,width,height,available_width,available_height-600*635 if figure['original_page']==1 else available_height)))
            continue
        image_parts = [paragraph(figure['caption'], 'Caption'), image_paragraph(rid, index, width, height)]
        if figure.get('source'):
            image_parts.append(paragraph(figure['source'], 'Evidence'))
        entry=(figure.get('placement') or {}, image_parts)
        if figure.get('document_figure_id'):source_rendered[figure['document_figure_id']]=entry
        else:rendered_figures.append(entry)
    for section in report['sections']:
        section_id = section_identity(section)
        basis_section = (report.get('report_type', 'facility_design') == 'facility_design'
                         and section_id == '1' and '设计依据' in section['title'] and not profile.get('paragraph_formats'))
        parts.append(paragraph(section['title'], 'BasisHeading1' if basis_section else 'Heading1'))
        if section.get('generation_status') == 'not_generated':
            parts.append(paragraph('本章尚未生成。请在工作台按章补写后，再导出完整报告。'))
            for t in section.get('tables',[]):
                if t.get('source_table_id'):
                    parts.append(paragraph(t['caption'],'Caption'));parts.append(table(t['headers'],t['rows'],layout=t.get('source_table_layout')))
            for location,image_parts in list(rendered_figures)+list(source_rendered.values()):
                if location.get('section_id')==section_id:
                    if location.get('heading') and location['heading']!=section['title']:
                        number=re.match(r'^\d+(?:\.\d+)*',location['heading']);level=min(3,len(number.group().split('.'))) if number else 2
                        parts.append(paragraph(location['heading'],'Heading'+str(level)))
                    parts.extend(image_parts)
            continue
        if section.get('generation_status') == 'failed' or section.get('needs_rewrite') or section.get('generation_error'):
            parts.append(paragraph('本章未通过生成检查，本次导出不包含旧版正文。请在工作台单独重试本章；失败信息见核对清单。'))
            for location,image_parts in list(rendered_figures)+list(source_rendered.values()):
                if location.get('section_id')==section_id:
                    if location.get('heading') and location['heading']!=section['title']:
                        number=re.match(r'^\d+(?:\.\d+)*',location['heading']);level=min(3,len(number.group().split('.'))) if number else 2
                        parts.append(paragraph(location['heading'],'Heading'+str(level)))
                    parts.extend(image_parts)
            continue
        from .content_order import order_content
        blocks=order_content(section)
        active_heading=None
        def legacy_heading_figures(heading):
            return [image_parts for location,image_parts in rendered_figures if location.get('section_id')==section_id and location.get('heading')==heading and location.get('paragraph_index') is None]
        for block in blocks:
            kind=block['kind'];heading=block['heading']
            if kind=='heading':
                if active_heading is not None:
                    for image_parts in legacy_heading_figures(active_heading):parts.extend(image_parts)
                active_heading=heading
                if heading!=section['title']:
                    match=re.match(r'\d+(?:\.\d+)*',heading);level=len(match.group().split('.')) if match else 2
                    parts.append(paragraph(heading,'BasisHeading2' if basis_section and level==2 else 'Heading'+str(min(level,3))))
            elif kind=='paragraph':
                item=section['paragraphs'][block['index']]
                parts.append(paragraph(item['text'],'BasisEntry' if basis_section else 'Normal'))
                for location,image_parts in rendered_figures:
                    if location.get('section_id')==section_id and location.get('paragraph_index')==block['index']:parts.extend(image_parts)
            elif kind=='table':
                item=section['tables'][block['index']]
                parts.append(paragraph(item['caption'],'Caption'))
                parts.append(table(item['headers'],item['rows'],layout=item.get('source_table_layout')))
            elif kind=='figure':
                entry=source_rendered.get(section['figures'][block['index']]['id'])
                if entry and entry[0].get('section_id')==section_id:parts.extend(entry[1])
        if active_heading is not None:
            for image_parts in legacy_heading_figures(active_heading):parts.extend(image_parts)
        # Legacy project figures without document-image IDs retain their declared placement.
        for location,image_parts in rendered_figures:
            if location.get('section_id')==section_id and not location.get('heading') and location.get('paragraph_index') is None:parts.extend(image_parts)
        if not blocks:parts.append(paragraph('本章尚待补充项目资料。'))
    # 缺失项、审阅意见和证据追溯在独立 review.html / JSON 中呈现，不穿插正文。
    appendix_figures = [image_parts for location, image_parts in list(rendered_figures)+list(source_rendered.values()) if not location.get('section_id')]
    if appendix_figures:
        parts.append(paragraph('项目图件', 'Heading1'))
        for image_parts in appendix_figures:
            parts.extend(image_parts)
    # Each original page remains a single page image; do not rebuild its text or symbols.
    for figure,image in original_pages:
        parts.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        if figure['original_page']==1:
            parts.append(paragraph(figure.get('attachment_title') or '附录 · '+figure['caption'],'Heading1'))
        if figure.get('appendix_table'):
            t=figure['appendix_table'];parts.append(table(t['headers'],t['rows'],layout=t.get('source_table_layout')))
        elif figure.get('appendix_text'):parts.append(paragraph(figure['appendix_text']))
        else:parts.append(image)
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
    styles += '''<w:style w:type="paragraph" w:styleId="BasisHeading1">
<w:name w:val="Design basis chapter"/><w:basedOn w:val="Heading1"/>
<w:pPr><w:pageBreakBefore/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="BasisHeading2">
<w:name w:val="Design basis heading"/><w:basedOn w:val="Heading2"/>
<w:pPr><w:spacing w:before="120" w:after="120" w:line="360" w:lineRule="auto"/></w:pPr>
<w:rPr><w:rFonts w:ascii="黑体" w:hAnsi="黑体" w:eastAsia="黑体"/><w:b w:val="0"/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BasisEntry"><w:name w:val="Design basis entry"/>
<w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="both"/><w:autoSpaceDE w:val="0"/><w:autoSpaceDN w:val="0"/>
<w:spacing w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:firstLine="560"/></w:pPr>
</w:style></w:styles>'''
    if profile.get('paragraph_formats'):
        from .report_template import apply_paragraph_formats
        styles = apply_paragraph_formats(styles, profile['paragraph_formats'])
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


def native_table(headers,rows,layout,total_width=9184):
    """Rebuild safe OOXML from source geometry, with no external source relationships."""
    matrix=[headers]+rows;grid=layout['grid'];total=max(1,sum(grid));widths=[max(1,int(total_width*w/total)) for w in grid]
    starts={(c['row'],c['col']):c for c in layout['cells']};covers={}
    for cell in layout['cells']:
        for r in range(cell['row'],cell['row']+cell['rowspan']):
            for c in range(cell['col'],cell['col']+cell['colspan']):covers[r,c]=cell
    parts=['<w:tbl><w:tblPr><w:tblW w:w="'+str(total_width)+'" w:type="dxa"/><w:tblBorders>'+''.join('<w:'+e+' w:val="single" w:sz="4" w:color="AAB4C0"/>' for e in ('top','left','bottom','right','insideH','insideV'))+'</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>'+''.join('<w:gridCol w:w="'+str(w)+'"/>' for w in widths)+'</w:tblGrid>']
    for ri,row in enumerate(matrix):
        parts.append('<w:tr>'+('<w:trPr><w:tblHeader/></w:trPr>' if ri<layout.get('header_rows',1) else ''))
        col=0
        while col<len(row):
            cell=covers.get((ri,col));span=cell['colspan'] if cell else 1
            if cell and col!=cell['col']:col+=1;continue
            continued=cell and ri>cell['row'];props='<w:tcW w:w="'+str(sum(widths[col:col+span]))+'" w:type="dxa"/>'
            if span>1:props+='<w:gridSpan w:val="'+str(span)+'"/>'
            if cell and cell['rowspan']>1:props+='<w:vMerge'+('/>' if continued else ' w:val="restart"/>')
            text='' if continued else row[col]
            parts.append('<w:tc><w:tcPr>'+props+'<w:vAlign w:val="center"/></w:tcPr>'+paragraph(text,'TableText')+'</w:tc>');col+=span
        parts.append('</w:tr>')
    parts.append('</w:tbl>');return ''.join(parts)
