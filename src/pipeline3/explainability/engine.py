"""Explainability engine."""

from __future__ import annotations

from typing import Any

from src.pipeline3.config import Pipeline3Settings


class ExplainabilityEngine:
    """
    Builds the explainability record for a ranked candidate.
    Must only use actual candidate information. Never hallucinate.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.settings = settings

    def build(
        self,
        record: dict[str, Any],
        scores: dict[str, float],
        final_score: float,
        penalties: list[dict[str, str]],
        candidate_domain: str
    ) -> dict[str, Any]:
        """
        Build the full explainability payload.
        """
        # Determine strengths and weaknesses from component scores
        score_items = list(scores.items())
        score_items.sort(key=lambda x: x[1], reverse=True)
        
        strengths = [k for k, v in score_items if v > 0.6]
        weaknesses = [k for k, v in score_items if v < 0.4]
        
        # Build natural language reasoning
        reasoning_parts = []
        
        # Domain context
        if candidate_domain != "unknown":
            reasoning_parts.append(f"Candidate has an inferred domain of '{candidate_domain}'.")
        else:
            reasoning_parts.append("Could not infer a clear primary domain from skills.")
            
        # Top strength reasoning
        if strengths:
            top_strength = strengths[0]
            if top_strength == "title":
                reasoning_parts.append("Strong title relevance to target roles.")
            elif top_strength == "semantic":
                reasoning_parts.append("High semantic alignment between career history and job description.")
            elif top_strength == "experience":
                reasoning_parts.append("Demonstrates solid experience duration and stability.")
            elif top_strength == "skill":
                reasoning_parts.append("Strong skill profile based on proficiency and assessments.")
            elif top_strength == "company":
                reasoning_parts.append("Valuable company background (e.g., product or AI-native experience).")
            elif top_strength == "behavioral":
                reasoning_parts.append("Highly engaged candidate with strong behavioral signals.")
                
        # Top weakness reasoning
        if weaknesses:
            top_weakness = weaknesses[0]
            if top_weakness == "title":
                reasoning_parts.append("Current and past titles lack direct relevance to the target role.")
            elif top_weakness == "experience":
                reasoning_parts.append("Experience duration or job stability is a potential concern.")
            elif top_weakness == "skill":
                reasoning_parts.append("Lacks deep proficiency or validation in core domain skills.")
            elif top_weakness == "company":
                reasoning_parts.append("Company background relies heavily on consulting without product exposure.")
            elif top_weakness == "behavioral":
                reasoning_parts.append("Low engagement or responsiveness signals detected.")
                
        # Penalty reasoning
        if penalties:
            hard_count = sum(1 for p in penalties if p["level"] == "hard")
            susp_count = sum(1 for p in penalties if p["level"] == "suspicious")
            warn_count = sum(1 for p in penalties if p["level"] == "warning")
            reasoning_parts.append(
                f"Confidence reduced due to detected flags: {hard_count} hard, {susp_count} suspicious, {warn_count} warnings."
            )
        else:
            reasoning_parts.append("No suspicious indicators or honeypot flags detected.")

        return {
            "score_breakdown": scores,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "penalties": penalties,
            "triggered_warnings": [p["type"] for p in penalties if p["level"] == "warning"],
            "confidence_score": final_score,
            "candidate_domain": candidate_domain,
            "reasoning": " ".join(reasoning_parts)
        }
