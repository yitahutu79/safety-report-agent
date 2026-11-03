"""附件分类和图件渲染。CAD 原图归档，临时文件不作为工程证据。"""
from pathlib import Path
import threading
import re

TEXT = {'.docx', '.pdf', '.csv', '.txt', '.md', '.json'}
RASTER = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
DRAWINGS = {'.dwg', '.dxf', '.svg'}
OTHER = {'.doc', '.xls', '.xlsx', '.ppt', '.pptx'}
TEMP = {'.dwl', '.dwl2', '.bak', '.tmp', '.ac$', '.sv$'}
PDF_LOCK = threading.RLock()


def classify(name, role='auto'):
    suffix = Path(name).suffix.lower()
    if suffix in {'.dwl', '.dwl2'}:
        return {'skip': True, 'message': '这是 CAD/办公软件临时文件，不含可用图纸正文；请选择同名 DWG，或导出的 PDF/PNG/JPG'}
    if suffix in TEMP or Path(name).name.lower() in {'.ds_store', 'thumbs.db'} or Path(name).name.startswith('~$'):
        return {'skip': True, 'message': '这是备份或临时辅助文件，当前不纳入正式资料；请在原软件确认并导出有效版本后上传'}
    if suffix not in TEXT | RASTER | DRAWINGS | OTHER:
        raise ValueError('暂不支持此格式；可导入 Word、PDF、文本、图片或 DWG/DXF 原图')
    if role not in {'auto', 'source', 'reference', 'figure', 'attachment'}:
        raise ValueError('资料用途无效')
    if role == 'auto':
        drawing_pdf = suffix == '.pdf' and re.search(r'总图|工艺.*图|布置图|位置图|示意图|消防.*图|电气图', Path(name).stem)
        role = 'figure' if suffix in RASTER or drawing_pdf else 'attachment' if suffix in DRAWINGS | OTHER else 'source'
    renderable = suffix in RASTER or suffix == '.pdf'
    status = '可读取' if suffix in TEXT else '可作图件' if suffix in RASTER else '待转换'
    if suffix in DRAWINGS:
        status = '已归档，需导出 PDF 或图片才能预览和嵌入'
    if role == 'reference':
        status = '参考样式，不作为项目事实'
    return {'role': role, 'status': status, 'renderable': renderable,
            'include': role == 'figure' and renderable, 'pages': '1', 'caption': Path(name).stem}


def parse_pages(value, count=None):
    if not isinstance(value, str) or len(value) > 120:
        raise ValueError('页码格式不正确')
    pages = []
    for piece in value.replace('，', ',').split(','):
        piece = piece.strip()
        if not re.fullmatch(r'\d+(?:-\d+)?', piece):
            raise ValueError('页码请填写 1 或 1,3-5 等格式')
        ends = list(map(int, piece.split('-')))
        start, end = ends[0], ends[-1]
        if not 1 <= start <= end or end - start > 19:
            raise ValueError('页码范围无效，单个文件最多选 20 页')
        pages += list(range(start, end + 1))
    pages = sorted(set(pages))
    if len(pages) > 20 or (count is not None and any(p > count for p in pages)):
        raise ValueError('选择页码超过文件页数或单文件 20 页上限')
    return pages


def render_file(target, file, page=1):
    from PIL import Image, ImageOps
    path = Path(target) / 'uploads' / file['stored']
    cache = Path(target) / 'rendered'
    cache.mkdir(exist_ok=True)
    output = cache / (file['sha256'] + '-' + str(page) + '.png')
    if output.exists():
        return output
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise ValueError('PDF 图件渲染组件未安装，请安装 requirements.txt') from None
        # PDFium 不可在多个线程中并发调用。
        with PDF_LOCK:
            with pdfium.PdfDocument(path) as pdf:
                if not 1 <= page <= len(pdf):
                    raise ValueError('PDF 页码超出范围')
                pdf_page = pdf[page - 1]
                width, height = pdf_page.get_size()
                scale = min(2, 2400 / max(width, height))
                bitmap = pdf_page.render(scale=scale)
                image = bitmap.to_pil().convert('RGB')
                image.save(output)
                bitmap.close()
                pdf_page.close()
    elif suffix in RASTER:
        Image.MAX_IMAGE_PIXELS = 60_000_000
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original)
            image.thumbnail((3000, 3000))
            background = Image.new('RGB', image.size, 'white')
            if image.mode in {'RGBA', 'LA'} or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                background.paste(rgba, mask=rgba.getchannel('A'))
            else:
                background.paste(image.convert('RGB'))
            background.save(output)
    else:
        raise ValueError('原图需要先从 CAD 或办公软件导出 PDF/PNG/JPG')
    return output


def collect_figures(target, files):
    figures, warnings = [], []
    for file in files:
        if not file.get('active', True) or not file.get('include'):
            continue
        try:
            suffix = Path(file['stored']).suffix.lower()
            if suffix == '.pdf':
                from pypdf import PdfReader
                pages = parse_pages(file.get('pages', '1'), len(PdfReader(Path(target) / 'uploads' / file['stored']).pages))
            else:
                pages = [1]
            for page in pages:
                figures.append({'path': str(render_file(target, file, page)),
                    'caption': file.get('caption') or file['name'],
                    'source': file['name'] + (f' 第{page}页' if suffix == '.pdf' else '')})
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else '文件无法渲染，请检查是否损坏、加密或格式不匹配'
            warnings.append(file['name'] + '：' + message)
    return figures, warnings
