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


def rank_written_sections(query, sections, max_results=3, relative_threshold=0.5):
    """Adapted from GPT Researcher context.lexical.rank_written_sections.

    Uses the project's Chinese tokenization and returns untrusted text snippets;
    they are for continuity only and must not be treated as evidence.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from .documents import tokens
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = [(section.get('section_title', ''), chunk)
              for section in sections
              for chunk in splitter.split_text(section.get('written_content') or '')
              if chunk.strip()]
    scores = bm25_scores(tokens(query), [tokens(title + '\n' + text) for title, text in chunks])
    best = max(scores, default=0.0)
    if best <= 0:
        return []
    ranked = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    return [f'标题：{chunks[i][0]}\n内容：{chunks[i][1][:240]}'
            for i in ranked if scores[i] >= relative_threshold * best][:max_results]
