# Daily SAP Job Alert System

A self-contained Python system that scans job sources every day, matches postings
against your resume (SAP CDS Views, AMDP, HANA, Datasphere, SAP Analytics Cloud,
ABAP, Fiori, RAP, SQL, Python), and alerts you about **new** relevant jobs — never
duplicates.

## ⚠️ LinkedIn / Indeed / Naukri — no public API, no scraping

None of these portals offers a public job-search API, and all three prohibit
automated scraping in their Terms of Service:

* **LinkedIn** — Jobs infrastructure is posting-only, restricted to approved
  partners (LinkedIn is not accepting new ones). Public "guest" endpoints are
  undocumented, rate-limited (~10 pages/IP), and scraping violates the
  [LinkedIn User Agreement](https://www.linkedin.com/legal/user-agreement).
* **Indeed** — the public Publisher API is discontinued; access is partner-only
  now, and scraping/crawling is prohibited by [Indeed's Terms of
  Service](https://www.indeed.com/legal).
* **Naukri** — no public API or RSS feed exists; integrations are recruiter-side
  only.

**This system does not scrape those portals.** It uses a RapidAPI job
aggregator (JSearch covers LinkedIn/Indeed/Glassdoor postings via a third party)
plus optional RSS feeds. You can also set up saved-search email alerts directly
in LinkedIn/Indeed/Naukri as a complementary free channel.

## Files

```
job-alert/                              ← separate repo from telegram-xp-claimer
├── resume.txt                          # your resume (export as .txt)
├── config.yaml                         # your real config (created from config.yaml.example)
├── config.yaml.example
├── .env                                # your secrets (JOBALERT_* env vars)
├── .env.example
├── main.py                             # entry point
├── requirements.txt
├── README.md
├── src/
│   ├── config.py                       # config loading (config.yaml + JOBALERT_* env vars)
│   ├── models.py                       # Job, Profile data models
│   ├── resume_parser.py                # extracts skills/experience from resume.txt
│   ├── matcher.py                      # scores jobs (skills, title, location, recency)
│   ├── state.py                        # data/seen_jobs.json — remembers notified jobs
│   ├── notify.py                       # console + email + Windows toast + Telegram
│   ├── sources/
│   │   ├── base.py                     # Source ABC
│   │   ├── demo.py                     # sample jobs for testing
│   │   ├── rapidapi.py                 # RapidAPI JSearch adapter
│   │   └── rss.py                      # generic RSS feed adapter
│   └── scheduler.py                    # local Task Scheduler / cron helper
├── data/                               # created at runtime (seen_jobs.json)
└── .github/workflows/daily-job-alert.yml   # GitHub Actions: daily at 9 AM IST
```

## Quick start (local test)

```powershell
cd "c:\Users\raaaaaaj\VSCode\job-alert"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install requests pyyaml

# config.yaml and .env are already created with your RapidAPI key
python main.py --run-once          # real scan — fetches SAP jobs from India
python main.py --self-test         # verify matcher scoring on demo jobs
python main.py --demo              # test with built-in sample jobs
```

## Run daily on a server (GitHub Actions) — recommended

The system includes `.github/workflows/daily-job-alert.yml` which runs every
day at **9:00 AM IST** (03:30 UTC) on GitHub Actions, free.

### One-time setup

1. **Push this repo to GitHub** (separate repo from `telegram-xp-claimer` — keep
   them independent so you can run either one alone).

2. **Create a Telegram bot** — message [@BotFather](https://t.me/botfather) on
   Telegram, run `/newbot`, and note the bot token.

3. **Get your chat ID** — send a message to your bot, then visit:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   Find `"chat":{"id":...}` — that's the chat ID to ping job messages to.

4. **Add GitHub repo secrets** — Settings → Secrets and variables → Actions →
   New repository secret:
   | Secret | Value |
   |--------|-------|
   | `RAPIDAPI_KEY` | `de719d5b3bmsh781f7ff459dd0f1p193b57jsnae85af53dde7` |
   | `TELEGRAM_BOT_TOKEN` | from @BotFather |
   | `TELEGRAM_CHAT_ID` | the chat ID from step 3 |

5. The workflow commits `data/seen_jobs.json` back after each run, so
   de-duplication persists across days — you only see *new* jobs.

### Telegram message format

Each relevant job is sent as:

```
🔔 SAP Job Alert — 3 new relevant job(s) found:

Role: SAP FIORI Lead Consultant
Company: Birlasoft Limited
Experience: 3+ years
Location: Pune, Maharashtra, IN
Notes: <summarized description>
Application Link: https://jobs.birlasoft.com/...
Score: 0.95

Role: SAP Analytics Cloud & Datasphere Consultant
Company: Virtusa
Experience: 3+ years
...
```

## Scoring

| Component | Weight | What it checks |
|-----------|--------|----------------|
| Skills | 50% | Resume skills found in job title+description |
| Title | 30% | SAP / CDS / AMDP / ABAP / HANA / Datasphere / Analytics Cloud / Fiori / RAP in title |
| Location | 15% | Preferred locations (Pune, India, Remote, WFH) |
| Recency | 5% | Posted within 3 days (full), 14 days (half) |

* **Relevant** (≥ 0.60): immediate alert
* **Maybe** (≥ 0.40): daily digest
* Below 0.40: skipped

Jobs explicitly saying "no SAP experience required" are penalized 60%.

## Keeping your resume current

Edit `resume.txt` whenever your skills change. The matcher reads skills
directly from it — no code changes needed.

## Disclaimer

This tool is for personal job-search assistance. Respect each job board's
Terms of Service; do not add scrapers that bypass login walls or rate limits.
Third-party API keys (RapidAPI, etc.) are your responsibility — check their
pricing before enabling.
