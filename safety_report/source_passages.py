"""Recover paragraph-sized, verbatim source spans from full blocks, including PDF soft wraps."""
import hashlib
import re


def paragraph_spans(block):
    text=block.get('text','')
    if block.get('kind')!='paragraph' or not block['locator'].startswith('page['):
        return [text] if text.strip() else []
    spans=[];start=None;offset=0
    for line in text.splitlines(keepends=True):
        value=line.strip()
        heading=bool(re.match(r'^(?:第.{1,8}[部分章节]|\d{1,2}[.、]\s*\D|一般职业卫生建议$|安全处置注意事项$|安全储存.{0,30}$|操作处置.{0,30}$|按照.*(?:法规|规定).*储存)',value))
        separator=not value or value in {':','：'}
        if (separator or heading) and start is not None:
            part=text[start:offset].strip()
            if part:spans.append(part)
            start=None
        if not separator and start is None:start=offset
        offset+=len(line)
    if start is not None:
        part=text[start:].strip()
        if part:spans.append(part)
    return spans


def split_large_passage(text,limit=12000):
    while len(text)>limit:
        cut=max(text.rfind('。',0,limit),text.rfind('；',0,limit),text.rfind('\n',0,limit))
        if cut<0:
            # Keep an unbroken long source intact, rather than silently cutting a word.
            yield text;return
        yield text[:cut+1].strip();text=text[cut+1:].strip()
    if text:yield text


def extraction_passages(analysis,file):
    chunks=[c for c in analysis.get('chunks',[])+analysis.get('reference_chunks',[]) if c.get('sha256')==file['sha256']]
    documents=[d for d in analysis.get('documents',[])+analysis.get('reference_documents',[]) if d.get('sha256')==file['sha256']]
    if not documents:
        for chunk in chunks:
            lines=chunk['text'].splitlines()
            if len(lines)>1 and all(re.match(r'^\s*(?:GB|AQ)\s*\d',line) for line in lines):
                for line in lines:yield {**chunk,'text':line}
            else:yield chunk
        return
    seen=set()
    for doc in documents:
        for block in doc.get('blocks',[]):
            for raw in paragraph_spans(block):
                for text in split_large_passage(raw):
                    key=(block['locator'],text)
                    if key in seen:continue
                    seen.add(key)
                    match=next((c for c in chunks if c['locator']==block['locator'] and text in c['text']),None)
                    yield {'id':match['id'] if match else 'passage-'+hashlib.sha256((file['sha256']+block['locator']+text).encode()).hexdigest()[:24],
                        'source':file['name'],'sha256':file['sha256'],'locator':block['locator'],'text':text,
                        'source_heading':match.get('source_heading','') if match else '', 'verbatim_full_passage':True}
