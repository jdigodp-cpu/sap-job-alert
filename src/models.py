"""Core data models: Job posting and candidate Profile."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    """A single job posting fetched from a source."""

    id: str
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    posted_at: Optional[str] = None  # ISO 8601 string when known
    source: str = ""
    raw: dict = field(default_factory=dict)
    score: float = 0.0
    reasons: dict = field(default_factory=dict)

    def text(self) -> str:
        """All searchable text of the job, lowercased by the matcher."""
        return " ".join(
            [self.title, self.company, self.location, self.description]
        )


@dataclass
class Profile:
    """Candidate profile derived from the resume."""

    skills: set[str]
    title_keywords: set[str]
    preferred_locations: list[str]
    experience_years: str
    raw_text: str = ""
