"""Daily SAP job alert — single entry point.

Usage:
    python main.py --run-once        # scan sources once, alert on new matches
    python main.py --demo            # same, using the built-in demo source
    python main.py --install-scheduler  # set up a daily scheduled task
    python main.py --self-test       # run matcher self-test on sample jobs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def run_once(demo_only: bool = False) -> dict:
    config = load_config()
    app_config = config  # plain dict is enough

    profile = parse_resume(RESUME_PATH)
    profile.preferred_locations = app_config.get("preferred_locations", [])
    profile.experience_years = app_config.get("experience_years", profile.experience_years)

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

    # De-duplicate across sources by job id, keep first occurrence.
    seen_ids: set[str] = set()
    unique_jobs = []
    for job in all_jobs:
        if job.id not in seen_ids:
            seen_ids.add(job.id)
            unique_jobs.append(job)

    new_jobs = [j for j in unique_jobs if state.is_new(j)]
    print(f"  {len(unique_jobs)} unique, {len(new_jobs)} new since last run")

    duplicates_removed = len(unique_jobs) - len(new_jobs)

    relevant, maybe = filter_jobs(
        new_jobs, profile, AppConfig.from_dict(app_config)
    )

    alert(relevant, maybe, app_config, duplicates_removed=duplicates_removed)

    # Persist state for everything we looked at this run (avoid re-scoring
    # and re-notifying jobs we have already seen).
    buckets = {job.id: ("relevant" if job in relevant else "maybe") for job in relevant + maybe}
    for job in unique_jobs:
        state.mark(
            job,
            job.score,
            buckets.get(job.id, "not_relevant"),
        )
    state.save()

    return {
        "fetched": len(unique_jobs),
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
            f"\nDone: {result['fetched']} unique, {result['new']} new, "
            f"{result['relevant']} relevant, {result['maybe']} maybe."
        )
        return
    parser.print_help()


if __name__ == "__main__":
    main()
