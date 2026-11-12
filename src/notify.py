"""Notifications: console, email (SMTP), Windows toast, Telegram."""
from __future__ import annotations

import json
import smtplib
import sys
import urllib.error
import urllib.request
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


TELEGRAM_MAX_LEN = 4000  # Telegram limit is 4096; stay safely under

def _send_telegram(token: str, chat_id: str, text: str) -> None:
    """Send a message via the Telegram Bot API sendMessage endpoint.

    Splits into multiple messages if text exceeds Telegram's length limit.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _send_chunk(chunk: str) -> None:
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()

    try:
        if len(text) <= TELEGRAM_MAX_LEN:
            _send_chunk(text)
            print("[telegram] message sent.")
        else:
            # Split on blank-line boundaries (between jobs) where possible.
            parts = text.split("\n\n")
            current = ""
            for part in parts:
                candidate = (current + "\n\n" + part) if current else part
                if len(candidate) <= TELEGRAM_MAX_LEN:
                    current = candidate
                else:
                    if current:
                        _send_chunk(current)
                    current = part
            if current:
                _send_chunk(current)
            print(f"[telegram] {len(text)} char(s) sent across message(s).")
    except urllib.error.HTTPError as exc:
        print(f"[telegram] failed (HTTP {exc.code}): {exc.read().decode(errors='replace')[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[telegram] failed: {exc}")


def _format_telegram_message(
    relevant: list[Job], maybe: list[Job]
) -> str:
    """Format message per user's structure:
    Role: XYZ
    Company: XYZ
    Experience:
    Notes: Summarized job description
    Application Link: XYZ.com
    """
    lines: list[str] = []

    if not relevant and not maybe:
        lines.append("🔔 SAP Job Alert — No new relevant jobs today.")
        return "\n".join(lines)

    if relevant:
        lines.append(
            f"🔔 SAP Job Alert — {len(relevant)} new relevant job(s) found:\n"
        )
        for job in relevant:
            # Notes = truncated description, cleaned of extra whitespace.
            desc = " ".join((job.description or "").split())
            notes = desc[:300] + ("…" if len(desc) > 300 else "")
            lines.append(
                f"<b>Role:</b> {job.title}\n"
                f"<b>Company:</b> {job.company}\n"
                f"<b>Experience:</b> 3+ years\n"
                f"<b>Location:</b> {job.location or 'Not specified'}\n"
                f"<b>Notes:</b> {notes}\n"
                f"<b>Application Link:</b> <a href=\"{job.url}\">{job.url}</a>\n"
                f"Score: {job.score:.2f}"
            )
            lines.append("")  # blank line between jobs

    if maybe:
        lines.append(
            f"📎 Also {len(maybe)} lower-confidence match(es):\n"
        )
        for job in maybe:
            desc = " ".join((job.description or "").split())
            notes = desc[:300] + ("…" if len(desc) > 300 else "")
            lines.append(
                f"<b>Role:</b> {job.title}\n"
                f"<b>Company:</b> {job.company}\n"
                f"<b>Experience:</b> 3+ years\n"
                f"<b>Location:</b> {job.location or 'Not specified'}\n"
                f"<b>Notes:</b> {notes}\n"
                f"<b>Application Link:</b> <a href=\"{job.url}\">{job.url}</a>\n"
                f"Score: {job.score:.2f}"
            )
            lines.append("")

    return "\n".join(lines)


def alert(
    relevant: list[Job],
    maybe: list[Job],
    config: dict,
) -> None:
    notif = config.get("notifications", {})

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

    # Telegram — builds a clean HTML message per the requested structure.
    tg = notif.get("telegram", {})
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        text = _format_telegram_message(relevant, maybe)
        _send_telegram(tg["bot_token"], tg["chat_id"], text)
