"""Skill score and domain inference."""

from __future__ import annotations

import json
from pathlib import Path
from collections import Counter
from typing import Any

from src.pipeline3.config import Pipeline3Settings


class SkillScorer:
    """
    Scores candidates based on skills and infers their primary domain.
    Tracks unknown skills to a report.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.taxonomy = settings.taxonomy
        self.unknown_skills: set[str] = set()
        
    def _infer_domain(self, skills: list[dict[str, Any]]) -> str:
        domain_counts = Counter()
        for s in skills:
            if not isinstance(s, dict):
                continue
            norm_name = s.get("normalized_name", "")
            if not norm_name:
                continue
                
            found = False
            for domain, domain_skills in self.taxonomy.items():
                if norm_name in domain_skills:
                    domain_counts[domain] += 1
                    found = True
                    
            if not found:
                self.unknown_skills.add(norm_name)
                
        if not domain_counts:
            return "unknown"
            
        # Return domain with highest count
        return domain_counts.most_common(1)[0][0]

    def score(self, record: dict[str, Any]) -> tuple[float, str]:
        """
        Compute skill score ∈ [0, 1] and return (score, candidate_domain).
        """
        skills = record.get("skills") or []
        domain = self._infer_domain(skills)
        
        if not skills:
            return 0.2, domain
            
        score = 0.5
        
        # Reward proficiency
        prof_weights = {"expert": 1.0, "advanced": 0.7, "intermediate": 0.4, "beginner": 0.1}
        prof_score = sum(prof_weights.get(s.get("proficiency", "beginner"), 0.1) for s in skills if isinstance(s, dict))
        # Normalize by skill count, but expect ~5-10 good skills
        score += min(0.2, (prof_score / max(1, len(skills))) * 0.2)
        
        # Reward assessment scores
        signals = record.get("redrob_signals", {})
        assessments = signals.get("skill_assessment_scores", {})
        if assessments:
            avg_assessment = sum(assessments.values()) / len(assessments)
            # assessments are 0-100
            if avg_assessment > 80:
                score += 0.2
            elif avg_assessment > 60:
                score += 0.1
                
        # Reward endorsements 
        features = record.get("features", {})
        total_end = features.get("total_endorsements", 0)
        if total_end > 50:
            score += 0.1
            
        return max(0.0, min(1.0, score)), domain

    def write_unknown_skills_report(self, path: str | Path) -> None:
        """Write the unknown skills set to a JSON file."""
        Path(path).write_text(json.dumps(sorted(list(self.unknown_skills)), indent=2), encoding="utf-8")
