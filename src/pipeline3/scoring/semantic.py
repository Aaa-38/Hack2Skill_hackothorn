"""Semantic career relevance scoring."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from src.pipeline3.config import Pipeline3Settings


def _tokenize(text: str) -> list[str]:
    """Basic word tokenization."""
    if not text:
        return []
    return re.findall(r"\w+", text.casefold())


class SemanticScorer:
    """
    Computes semantic similarity using TF-IDF and cosine similarity.
    This implementation is CPU-only, deterministic, and requires no network.
    It builds a local vocabulary from the job description and candidate documents.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.jd_text = settings.job_description
        self.jd_tokens = _tokenize(self.jd_text)
        self.jd_tf = Counter(self.jd_tokens)
        
        # In a real batch pipeline we would compute IDF over the whole corpus.
        # For streaming without O(N^2) memory, we will just use normalized TF overlap,
        # or we could approximate IDF if we passed over the corpus once.
        # Since we must stream, we'll use a Jaccard + TF overlap approach which acts 
        # as a proxy for cosine similarity without needing global IDF counts.

    def score(self, record: dict[str, Any]) -> float:
        """
        Compute semantic similarity against the job description.
        Score ∈ [0, 1].
        """
        if not self.jd_tokens:
            return 0.5  # Neutral if no JD
            
        doc = record.get("candidate_document", "")
        if not doc:
            return 0.0
            
        doc_tokens = _tokenize(doc)
        if not doc_tokens:
            return 0.0
            
        doc_tf = Counter(doc_tokens)
        
        # Compute dot product of term frequencies
        dot_product = 0.0
        for token, count in doc_tf.items():
            if token in self.jd_tf:
                dot_product += count * self.jd_tf[token]
                
        # Compute magnitudes
        jd_mag = math.sqrt(sum(count ** 2 for count in self.jd_tf.values()))
        doc_mag = math.sqrt(sum(count ** 2 for count in doc_tf.values()))
        
        if jd_mag == 0 or doc_mag == 0:
            return 0.0
            
        cosine_sim = dot_product / (jd_mag * doc_mag)
        
        # Cosine similarity is typically small for long documents due to many unique words.
        # We'll normalize it to a reasonable [0,1] range using a simple curve.
        # A cosine similarity > 0.3 is generally very strong for plain TF matching.
        normalized = min(1.0, cosine_sim * 2.5)
        
        return normalized
