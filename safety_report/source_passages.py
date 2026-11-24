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


def paragraph_passages(analysis,file):
    chunks=[c for c in analysis.get('chunks',[])+analysis.get('reference_chunks',[]) if c.get('sha256')==file['sha256']]
    documents=[d for d in analysis.get('documents',[])+analysis.get('reference_documents',[]) if d.get('sha256')==file['sha256']]
    if not documents:
        for chunk in chunks:
            yield chunk
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


def extraction_passages(analysis,file):
    """Keep the body of a source subsection together, including unlabelled continuation paragraphs."""
    contexts={}
    for doc in analysis.get('documents',[])+analysis.get('reference_documents',[]):
        if doc.get('sha256')!=file['sha256']:continue
        parents={}
        for block in doc.get('blocks',[]):
            level=block.get('level')
            if level in (1,2,3):
                parents={k:v for k,v in parents.items() if k<level}
                parents[level]=block['text']
            toc='toc' in (block.get('style_id','')+' '+block.get('style_name','')).lower() or '目录' in block.get('style_name','')
            contexts[block['locator']]=('/'.join(parents.values()),level in (1,2,3) or toc)
    pending=[];heading='';size=0
    def packed():
        first=pending[0];text='\n\n'.join(p['text'] for p in pending)
        spans=[{'locator':p['locator'],'evidence_id':p['id'],'text':p['text']} for p in pending]
        return {**first,'text':text,'source_heading':heading,
                'id':first['id'] if len(pending)==1 else 'passage-'+hashlib.sha256((file['sha256']+repr(spans)).encode()).hexdigest()[:24],
                'source_spans':spans,'content_block_version':1}
    for passage in paragraph_passages(analysis,file):
        passage={**passage,'text':passage['text'].strip()}
        context,skip=contexts.get(passage['locator'],(passage.get('source_heading',''),False))
        if skip:
            if pending:yield packed();pending=[];size=0
            continue
        # Without a reliable heading boundary, keep original paragraphs intact.
        if pending and (not context or context!=heading or size+len(passage['text'])+2>12000):
            yield packed();pending=[];size=0
        if not pending:heading=context
        pending.append(passage);size+=len(passage['text'])+2
    if pending:yield packed()
