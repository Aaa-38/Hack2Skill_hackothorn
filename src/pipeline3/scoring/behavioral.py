"""Behavioral intelligence score."""

from __future__ import annotations

from typing import Any

from src.pipeline3.config import Pipeline3Settings


class BehavioralScorer:
    """
    Scores candidates based on behavioral signals.
    Avoids popularity bias.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.weights = settings.p3.behavioral.weights

    def score(self, record: dict[str, Any]) -> float:
        """
        Compute behavioral score ∈ [0, 1].
        """
        # Base starts at 0, we accumulate based on configured weights
        score = 0.0
        max_possible = 0.0
        
        signals = record.get("redrob_signals", {})
        
        # Helper to safely get value and apply weight
        def add_signal(key: str, val_norm: float):
            nonlocal score, max_possible
            w = self.weights.get(key, 0.0)
            score += val_norm * w
            max_possible += w

        # Recruiter response rate (0 to 1)
        add_signal("recruiter_response_rate", signals.get("recruiter_response_rate", 0.0))
        
        # Interview completion rate (0 to 1)
        add_signal("interview_completion_rate", signals.get("interview_completion_rate", 0.0))
        
        # Offer acceptance rate (0 to 1, -1 means no data)
        oar = signals.get("offer_acceptance_rate", -1)
        add_signal("offer_acceptance_rate", oar if oar >= 0 else 0.5)  # neutral if -1
        
        # GitHub activity (0 to 100, -1 means no data)
        gh = signals.get("github_activity_score", -1)
        add_signal("github_activity_score", gh / 100.0 if gh >= 0 else 0.0)
        
        # Profile completeness (0 to 100)
        pc = signals.get("profile_completeness_score", 0.0)
        add_signal("profile_completeness_score", pc / 100.0)
        
        # Open to work flag (boolean)
        otw = signals.get("open_to_work_flag", False)
        add_signal("open_to_work_flag", 1.0 if otw else 0.0)
        
        if max_possible == 0.0:
            return 0.5
            
        return max(0.0, min(1.0, score / max_possible))
