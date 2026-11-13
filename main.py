"""Daily SAP job alert — single entry point.

Usage:
    python main.py --run-once        # scan sources once, alert on new matches
    python main.py --demo            # same, using the built-in demo source
    python main.py --install-scheduler  # set up a daily scheduled task
    python main.py --self-test       # run matcher self-test on sample jobs
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR / "src"
for p in (SRC_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import APP_DIR, RESUME_PATH, STATE_PATH, load_config
from matcher import filter_jobs
from config import AppConfig
from notify import alert
from resume_parser import parse_resume
from scheduler import install
from state import State

# Source priority: when the same job appears on multiple portals,
# keep the one from the highest-priority source.
SOURCE_PRIORITY = {
    "linkedin.com": 0,
    "indeed.com": 1,
    "naukri.com": 2,
    "shine.com": 3,
    "foundit.in": 4,
    "monster.com": 5,
    "dice.com": 6,
    "ziprecruiter.com": 7,
    "glassdoor.com": 8,
}


def build_sources(config: dict):
    sources = []
    source_cfg = config.get("sources", {})

    demo_cfg = source_cfg.get("demo", {})
    if demo_cfg.get("enabled", True):
        from sources.demo import DemoSource

        sources.append(DemoSource())

    rapid_cfg = source_cfg.get("rapidapi", {})
    if rapid_cfg.get("enabled", False):
        from sources.rapidapi import RapidApiSource

        sources.append(
            RapidApiSource(
                api_key=rapid_cfg.get("api_key", ""),
                engine=rapid_cfg.get("engine", "jsearch"),
                country=rapid_cfg.get("country", ""),
            )
        )

    rss_cfg = source_cfg.get("rss_feeds", {})
    if rss_cfg.get("enabled", False):
        from sources.rss import RssSource

        sources.append(RssSource(rss_cfg.get("urls", [])))

    return sources


def _source_priority(job) -> int:
    """Return priority rank for a job's source (lower = better)."""
    url = (job.url or "").lower()
    netloc = urlparse(job.url or "").netloc.lower()
    for domain, rank in SOURCE_PRIORITY.items():
        if domain in netloc:
            return rank
    return 99  # unknown sources go last


def _normalize(text: str) -> str:
    """Normalize text for fingerprint comparison."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _job_fingerprint(job) -> str:
    """Create a fingerprint to detect the same job posted on multiple portals."""
    title = _normalize(job.title)
    company = _normalize(job.company)
    location = _normalize(job.location)
    return f"{title}||{company}||{location}"


def _is_paywalled(job, blocked_domains):
    """Return True if the job's URL or company matches a blocked domain."""
    url = (job.url or "").lower()
    netloc = urlparse(job.url or "").netloc.lower()
    company = (job.company or "").lower()
    for domain in blocked_domains:
        d = domain.lower()
        if d in netloc or d in url or d in company:
            return True
    return False


def _dedup_by_fingerprint(jobs):
    """When the same job appears on multiple portals, keep the best source.

    Returns (kept_jobs, dropped_count).
    """
    groups: dict[str, list] = {}
    for job in jobs:
        fp = _job_fingerprint(job)
        groups.setdefault(fp, []).append(job)

    kept = []
    dropped = 0
    for fp, group in groups.items():
        # Sort by source priority (lower rank = better source)
        group.sort(key=_source_priority)
        kept.append(group[0])
        dropped += len(group) - 1
    return kept, dropped


def run_once(demo_only: bool = False) -> dict:
    config = load_config()
    app_config = config  # plain dict is enough

    profile = parse_resume(RESUME_PATH)
    profile.preferred_locations = app_config.get("preferred_locations", [])
    profile.experience_years = app_config.get("experience_years", profile.experience_years)

    # Blocked / paywalled domains — configurable via config.yaml sources.blocked_domains
    blocked_domains = tuple(
        app_config.get("sources", {}).get("blocked_domains", ["bebee.com", "bebee"])
    )

    sources = build_sources(app_config)
    if demo_only:
        sources = [s for s in sources if s.name == "demo"] or [
            __import__("sources.demo", fromlist=["DemoSource"]).DemoSource()
        ]

    print(f"Profile: {profile.experience_years} experience, skills: {sorted(profile.skills)}")
    print(f"Sources: {[s.name for s in sources]} | queries: {len(app_config.get('search_queries', []))}")

    state = State(STATE_PATH)
    all_jobs = []
    for source in sources:
        jobs = source.fetch(app_config.get("search_queries", []))
        print(f"  [{source.name}] {len(jobs)} job(s) fetched")
        all_jobs.extend(jobs)

    # 1) De-duplicate across sources by exact job id, keep first occurrence.
    seen_ids: set[str] = set()
    exact_unique = []
    for job in all_jobs:
        if job.id not in seen_ids:
            seen_ids.add(job.id)
            exact_unique.append(job)

    # 2) Cross-portal dedup: same job posted on LinkedIn + Indeed + etc.
    #    Keep the one from the highest-priority source (LinkedIn > Indeed > Naukri > ...).
    cross_deduped, cross_dedup_dropped = _dedup_by_fingerprint(exact_unique)

    # 3) Filter out paywalled / low-quality job boards BEFORE scoring.
    before_paywall = len(cross_deduped)
    cross_deduped = [j for j in cross_deduped if not _is_paywalled(j, blocked_domains)]
    skipped_paywall = before_paywall - len(cross_deduped)

    # 4) De-duplicate against seen_jobs.json (jobs already notified in prior runs).
    true_duplicates = [j for j in cross_deduped if not state.is_new(j)]
    new_jobs = [j for j in cross_deduped if state.is_new(j)]
    duplicates_removed = len(true_duplicates)

    print(
        f"  {len(all_jobs)} fetched, "
        f"{len(exact_unique)} exact-unique, "
        f"{cross_dedup_dropped} cross-portal deduped, "
        f"{skipped_paywall} paywalled, "
        f"{duplicates_removed} duplicates, "
        f"{len(new_jobs)} new to score"
    )

    # 5) Score only the new, non-paywalled jobs.
    relevant, maybe = filter_jobs(
        new_jobs, profile, AppConfig.from_dict(app_config)
    )

    alert(relevant, maybe, app_config, duplicates_removed=duplicates_removed)

    # 6) Persist state for everything we processed this run (avoid re-notifying).
    buckets = {
        job.id: ("relevant" if job in relevant else "maybe")
        for job in relevant + maybe
    }
    for job in cross_deduped:
        state.mark(
            job,
            job.score,
            buckets.get(job.id, "not_relevant"),
        )
    state.save()

    return {
        "fetched": len(all_jobs),
        "exact_unique": len(exact_unique),
        "cross_dedup_dropped": cross_dedup_dropped,
        "paywalled": skipped_paywall,
        "duplicates": duplicates_removed,
        "new": len(new_jobs),
        "relevant": len(relevant),
        "maybe": len(maybe),
    }


def self_test() -> None:
    """Run the matcher on the built-in demo jobs to verify scoring."""
    from sources.demo import SAMPLE_JOBS

    config = load_config()
    profile = parse_resume(RESUME_PATH)
    profile.preferred_locations = config.get("preferred_locations", [])
    profile.experience_years = config.get("experience_years", profile.experience_years)

    relevant, maybe = filter_jobs(
        SAMPLE_JOBS, profile, AppConfig.from_dict(config)
    )
    print("=== Matcher self-test (demo jobs) ===")
    print("Relevant:")
    for job in relevant:
        print(f"  [{job.score:.2f}] {job.title} — {job.company}")
    print("Maybe:")
    for job in maybe:
        print(f"  [{job.score:.2f}] {job.title} — {job.company}")
    print("Not relevant:", len(SAMPLE_JOBS) - len(relevant) - len(maybe))


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily SAP job alert system")
    parser.add_argument(
        "--run-once", action="store_true", help="run one scan and alert"
    )
    parser.add_argument(
        "--demo", action="store_true", help="run one scan with the demo source only"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="test the matcher on demo jobs"
    )
    parser.add_argument(
        "--install-scheduler",
        action="store_true",
        help="install a daily scheduled task (Windows Task Scheduler / cron)",
    )
    args = parser.parse_args()

    if args.install_scheduler:
        install()
        return
    if args.self_test:
        self_test()
        return
    if args.demo or args.run_once:
        result = run_once(demo_only=args.demo)
        print(
            f"\nDone: {result['fetched']} fetched, "
            f"{result['relevant']} relevant, {result['maybe']} maybe."
        )
        return
    parser.print_help()


if __name__ == "__main__":
    main()
