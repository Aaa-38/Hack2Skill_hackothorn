"""Company score component."""

from __future__ import annotations

from typing import Any

from src.pipeline3.config import Pipeline3Settings


class CompanyScorer:
    """
    Scores candidates based on their company history.
    Rewards product and AI-native companies.
    Penalizes consulting-heavy careers.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.registries = settings.p1.registries

    def score(self, record: dict[str, Any]) -> float:
        """
        Compute company score ∈ [0, 1].
        """
        features = record.get("features", {})
        career_count = features.get("career_history_count", 0)
        
        if career_count == 0:
            return 0.5  # Neutral if no history
            
        product_count = features.get("product_company_count", 0)
        consulting_count = features.get("consulting_company_count", 0)
        
        # Compute AI native count from career history
        career = record.get("career_history") or []
        ai_native_count = 0
        for c in career:
            if isinstance(c, dict):
                comp = c.get("company", "")
                if comp and comp.casefold() in self.registries.ai_native:
                    ai_native_count += 1
                    
        # Base score starts at 0.5
        base = 0.5
        
        # Reward AI native heavily
        if ai_native_count > 0:
            base += 0.3 * min(1.0, ai_native_count / 2)
            
        # Reward product companies
        if product_count > 0:
            base += 0.2 * min(1.0, product_count / max(1, career_count))
            
        # Penalize consulting heavily (if it's the majority)
        if consulting_count > 0:
            ratio = consulting_count / max(1, career_count)
            # Only penalize if ratio is high
            if ratio > 0.5:
                base -= 0.3 * ratio
                
        return max(0.0, min(1.0, base))
