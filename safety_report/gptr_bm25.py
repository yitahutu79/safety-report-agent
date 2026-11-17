"""BM25 adapted from GPT Researcher 0.17.0 context/lexical.py.

Upstream license and complete Python wheel sources are under
third_party/gpt_researcher/upstream-0.17.0. Tokenization is adapted for Chinese
and accepts pre-tokenized evidence, avoiding upstream network-capable imports.
"""
import math
from collections import Counter


def bm25_scores(query_terms, passages, k1=1.5, b=0.75):
    """Score pre-tokenized passages locally; no overlap produces zero."""
    docs = [Counter(passage) for passage in passages]
    if not docs:
        return []
    avg_len = sum(sum(d.values()) for d in docs) / len(docs) or 1.0
    query_terms = set(query_terms)
    df = {t: sum(1 for d in docs if t in d) for t in query_terms}
    idf = {t: math.log((len(docs) - n + 0.5) / (n + 0.5) + 1) for t, n in df.items()}
    scores = []
    for d in docs:
        length = sum(d.values())
        score = 0.0
        for t in query_terms:
            tf = d.get(t, 0)
            if tf:
                score += idf[t] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg_len))
        scores.append(score)
    return scores
