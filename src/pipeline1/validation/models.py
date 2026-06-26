"""Pydantic v2 domain models mirroring the real Redrob candidate schema.

These models are used purely as a *gatekeeper*: they decide whether a raw record
is structurally valid (required fields present, types coercible). The raw dict —
not the model dump — is what flows downstream, so unknown fields and verbatim
text are preserved exactly. ``extra="allow"`` lets us detect pass-through fields
for ``schema_warning`` without rejecting them.

Field set validated against ``data/candidate_schema.json``; no fields invented.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Extra fields are detected manually at the top level (see ValidationStep); the
# models themselves ignore extras so pydantic does not pay to capture them. This
# is a measured hot path at 100k records.
_ALLOW = ConfigDict(extra="ignore")


class Profile(BaseModel):
    model_config = _ALLOW
    anonymized_name: str
    headline: str
    summary: str
    location: str
    country: str
    years_of_experience: float
    current_title: str
    current_company: str
    current_company_size: str
    current_industry: str


class CareerEntry(BaseModel):
    model_config = _ALLOW
    company: str
    title: str
    start_date: str
    end_date: Optional[str] = None
    duration_months: int
    is_current: bool
    industry: str
    company_size: str
    description: str


class EducationEntry(BaseModel):
    model_config = _ALLOW
    institution: str
    degree: str
    field_of_study: str
    start_year: int
    end_year: int
    grade: Optional[str] = None
    tier: Optional[str] = None


class Skill(BaseModel):
    model_config = _ALLOW
    name: str
    proficiency: str
    endorsements: int
    duration_months: Optional[int] = None


class RedrobSignals(BaseModel):
    model_config = _ALLOW
    profile_completeness_score: float
    last_active_date: str
    open_to_work_flag: bool
    recruiter_response_rate: float
    notice_period_days: int
    willing_to_relocate: bool
    github_activity_score: float
    saved_by_recruiters_30d: int
    interview_completion_rate: float
    offer_acceptance_rate: float
    verified_email: bool
    verified_phone: bool


class Candidate(BaseModel):
    """Top-level candidate. Only required fields are constrained for quarantine."""

    model_config = _ALLOW
    candidate_id: str = Field(pattern=r"^CAND_[0-9]{7}$")
    profile: Profile
    career_history: list[CareerEntry] = Field(min_length=1, max_length=10)
    education: list[EducationEntry] = Field(default_factory=list, max_length=5)
    skills: list[Skill]
    redrob_signals: RedrobSignals
