"""Feature generation — counts and lookups only.

Strictly non-ranking, non-semantic: simple cardinalities, sums and registry
lookups written under the ``features`` namespace, kept separate from
``redrob_signals``. No scores, weights, embeddings or ranking — those belong to
Pipeline 3.

Pass 1 features: ``skill_count``, ``certification_count``, ``language_count``,
``career_history_count``, ``total_endorsements``, ``average_skill_duration``.
Pass 2 additions (all counts/lookups): ``total_career_months``,
``product_company_count``, ``consulting_company_count``, ``ai_skill_count``,
``expert_skill_count``, ``highest_education_tier``.
"""

from __future__ import annotations

from typing import Any

from src.pipeline1.config import Registries
from src.pipeline1.ports import Step

# Education tier ranking, best first. Anything unknown/missing → "unknown".
_TIER_ORDER = ["tier_1", "tier_2", "tier_3", "tier_4", "unknown"]
_TIER_RANK = {tier: rank for rank, tier in enumerate(_TIER_ORDER)}


def _avg(values: list[float]) -> float:
    """Deterministic mean rounded to 4 dp; 0.0 for an empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _highest_tier(education: list[dict[str, Any]]) -> str:
    """Return the best (lowest-rank) education tier, or 'unknown' if none."""
    best = "unknown"
    best_rank = _TIER_RANK["unknown"]
    for entry in education:
        if not isinstance(entry, dict):
            continue
        tier = entry.get("tier")
        rank = _TIER_RANK.get(tier if isinstance(tier, str) else "", None)
        if rank is not None and rank < best_rank:
            best_rank, best = rank, tier
    return best


class FeatureGenerationStep(Step):
    """Attach count-based features to a transformed record."""

    name = "feature_generation"

    def __init__(self, registries: Registries) -> None:
        self._registries = registries
        self._records = 0

    def process(self, record: dict[str, Any]) -> dict[str, Any]:
        """Populate ``record['features']`` with deterministic counts in place."""
        skills = record.get("skills") or []
        certs = record.get("certifications") or []
        langs = record.get("languages") or []
        career = record.get("career_history") or []

        endorsements = [
            int(s.get("endorsements", 0))
            for s in skills
            if isinstance(s, dict) and isinstance(s.get("endorsements"), (int, float))
        ]
        durations = [
            float(s.get("duration_months", 0))
            for s in skills
            if isinstance(s, dict) and isinstance(s.get("duration_months"), (int, float))
        ]

        # Pass 2: career months, company-type counts, AI/expert skill counts.
        reg = self._registries
        total_career_months = sum(
            int(c.get("duration_months", 0))
            for c in career
            if isinstance(c, dict) and isinstance(c.get("duration_months"), (int, float))
        )
        product_count = 0
        consulting_count = 0
        for c in career:
            if not isinstance(c, dict):
                continue
            company = c.get("company")
            key = company.strip().casefold() if isinstance(company, str) else ""
            if key in reg.product:
                product_count += 1
            if key in reg.consulting:
                consulting_count += 1
        ai_skill_count = sum(
            1
            for s in skills
            if isinstance(s, dict) and s.get("normalized_name") in reg.ai_skills
        )
        expert_skill_count = sum(
            1
            for s in skills
            if isinstance(s, dict) and s.get("proficiency") == "expert"
        )

        features = record.setdefault("features", {})
        features.update(
            {
                "skill_count": len(skills),
                "certification_count": len(certs),
                "language_count": len(langs),
                "career_history_count": len(career),
                "total_endorsements": sum(endorsements),
                "average_skill_duration": _avg(durations),
                "total_career_months": total_career_months,
                "product_company_count": product_count,
                "consulting_company_count": consulting_count,
                "ai_skill_count": ai_skill_count,
                "expert_skill_count": expert_skill_count,
                "highest_education_tier": _highest_tier(record.get("education") or []),
            }
        )

        meta = record.get("_pipeline_metadata")
        if isinstance(meta, dict):
            meta["feature_generated"] = True

        self._records += 1
        return record

    def report(self) -> dict[str, Any]:
        return {"records_featurized": self._records}
