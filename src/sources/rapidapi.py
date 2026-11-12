"""RapidAPI job-aggregation source (optional, requires an API key).

Supported engines:
* jsearch (rapidapi.com/letscrape-6bba543e-jsearch/api) - aggregates LinkedIn,
  Indeed, Glassdoor and other boards. Needs X-RapidAPI-Key.
* techmap / jobdatafeeds - portal-filtered job feed.

This source is disabled by default. Enable it in config.yaml only after you
have obtained your own key. Direct scraping of LinkedIn/Indeed/Naukri is not
used here, since those portals prohibit scraping and offer no public
job-search API (see README.md).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

from models import Job
from sources.base import Source

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"
TECHMAP_URL = "https://jobdatafeeds.p.rapidapi.com/jobs"  # illustrative


class RapidApiSource(Source):
    name = "rapidapi"

    def __init__(self, api_key: str = "", engine: str = "jsearch", country: str = ""):
        self.api_key = api_key
        self.engine = engine
        self.country = country

    def fetch(self, queries: Iterable[str]) -> list[Job]:
        if not self.api_key:
            return []
        jobs: list[Job] = []
        for query in queries:
            try:
                if self.engine == "jsearch":
                    jobs.extend(self._jsearch(query))
                else:
                    jobs.extend(self._techmap(query))
            except Exception as exc:  # keep one bad query from killing the run
                print(f"[rapidapi:{self.engine}] query failed '{query}': {exc}")
        return jobs

    def _get(self, url: str, params: dict[str, str]) -> dict:
        qs = "&".join(
            f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}"
            for k, v in params.items()
        )
        req = urllib.request.Request(
            f"{url}?{qs}",
            headers={
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": urllib.request.urlparse(url).netloc,
                "User-Agent": "sap-job-alert/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _jsearch(self, query: str) -> list[Job]:
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "date_posted": "3days",
        }
        if self.country:
            params["country"] = self.country
        data = self._get(JSEARCH_URL, params)
        jobs_data = data.get("data", {}) if isinstance(data, dict) else {}
        jobs: list[Job] = []
        for item in jobs_data.get("jobs", []):
            job_id = item.get("job_id") or item.get("job_apply_link") or ""
            location = ", ".join(
                str(item.get(k) or "")
                for k in ("job_city", "job_state", "job_country")
                if item.get(k)
            )
            jobs.append(
                Job(
                    id=f"rapidapi:jsearch:{job_id}",
                    title=item.get("job_title", ""),
                    company=item.get("employer_name", ""),
                    location=location,
                    url=item.get("job_apply_link", ""),
                    description=item.get("job_description", "") or "",
                    posted_at=item.get("job_posted_at_datetime_utc", ""),
                    source="rapidapi",
                    raw=item,
                )
            )
        return jobs

    def _techmap(self, query: str) -> list[Job]:
        # Placeholder for the Techmap/jobdatafeeds endpoint; shape varies by plan.
        data = self._get(TECHMAP_URL, {"query": query, "portal": "naukri,linkedin,indeed"})
        jobs: list[Job] = []
        for item in data.get("jobs", []):
            jobs.append(
                Job(
                    id=f"rapidapi:techmap:{item.get('id','')}",
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    url=item.get("url", ""),
                    description=item.get("description", "") or "",
                    posted_at=item.get("posted_at", ""),
                    source="rapidapi",
                    raw=item,
                )
            )
        return jobs


