"""Local OCR for PDF pages without sufficient embedded text."""
from contextlib import closing
from functools import lru_cache
from io import BytesIO
from threading import Lock

from .assets import PDF_LOCK

_ENGINE_LOCK = Lock()


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def recognize_pdf_page(path, page_index):
    import pypdfium2

    with PDF_LOCK, pypdfium2.PdfDocument(path) as pdf:
        with closing(pdf[page_index]) as page:
            width, height = page.get_size()
            # Bound the raster size, including for large-format drawings.
            with closing(page.render(scale=min(4, 2800 / max(width, height)))) as bitmap, BytesIO() as image:
                bitmap.to_pil().save(image, format="PNG")
                png = image.getvalue()

    with _ENGINE_LOCK:
        result = _engine()(png)
    return ordered_ocr_text(result.txts, result.boxes)


def ordered_ocr_text(texts, boxes):
    """Sort by spatial rows, keeping left labels before their right-hand values."""
    texts=[] if texts is None else list(texts)
    if boxes is None or len(boxes)!=len(texts):
        return "\n".join(t.strip() for t in texts if t.strip())
    items=[]
    for text,box in zip(texts,boxes):
        points=list(box);xs=[float(p[0]) for p in points];ys=[float(p[1]) for p in points]
        if text.strip():items.append((min(ys),min(xs),max(ys)-min(ys),text.strip()))
    rows=[]
    for item in sorted(items):
        if rows and abs(item[0]-rows[-1][0][0])<=max(3,min(item[2],rows[-1][0][2])*.45):rows[-1].append(item)
        else:rows.append([item])
    return "\n".join("    ".join(p[3] for p in sorted(row,key=lambda p:p[1])) for row in rows)
