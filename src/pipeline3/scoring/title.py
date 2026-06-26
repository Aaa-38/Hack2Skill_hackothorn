"""Title relevance scoring."""

from __future__ import annotations

import re
from typing import Any

from src.pipeline3.config import Pipeline3Settings


class TitleScorer:
    """Scores candidate titles against target role keywords."""

    def __init__(self, settings: Pipeline3Settings):
        # Casefolded and tokenized target roles
        self.target_keywords = set()
        for role in settings.p3.keywords.target_roles:
            tokens = set(re.findall(r"\w+", role.casefold()))
            self.target_keywords.update(tokens)

    def score(self, record: dict[str, Any]) -> float:
        """
        Compute title relevance score ∈ [0, 1].
        Headline has highest weight, current title medium, past titles lowest.
        """
        if not self.target_keywords:
            return 0.5  # Neutral if no targets configured
            
        headline = record.get("profile_headline", "")
        current_title = record.get("profile_current_title", "")
        
        career = record.get("career_history") or []
        past_titles = []
        for c in career:
            if isinstance(c, dict) and not c.get("is_current", False):
                past_titles.append(c.get("title", ""))
                
        def match_ratio(text: str) -> float:
            if not text:
                return 0.0
            tokens = set(re.findall(r"\w+", text.casefold()))
            if not tokens:
                return 0.0
            # Intersection of keywords
            overlap = tokens.intersection(self.target_keywords)
            # Cap at 1.0, give credit for partial overlap
            return min(1.0, len(overlap) / max(1, len(self.target_keywords) * 0.5))

        h_score = match_ratio(headline)
        c_score = match_ratio(current_title)
        
        # Max over past titles
        p_scores = [match_ratio(pt) for pt in past_titles]
        p_score = max(p_scores) if p_scores else 0.0
        
        # Weighted combination: headline 50%, current 30%, past 20%
        final = (h_score * 0.5) + (c_score * 0.3) + (p_score * 0.2)
        return min(1.0, final)
