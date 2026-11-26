"""Separate project/public retrieval and human-labelled retrieval evaluation."""
from .documents import HybridEvidenceIndex, EvidenceIndex, tokens
import re


def search_project(chunks, index_path, query, limit):
    index = HybridEvidenceIndex(chunks, index_path)
    try:
        results = index.search(query, max(limit*3,20))
        results = expand_source_context(chunks,results,query,limit)
        mode = 'hybrid_qdrant_rrf' if index.client and not index.semantic_error else 'keyword_fallback'
        return results, mode, index.semantic_error
    finally:
        index.close()


def expand_source_context(chunks,results,query,limit):
    """Resolve short title hits to adjacent original blocks, never crossing a source revision."""
    def body(item):
        match=re.fullmatch(r'body\[(\d+)\]',item.get('locator',''))
        return int(match[1]) if match else None
    def title(item):
        text=item.get('text','').strip()
        return len(text)<180 and bool(re.match(r'^(?:\d+(?:\.\d+)*|表\s*\d|附件\s*\d|附图\s*\d)',text)) and not re.search(r'[。；]|成立于|经营范围',text)
    pool=chunks
    filenames=re.findall(r'《([^》]+\.(?:pdf|docx|txt|doc))》',query,re.I)
    if filenames and any(c.get('source') in filenames for c in pool):pool=[c for c in pool if c.get('source') in filenames]
    identifiers=re.findall(r'(?<![A-Za-z0-9])[A-Za-z]{1,16}[-－–—]\d[A-Za-z0-9-]*(?![A-Za-z0-9])',query)
    patterns=[re.compile(r'(?<![A-Za-z0-9])'+re.escape(code).replace(r'\-',r'[-－–—]')+r'(?![A-Za-z0-9])',re.I) for code in identifiers]
    anchored=[c for c in pool if all(pattern.search(c.get('text','')) for pattern in patterns)] if patterns else []
    ranks={item['id']:i for i,item in enumerate(results)}
    if patterns:results=anchored
    elif filenames:results=[c for c in results if c in pool]
    for item in results:ranks.setdefault(item['id'],len(ranks))
    candidates={item['id']:item for item in results}
    for rank,item in enumerate(results):
        number=body(item)
        if number is None or not title(item):continue
        for other in chunks:
            n=body(other)
            if n is not None and number<n<=number+3 and other.get('source')==item.get('source') and other.get('sha256')==item.get('sha256') and not title(other):
                candidates[other['id']]=other;ranks.setdefault(other['id'],rank)
    query_tokens=tokens(query)
    field_aliases={'成立日期':('成立日期','成立于','注册时间','成立时间'),'经营范围':('经营范围',),'名称':('企业名称','公司名称','有限公司'),'地址':('注册地址','建设地址','地址'),'生产规模':('生产规模','年产','产能'),'产品名称':('产品名称',),'通用名称':('通用名称',),'危险性分类':('危险性概述','GHS危险性类别','危险性分类')}
    aspects=[aliases for field,aliases in field_aliases.items() if field in query]
    def score(item):
        text=item.get('text','');overlap=len(tokens(text)&query_tokens)
        # Concrete body evidence outranks headings that merely repeat the question.
        substantive=not title(item)
        return (substantive,sum(any(term in text for term in aliases) for aliases in aspects),overlap,-ranks[item['id']])
    ranked=sorted(candidates.values(),key=score,reverse=True)
    relation=bool(patterns and re.search(r'实际使用|是否.{0,12}(?:对应|关联|匹配)|建立.{0,8}(?:对应|关联)',query))
    if relation and anchored:
        # Identity evidence and project-use evidence are separate retrieval branches.
        # A generic material list need not repeat the supplier's product identifier.
        primary=ranked[:max(1,limit//2)]
        primary_sources={c.get('source') for c in anchored}
        context_pool=[c for c in chunks if c.get('source') not in primary_sources]
        context=EvidenceIndex(context_pool).search(query,limit-len(primary)) if context_pool else []
        return primary+context
    return ranked[:limit]


def retrieval_metrics(results, relevant_ids, limit):
    if not isinstance(relevant_ids, list) or not relevant_ids or not all(isinstance(x, str) and x for x in relevant_ids):
        raise ValueError('请至少提供一个人工标注的相关证据 ID')
    gold = set(relevant_ids)
    found = [item['id'] for item in results[:limit]]
    hits = len(set(found) & gold)
    return {'relevant_count': len(gold), 'returned_count': len(found), 'hit_count': hits,
            'precision_at_k': hits / limit, 'precision_returned': hits / len(found) if found else 0.0,
            'recall_at_k': hits / len(gold), 'hit_rate': int(hits > 0),
            'unretrieved_relevant_ids': sorted(gold - set(found))}
