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
    return "\n".join(line.strip() for line in (result.txts or ()) if line.strip())
