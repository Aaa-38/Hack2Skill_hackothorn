"""Experience score component."""

from __future__ import annotations

from typing import Any

from src.pipeline3.config import Pipeline3Settings


class ExperienceScorer:
    """
    Scores candidates based on tenure, stability, and growth.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.cfg = settings.p3.experience

    def score(self, record: dict[str, Any]) -> float:
        """
        Compute experience score ∈ [0, 1].
        """
        features = record.get("features", {})
        total_months = features.get("total_career_months", 0)
        roles_count = features.get("career_history_count", 0)
        yoe = record.get("profile_years_of_experience", 0.0)
        
        if roles_count == 0 or total_months == 0:
            return 0.5
            
        avg_months = total_months / roles_count
        
        score = 0.5
        
        # 1. Job Hopping Penalty
        if avg_months < self.cfg.job_hopping_months_threshold:
            score -= 0.3
            
        # 2. Stability Reward (Ideal Tenure)
        if self.cfg.ideal_tenure_months_min <= avg_months <= self.cfg.ideal_tenure_months_max:
            score += 0.3
        elif avg_months > self.cfg.ideal_tenure_months_max:
            # Too long in same roles might indicate stagnation, but still better than hopping
            score += 0.1
            
        # 3. YOE Alignment
        if yoe >= 5.0 and yoe <= 9.0:
            score += 0.2
        elif yoe > 9.0:
            score += 0.1
            
        return max(0.0, min(1.0, score))
