"""Exact file/text identities; no model or fuzzy similarity decisions."""
import hashlib
import re
import unicodedata


def compact_text(text):
    text = unicodedata.normalize('NFKC', text)
    # Preserve word/number boundaries: table values "1 2" must not become "12".
    return re.sub(r'\s+', lambda match: ' ' if match.start() and match.end() < len(text)
                  and text[match.start()-1].isascii() and text[match.start()-1].isalnum()
                  and text[match.end()].isascii() and text[match.end()].isalnum() else '', text)


def chunk_key(text):
    return hashlib.sha256(compact_text(text).encode()).hexdigest()


def document_keys(text):
    lines = unicodedata.normalize('NFKC', text).splitlines()
    # Recognised download wrappers are not part of the regulation's body.
    lines = [line for line in lines if not re.search(
        r'^\s*(?:样稿引用[:：]|来源[:：]|采集日期[:：]|版本与项目适用性待核验|原文链接[:：])'
        r'|北大法宝|法宝快讯|扫描二维码阅读原文|欢迎查看所有产品和服务|www\.pkulaw\.com', line)]
    clean = '\n'.join(lines).strip()
    compact = compact_text(clean)
    if not compact:
        return set()
    keys = {'text-' + hashlib.sha256(compact.encode()).hexdigest()}
    # Strip the portal/preamble only for recognisable law documents, never for a
    # project report that merely quotes statutes or appends legal references.
    title = re.compile(r'^中华人民共和国[\u4e00-\u9fff]{1,40}(?:法|条例)(?:\(\d{4}年?(?:修正|修订)\))?$')
    is_law = any(title.fullmatch(compact_text(line)) for line in lines[:120])
    article = re.search(r'(?m)^\s*第\s*一\s*条', clean)
    project_preamble = article and re.search(r'本项目|建设单位|项目名称|评价报告|设计专篇', clean[:article.start()])
    if article and not project_preamble and (is_law and article.start() < 6000 or not clean[:article.start()].strip()):
        body = clean[article.start():]
        articles = set(re.findall(r'第\s*([零〇一二三四五六七八九十百千万0-9\s]+)\s*条', body))
        if len(articles) >= 2 and len(compact_text(body)) >= 200:
            body_lines = [line for line in body.splitlines() if not title.fullmatch(compact_text(line))]
            keys.add('law-' + chunk_key('\n'.join(body_lines)))
    return keys


def joined_blocks(parsed):
    return '\n\n'.join(block['text'] for block in parsed.get('blocks', []) if block.get('text', '').strip())


def legacy_documents(records):
    """Reassemble complete importer windows for pre-existing chunk-only libraries."""
    groups = {}
    for record in records:
        match = re.fullmatch(r'(.+) · (.+) · (\d+)', record.get('title', ''))
        if match:
            groups.setdefault(match[1], []).append((match[2], int(match[3]), record))
    for pieces in groups.values():
        blocks = {}; valid = True
        for locator, offset, record in pieces:
            slots = blocks.setdefault(locator, {})
            if offset in slots and slots[offset] != record['content']:
                valid = False; break
            slots[offset] = record['content']
        if not valid:
            continue
        restored = []
        for locator, slots in sorted(blocks.items(), key=lambda item: (re.sub(r'\d+', '', item[0]), [int(n) for n in re.findall(r'\d+', item[0])])):
            body = ''
            for offset, text in sorted(slots.items()):
                if offset > len(body): valid = False; break
                overlap = min(len(text), len(body)-offset)
                if body[offset:offset+overlap] != text[:overlap]: valid = False; break
                body += text[overlap:]
            if not valid: break
            restored.append(body)
        if valid:
            yield pieces[0][2], '\n\n'.join(restored)


def find_duplicate(data, file_sha256='', text='', category=None):
    records = [r for r in data['records'] if not r.get('migrated_to') and (not category or r['category'] == category)]
    by_id = {r['id']: r for r in records}
    keys = document_keys(text) if text else set()
    for manifest in data.get('document_imports', []):
        parts = manifest.get('records', [])
        if not parts or not all(part['id'] in by_id and chunk_key(by_id[part['id']]['content']) == part['hash'] for part in parts):
            continue
        if file_sha256 and manifest.get('file_sha256') == file_sha256 or keys.intersection(manifest.get('text_keys', [])):
            return by_id[parts[0]['id']]
    for record in records:
        if file_sha256 and record.get('file_sha256') == file_sha256 and all(
                chunk_key(old.get('content', record['content'])) == chunk_key(record['content']) for old in record.get('history', [])):
            return record
        if keys and keys.intersection(document_keys(record['content'])):
            return record
    if keys:
        for record, restored in legacy_documents(records):
            if keys.intersection(document_keys(restored)):
                return record
    return None


def quick_upload_text(content, filename):
    """Read text for upload comparison; scanning/OCR remains in normal analysis."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    try:
        suffix = Path(filename).suffix.lower()
        if suffix == '.pdf':
            from io import BytesIO
            from pypdf import PdfReader
            pdf = PdfReader(BytesIO(content))
            if len(pdf.pages) > 200:
                return ''
            return '\n\n'.join(page.extract_text() or '' for page in pdf.pages)
        if suffix not in {'.txt', '.md', '.csv', '.docx', '.json'}:
            return ''
        from .documents import parse_file
        with TemporaryDirectory(prefix='safety-upload-identity-') as folder:
            file = Path(folder) / Path(filename).name
            file.write_bytes(content)
            return joined_blocks(parse_file(file))
    except Exception:
        return ''  # Failure to prove equality must not reject a valid upload.
