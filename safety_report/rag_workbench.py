"""Separate project/public retrieval and human-labelled retrieval evaluation."""
from .documents import HybridEvidenceIndex


def search_project(chunks, index_path, query, limit):
    index = HybridEvidenceIndex(chunks, index_path)
    try:
        results = index.search(query, limit)
        mode = 'hybrid_qdrant_rrf' if index.client and not index.semantic_error else 'keyword_fallback'
        return results, mode, index.semantic_error
    finally:
        index.close()


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
