"""Generic RSS job-feed source (optional).

Some niche job boards still offer RSS feeds. Add feed URLs under
sources.rss_feeds.urls in config.yaml. Uses only the standard library.
"""
from __future__ import annotations

import email.utils
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable

from models import Job
from sources.base import Source


class RssSource(Source):
    name = "rss"

    def __init__(self, urls: list[str]):
        self.urls = urls

    def fetch(self, queries: Iterable[str]) -> list[Job]:
        jobs: list[Job] = []
        query_terms = [q.lower() for q in queries]
        for url in self.urls:
            try:
                jobs.extend(self._fetch_feed(url, query_terms))
            except Exception as exc:  # keep one bad feed from killing the run
                print(f"[rss] feed failed '{url}': {exc}")
        return jobs

    def _fetch_feed(self, url: str, query_terms: list[str]) -> list[Job]:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sap-job-alert/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
        jobs: list[Job] = []
        for item in root.findall(".//item"):
            title = self._text(item, "title")
            link = self._text(item, "link")
            desc = self._text(item, "description")
            pub_date = self._text(item, "pubDate")
            job_id = f"rss:{link or title}"
            # Only keep items that look related to our search terms.
            haystack = f"{title} {desc}".lower()
            if query_terms and not any(t in haystack for t in query_terms):
                continue
            jobs.append(
                Job(
                    id=job_id,
                    title=title,
                    company=self._guess_company(title, desc),
                    location="",
                    url=link,
                    description=desc,
                    posted_at=self._parse_date(pub_date),
                    source="rss",
                    raw={},
                )
            )
        return jobs

    @staticmethod
    def _text(item, tag: str) -> str:
        el = item.find(tag)
        return (el.text or "").strip() if el is not None else ""

    @staticmethod
    def _guess_company(title: str, desc: str) -> str:
        # RSS feeds rarely carry a company field; leave blank unless obvious.
        return ""

    @staticmethod
    def _parse_date(date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            return date_str
