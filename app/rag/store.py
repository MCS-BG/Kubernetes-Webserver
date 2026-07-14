"""Minimal per-entity retrieval over reference documents (chart of
accounts notes, accounting policy text, prior close notes).

Deliberately not embeddings-based: no external API calls, no vector DB,
no network dependency, so it runs and is testable with zero configuration.
Scoring is TF-IDF over the entity's own document set with cosine-style
normalization -- good enough to ground the chat agent's answers in a
specific client's documents rather than generic knowledge. Swap this for
a real vector store when corpus size or relevance needs outgrow it; the
`search()` signature is the only thing a caller depends on.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from app.models import new_id

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Document:
    id: str = field(default_factory=new_id)
    entity_id: str = ""
    title: str = ""
    text: str = ""


class RAGStore:
    def __init__(self):
        self._docs: dict[str, list[Document]] = {}

    def add_document(self, entity_id: str, title: str, text: str) -> Document:
        doc = Document(entity_id=entity_id, title=title, text=text)
        self._docs.setdefault(entity_id, []).append(doc)
        return doc

    def documents_for(self, entity_id: str) -> list[Document]:
        return self._docs.get(entity_id, [])

    def search(self, entity_id: str, query: str, top_k: int = 3) -> list[tuple[Document, float]]:
        docs = self.documents_for(entity_id)
        if not docs:
            return []

        doc_tokens = [_tokenize(d.text) for d in docs]
        doc_freq: Counter[str] = Counter()
        for tokens in doc_tokens:
            for term in set(tokens):
                doc_freq[term] += 1

        n_docs = len(docs)
        query_terms = set(_tokenize(query))
        if not query_terms:
            return []

        scored: list[tuple[Document, float]] = []
        for doc, tokens in zip(docs, doc_tokens):
            if not tokens:
                continue
            term_counts = Counter(tokens)
            score = 0.0
            for term in query_terms:
                if term not in term_counts:
                    continue
                tf = term_counts[term] / len(tokens)
                idf = math.log((n_docs + 1) / (doc_freq[term] + 1)) + 1.0
                score += tf * idf
            if score > 0:
                scored.append((doc, score))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


rag_store = RAGStore()
