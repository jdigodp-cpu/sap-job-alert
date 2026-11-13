"""Notifications: console, email (SMTP), Windows toast, Telegram."""
from __future__ import annotations

import json
import smtplib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from typing import Iterable

from models import Job


def _safe(text: str) -> str:
    """Make text safe to print on the current console encoding (e.g. cp1252)."""
    enc = sys.stdout.encoding or "utf-8"
    return text.encode(enc, errors="replace").decode(enc)


def _job_line(job: Job) -> str:
    return (
        f"  [{job.score:.2f}] {job.title} — {job.company} ({job.location})\n"
        f"        {job.url}\n"
    )


def console(jobs: Iterable[Job], label: str) -> None:
    jobs = list(jobs)
    if not jobs:
        print(f"[{label}] No new jobs.")
        return
    print(f"[{label}] {len(jobs)} new job(s):")
    for job in jobs:
        reasons = job.reasons or {}
        skills = ", ".join(reasons.get("matched_skills", []))
        print(_safe(_job_line(job)))
        if skills:
            print(_safe(f"        matched skills: {skills}"))


def _send_email(subject: str, body: str, config: dict) -> None:
    if not config.get("enabled"):
        return
    host = config.get("smtp_host", "")
    port = int(config.get("smtp_port", 587))
    user = config.get("smtp_user", "")
    pwd = config.get("smtp_pass", "")
    to = config.get("to", "")
    if not all([host, user, pwd, to]):
        print("[email] SMTP not fully configured; skipping email.")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, pwd)
            smtp.send_message(msg)
        print("[email] alert sent.")
    except Exception as exc:  # noqa: BLE001
        print(f"[email] failed to send: {exc}")


def windows_toast(title: str, body: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        from win10toast import ToastNotifier  # type: ignore

        ToastNotifier().show_toast(title, body, duration=10, threaded=True)
    except ImportError:
        print(f"[toast] {title}: {body}  (install win10toast for pop-ups)")


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

TELEGRAM_MAX_LEN = 4000  # Telegram limit is 4096; stay safely under

IST = timezone(timedelta(hours=5, minutes=30))


def _send_telegram(token: str, chat_id: str, text: str, max_retries: int = 3) -> bool:
    """Send a single message via the Telegram Bot API sendMessage endpoint.

    Handles HTTP 429 (rate limit) by respecting the `retry_after` value
    and retrying automatically.
    Returns True if sent successfully, False otherwise.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            print("[telegram] message sent.")
            return True
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 429:
                # Parse retry_after from the response body.
                import json as _json

                try:
                    data = _json.loads(body)
                    retry_after = data.get("parameters", {}).get("retry_after", 5)
                except Exception:
                    retry_after = 5
                print(
                    f"[telegram] rate limited (429), retrying after {retry_after}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_after)
                continue
            print(f"[telegram] failed (HTTP {exc.code}): {body[:200]}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"[telegram] failed: {exc}")
            return False
    print(f"[telegram] failed after {max_retries} retries.")
    return False


def _send_telegram_messages(token: str, chat_id: str, texts: list[str]) -> None:
    """Send multiple Telegram messages, one after another, with safe delays.

    Uses a 3-second base delay between messages and handles 429 rate limits
    by respecting Telegram's `retry_after` value.
    """
    for i, text in enumerate(texts):
        if len(text) > TELEGRAM_MAX_LEN:
            text = text[:TELEGRAM_MAX_LEN] + "\n…(truncated)"
        _send_telegram(token, chat_id, text)
        # Base delay between messages to avoid hitting Telegram rate limits.
        if i < len(texts) - 1:
            time.sleep(3)


def _ist_now() -> datetime:
    return datetime.now(IST)


def _format_header(total_relevant: int, total_maybe: int, duplicates_removed: int) -> str:
    """Header message with date, time, and counts."""
    now = _ist_now()
    date_str = now.strftime("%d %b %Y")
    time_str = now.strftime("%I:%M %p IST")
    lines = [
        "🔔 <b>SAP Job Alert — Daily Digest</b>",
        f"📅 <b>Date:</b> {date_str}",
        f"🕐 <b>Time:</b> {time_str}",
        f"✅ <b>Relevant jobs found:</b> {total_relevant}",
        f"📎 <b>Maybe / lower confidence:</b> {total_maybe}",
        f"🔄 <b>Duplicates removed:</b> {duplicates_removed}",
    ]
    return "\n".join(lines)


# Skill keywords to extract from job descriptions for summarization.
_SUMMARY_SKILLS = [
    "SAP CDS Views", "CDS Views", "AMDP", "ABAP", "ABAP on HANA", "ABAP Cloud",
    "HANA", "HANA Calculation View", "SAP Datasphere", "SAP Analytics Cloud",
    "SAP Fiori", "Fiori", "RAP", "ABAP RAP", "RESTful Application Programming",
    "SAP S/4HANA", "S/4HANA", "SAP BW", "SAP BTP", "SAP SCM", "SAP SD",
    "SAP MM", "SAP FICO", "SAP HCM", "SAP BASIS", "SQL", "Python", "Git",
    "Web Dynpro", "Embedded Analytics", "Table Functions",
]

_EXPERIENCE_HINTS = [
    "years of experience", "year experience", "yrs exp", "yr exp",
    "senior", "junior", "lead", "manager", "associate", "consultant",
    "fresher", "entry level",
]


def _extract_experience(text: str) -> str:
    """Try to extract an experience requirement from the job text."""
    import re

    lower = text.lower()
    # Look for patterns like "5+ years", "3-5 years", "5 years"
    m = re.search(r"(\d+\s*(?:\+\s*)?\s*-\s*\d+\s*|\d+\s*\+\s*)\s*years?", lower)
    if m:
        return m.group(0).strip()
    # Look for seniority keywords
    for hint in ("senior", "lead", "manager", "consultant", "associate", "junior", "fresher"):
        if hint in lower:
            return hint.title()
    return "Not specified"


def _summarize_job(job: Job) -> str:
    """Build a short skills/requirements summary from the job description.

    Rule-based extraction — no extra API needed.
    """
    text = job.description or ""
    title = job.title or ""
    combined = f"{title} {text}"
    lower = combined.lower()

    # Skills found in the description/title.
    found_skills: list[str] = []
    for skill in _SUMMARY_SKILLS:
        sl = skill.lower()
        # Whole-ish word match.
        if sl in lower and skill not in found_skills:
            found_skills.append(skill)

    experience = _extract_experience(combined)

    parts: list[str] = []
    if found_skills:
        parts.append(f"<b>Key skills:</b> {', '.join(found_skills[:8])}")
    if experience != "Not specified":
        parts.append(f"<b>Experience:</b> {experience}")
    if not parts:
        parts.append("<b>Notes:</b> See application link for full details.")

    return " | ".join(parts)


def _format_job_message(job: Job, label: str, index: int, total: int) -> str:
    """Format a single job as its own Telegram message."""
    summary = _summarize_job(job)
    return (
        f"{label} <b>Job {index}/{total}</b>\n"
        f"💼 <b>Role:</b> {job.title}\n"
        f"🏢 <b>Company:</b> {job.company}\n"
        f"📍 <b>Location:</b> {job.location or 'Not specified'}\n"
        f"{summary}\n"
        f"⭐ <b>Match score:</b> {job.score:.2f}\n"
        f"🔗 <b>Apply:</b> <a href=\"{job.url}\">{job.url}</a>"
    )


def alert(
    relevant: list[Job],
    maybe: list[Job],
    config: dict,
    duplicates_removed: int = 0,
) -> None:
    notif = config.get("notifications", {})

    # Console / email / toast (unchanged behavior).
    if relevant:
        body = "New relevant SAP job(s) found:\n\n"
        for job in relevant:
            body += _job_line(job)
        subject = f"SAP Job Alert: {len(relevant)} new relevant job(s)"
    else:
        body = "No new relevant SAP jobs this run.\n"
        subject = "SAP Job Alert: no new relevant jobs"

    if maybe:
        body += "\n--- Maybe (lower confidence) ---\n"
        for job in maybe:
            body += _job_line(job)

    if notif.get("console", True):
        console(relevant, "RELEVANT")
        console(maybe, "MAYBE")

    windows_toast(subject, body[:300], bool(notif.get("windows_toast", True)))

    if notif.get("email", {}).get("enabled"):
        _send_email(subject, body, notif["email"])

    # Telegram — header message first, then one message per job.
    tg = notif.get("telegram", {})
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        token = tg["bot_token"]
        chat_id = tg["chat_id"]

        messages: list[str] = []

        # Header message.
        messages.append(
            _format_header(len(relevant), len(maybe), duplicates_removed)
        )

        if not relevant and not maybe:
            messages.append("No new relevant SAP jobs today.")
        else:
            if relevant:
                messages.append(
                    f"\n<b>✅ Relevant jobs ({len(relevant)}):</b>"
                )
                for i, job in enumerate(relevant, 1):
                    messages.append(
                        _format_job_message(job, "💼", i, len(relevant))
                    )

            if maybe:
                messages.append(
                    f"\n<b>📎 Maybe / lower confidence ({len(maybe)}):</b>"
                )
                for i, job in enumerate(maybe, 1):
                    messages.append(
                        _format_job_message(job, "💡", i, len(maybe))
                    )

        _send_telegram_messages(token, chat_id, messages)
