"""Abstract base class for job sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from models import Job


class Source(ABC):
    """A source of job postings.

    fetch(queries) returns Job objects. Every Job must carry a stable,
    unique `id` so the state store can de-duplicate across runs.
    """

    name: str = "base"

    @abstractmethod
    def fetch(self, queries: Iterable[str]) -> list[Job]:
        """Return jobs matching any of the given search queries."""
        raise NotImplementedError
