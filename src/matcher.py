"""Score a job posting against the candidate profile.

Scoring (all components 0-1, weighted per config):

* skill_score     - how many resume skills appear in the job text
                    (whole-word matching; negative phrases like
                     "no SAP experience required" are penalized)
* title_score     - strong title keywords (SAP, CDS, AMDP, ABAP, HANA, …)
* location_score  - remote/WFH (1.0), named city (0.85), country (0.5)
* recency_score   - posted within 3 days (1.0), 14 days (0.5), else 0.0

A job is "relevant" if total >= relevant_threshold (default 0.60)
and "maybe" if >= maybe_threshold (default 0.40).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from config import AppConfig
from models import Job, Profile

DEFAULT_THRESHOLDS = {"relevant": 0.60, "maybe": 0.40}

# Phrases that mean the role is explicitly *not* an SAP role.
NEGATIVE_SIGNALS = [
    "no sap experience", "no sap", "non-sap", "sap not required",
    "without sap", "not sap", "no cds", "no amdp", "non-amdp",
]

REMOTE_TERMS = ("remote", "work from home", "wfh", "work from anywhere")
COUNTRY_TERMS = ("india",)


def _contains(text: str, term: str) -> bool:
    """Whole-word, case-insensitive substring match."""
    return re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) is not None


def _parse_posted(posted_at: str | None) -> datetime | None:
    if not posted_at:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(posted_at, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _matched_skills(text: str, skills) -> list[str]:
    matched: list[str] = []
    # Longer skills first so "CDS Views" covers "CDS" instead of double counting.
    for skill in sorted(skills, key=len, reverse=True):
        if _contains(text, skill) and not any(
            skill in existing for existing in matched
        ):
            matched.append(skill)
    return matched


def _location_score(location: str, preferred_locations) -> float:
    loc = location.lower()
    if any(term in loc for term in REMOTE_TERMS):
        return 1.0
    best = 0.0
    for pref in preferred_locations or []:
        pl = pref.lower()
        if not pl or pl in REMOTE_TERMS:
            continue
        if _contains(loc, pl):
            if pl in COUNTRY_TERMS:
                best = max(best, 0.5)
            else:
                best = max(best, 0.85)
    return best


def score_job(
    job: Job,
    profile: Profile,
    weights: dict,
) -> tuple[float, dict]:
    text = job.text().lower()
    title_l = job.title.lower()

    # --- skills --------------------------------------------------------
    matched_skills = _matched_skills(text, profile.skills)
    skill_score = min(1.0, len(matched_skills) / 3.0)

    # --- title ---------------------------------------------------------
    title_hits = [k for k in profile.title_keywords if _contains(title_l, k)]
    desc_hits = [k for k in profile.title_keywords if _contains(text, k)]
    if title_hits:
        title_score = 1.0
    elif desc_hits:
        title_score = 0.5
    else:
        title_score = 0.0

    # --- location ------------------------------------------------------
    location_score = _location_score(job.location, profile.preferred_locations)

    # --- recency -------------------------------------------------------
    posted = _parse_posted(job.posted_at)
    now = datetime.now(timezone.utc)
    if posted is None:
        recency_score = 0.5  # unknown: neutral
    elif now - posted <= timedelta(days=3):
        recency_score = 1.0
    elif now - posted <= timedelta(days=14):
        recency_score = 0.5
    else:
        recency_score = 0.0

    total = (
        weights.get("skill_weight", 0.5) * skill_score
        + weights.get("title_weight", 0.3) * title_score
        + weights.get("location_weight", 0.15) * location_score
        + weights.get("recency_weight", 0.05) * recency_score
    )

    # Penalize jobs that explicitly say "no SAP experience required", etc.
    if any(sig in text for sig in NEGATIVE_SIGNALS):
        total *= 0.4

    reasons = {
        "matched_skills": matched_skills,
        "title_hits": title_hits,
        "skill_score": round(skill_score, 2),
        "title_score": title_score,
        "location_score": location_score,
        "recency_score": recency_score,
    }
    return round(total, 3), reasons


def classify(score: float, thresholds: dict) -> str:
    if score >= thresholds.get("relevant", 0.60):
        return "relevant"
    if score >= thresholds.get("maybe", 0.40):
        return "maybe"
    return "not_relevant"


def filter_jobs(
    jobs: list[Job],
    profile: Profile,
    config: AppConfig,
) -> tuple[list[Job], list[Job]]:
    """Split jobs into (relevant, maybe)."""
    thresholds = config.scoring
    relevant: list[Job] = []
    maybe: list[Job] = []
    for job in jobs:
        score, reasons = score_job(job, profile, thresholds)
        job.score = score
        job.reasons = reasons
        bucket = classify(score, thresholds)
        if bucket == "relevant":
            relevant.append(job)
        elif bucket == "maybe":
            maybe.append(job)
    relevant.sort(key=lambda j: j.score, reverse=True)
    maybe.sort(key=lambda j: j.score, reverse=True)
    return relevant, maybe
