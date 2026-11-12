"""Persistent store of jobs we have already notified about.

kept in data/seen_jobs.json so re-runs only surface *new* postings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from models import Job


class State:
    def __init__(self, path: Path):
        self.path = path
        self._entries: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def known_ids(self) -> set[str]:
        return set(self._entries.keys())

    def is_new(self, job: Job) -> bool:
        return job.id not in self._entries

    def mark(
        self,
        job: Job,
        score: float,
        bucket: str,
    ) -> None:
        self._entries[job.id] = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "source": job.source,
            "score": score,
            "bucket": bucket,
            "notified_at": _now_iso(),
        }

    def summary(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
