"""Parse the resume into a searchable Profile.

The resume is plain text (resume.txt). We extract:

* skills      - known SAP/data keywords that appear in the resume
* title_keywords - role keywords that make a job title relevant
* experience_years - rough total experience from date ranges
* raw_text    - full resume text

No external PDF libraries are required: point the system at a .txt export
of your resume, or paste your LinkedIn profile text into resume.txt.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from models import Job, Profile

# Canonical skills we care about (from your resume + SAP ecosystem).
KNOWN_SKILLS = [
    "SAP CDS Views",
    "CDS Views",
    "CDS",
    "AMDP",
    "ABAP Managed Database Procedures",
    "ABAP",
    "SAP Embedded Analytics",
    "SAP Native HANA Calculation Views",
    "HANA Calculation View",
    "Calculation View",
    "SAP Datasphere",
    "SAP Analytics Cloud",
    "SAP Fiori",
    "Fiori",
    "RAP",
    "Web Dynpro",
    "SQL",
    "Python",
    "Git",
    "GitHub",
]

# Title keywords that strongly signal a relevant SAP analytics role.
TITLE_KEYWORDS = [
    "SAP",
    "CDS",
    "AMDP",
    "ABAP",
    "HANA",
    "Datasphere",
    "Analytics Cloud",
    "Fiori",
    "RAP",
    "Embedded Analytics",
]


def _year_range_matches(text: str) -> list[tuple[int, int | None]]:
    """Find MM/YYYY - MM/YYYY style date ranges in the resume."""
    pattern = re.compile(
        r"(\d{1,2})/(\d{4})\s*[-–]\s*(\d{1,2})/(\d{4}|Present)"
    )
    ranges: list[tuple[int, int | None]] = []
    for m in pattern.finditer(text):
        start_year = int(m.group(2))
        end_year: int | None = None if m.group(4) == "Present" else int(m.group(4))
        ranges.append((start_year, end_year))
    return ranges


def estimate_experience_years(text: str) -> str:
    ranges = _year_range_matches(text)
    if not ranges:
        return "unknown"
    today = date.today()
    total = 0
    for start_year, end_year in ranges:
        end = end_year or today.year
        total += max(0, end - start_year)
    return f"{total}+"


def extract_skills(text: str) -> set[str]:
    found: set[str] = set()
    lower = text.lower()
    for skill in KNOWN_SKILLS:
        if skill.lower() in lower:
            found.add(skill)
    return found


def parse_resume(path: Path) -> Profile:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    skills = extract_skills(text)
    # Always keep the core SAP CDS/AMDP signals even if parsing misses them.
    for core in ("CDS Views", "AMDP", "ABAP", "SAP"):
        if core not in skills:
            skills.add(core)
    return Profile(
        skills=skills,
        title_keywords=set(TITLE_KEYWORDS),
        preferred_locations=[],  # filled from config later
        experience_years=estimate_experience_years(text),
        raw_text=text,
    )
