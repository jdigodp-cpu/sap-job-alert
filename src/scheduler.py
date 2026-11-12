"""Install the job alert as a daily scheduled task.

Windows: registers a Task Scheduler task via schtasks.
Linux/macOS: prints the crontab line to add manually.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAIN_SCRIPT = Path(__file__).resolve().parent.parent / "main.py"


def windows_install() -> str:
    main = str(MAIN_SCRIPT)
    command = (
        f'schtasks /create /tn "SAP Daily Job Alert" /sc daily /st 09:00 '
        f'/ru "%USERNAME%" /rl HIGHEST /f '
        f'/tr "\"python\" \"{main}\" --run-once"'
    )
    return command


def cron_line() -> str:
    python = sys.executable or "python3"
    return f"0 9 * * * {python} {MAIN_SCRIPT} --run-once >> {MAIN_SCRIPT.parent}/data/job-alert.log 2>&1"


def install() -> None:
    if sys.platform.startswith("win"):
        cmd = windows_install()
        print("Registering daily Task Scheduler task 'SAP Daily Job Alert' (09:00 daily)...")
        print(f"   {cmd}")
        try:
            subprocess.run(cmd, shell=True, check=True)
            print("Installed. The task will run main.py --run-once every day at 09:00.")
        except subprocess.CalledProcessError as exc:
            print(f"Failed to install scheduled task: {exc}")
            print("Run the command above as Administrator, or use Task Scheduler manually.")
    else:
        print("Add this line to your crontab (crontab -e):")
        print(f"   {cron_line()}")
        print("This runs main.py --run-once every day at 09:00.")
