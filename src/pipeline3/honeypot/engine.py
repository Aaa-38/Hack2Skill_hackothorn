"""Honeypot penalty engine."""

from __future__ import annotations

from typing import Any

from src.pipeline3.config import Pipeline3Settings


class HoneypotEngine:
    """
    Applies penalties to candidate confidence based on quality flags and heuristics.
    Never removes candidates.
    Outputs a multiplier and a list of triggered penalties.
    """

    def __init__(self, settings: Pipeline3Settings):
        self.cfg = settings.p3.honeypot
        self.exp_cfg = settings.p3.experience

    def process(self, record: dict[str, Any], candidate_domain: str) -> tuple[float, list[dict[str, str]]]:
        """
        Compute honeypot multiplier and penalties.
        Returns:
            multiplier (float ∈ [0, 1])
            penalties (list of dict with 'level', 'reason', 'type')
        """
        penalties = []
        
        # 1. Map existing quality flags from Pipeline 1/2
        quality_flags = record.get("quality_flags", [])
        for flag in quality_flags:
            severity = self.cfg.flag_severity.get(flag)
            if severity:
                penalties.append({
                    "level": severity,
                    "type": flag,
                    "reason": f"Triggered quality flag: {flag}"
                })
                
        # 2. Additional Pipeline 3 heuristics
        
        # a) Assessment score mismatch (High proficiency but very low assessment)
        skills = record.get("skills") or []
        signals = record.get("redrob_signals", {})
        assessments = signals.get("skill_assessment_scores", {})
        for s in skills:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "")
            prof = s.get("proficiency", "")
            if prof in ("expert", "advanced") and name in assessments:
                score = assessments[name]
                if score < 30:  # Suspicious mismatch
                    penalties.append({
                        "level": "warning",
                        "type": "assessment_mismatch",
                        "reason": f"Claimed {prof} in {name} but scored {score} in assessment"
                    })
                    
        # b) Domain inconsistency
        # If inferred domain is 'unknown' but they claim many tech skills
        if candidate_domain == "unknown" and len(skills) > 10:
            penalties.append({
                "level": "warning",
                "type": "domain_inconsistency",
                "reason": "Large number of skills but no clear domain inferred"
            })
            
        # Determine worst severity to apply correct multiplier
        levels_triggered = {p["level"] for p in penalties}
        
        # Multiple severe flags heuristic -> hard
        suspicious_count = sum(1 for p in penalties if p["level"] == "suspicious")
        if suspicious_count >= 2:
            levels_triggered.add("hard")
            penalties.append({
                "level": "hard",
                "type": "multiple_severe_flags",
                "reason": "Multiple suspicious indicators found"
            })

        multiplier = 1.0
        if "hard" in levels_triggered:
            multiplier = self.cfg.multipliers.hard
        elif "suspicious" in levels_triggered:
            multiplier = self.cfg.multipliers.suspicious
        elif "warning" in levels_triggered:
            multiplier = self.cfg.multipliers.warning
            
        return multiplier, penalties
