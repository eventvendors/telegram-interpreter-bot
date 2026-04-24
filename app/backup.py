from __future__ import annotations

import csv
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import BASE_DIR, Settings
from app.submissions import SubmissionRepository


logger = logging.getLogger(__name__)

DUBAI_TZ = ZoneInfo("Asia/Dubai")
SUBMISSIONS_EXPORT_PATH = BASE_DIR / "data" / "registration_submissions.csv"


@dataclass(frozen=True)
class NextBackupRun:
    scheduled_at: datetime
    sleep_seconds: float


def run_backup_scheduler(settings: Settings) -> None:
    if not settings.github_backup_token:
        logger.info("GitHub backup scheduler disabled because GITHUB_BACKUP_TOKEN is missing")
        return

    repository = SubmissionRepository(settings.submissions_db)
    logger.info(
        "GitHub backup scheduler enabled for %s at %02d:%02d Dubai time",
        settings.github_repo,
        settings.backup_hour_dubai,
        settings.backup_minute_dubai,
    )

    while True:
        next_run = _next_backup_run(
            now=datetime.now(DUBAI_TZ),
            hour=settings.backup_hour_dubai,
            minute=settings.backup_minute_dubai,
        )
        time.sleep(next_run.sleep_seconds)
        try:
            export_submissions_csv(repository, SUBMISSIONS_EXPORT_PATH)
            commit_and_push_backup(settings, SUBMISSIONS_EXPORT_PATH)
        except Exception:
            logger.exception("Daily GitHub backup failed")


def _next_backup_run(now: datetime, hour: int, minute: int) -> NextBackupRun:
    scheduled_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled_at <= now:
        scheduled_at = scheduled_at + timedelta(days=1)
    return NextBackupRun(
        scheduled_at=scheduled_at,
        sleep_seconds=max(1.0, (scheduled_at - now).total_seconds()),
    )


def export_submissions_csv(repository: SubmissionRepository, output_path: Path) -> None:
    submissions = repository.list_submissions()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "full_name",
                "working_languages",
                "phone_number",
                "email_address",
                "short_bio",
                "status",
                "submitted_at",
            ],
        )
        writer.writeheader()
        for submission in submissions:
            writer.writerow(
                {
                    "id": submission.id,
                    "full_name": submission.full_name,
                    "working_languages": submission.working_languages,
                    "phone_number": submission.phone_number,
                    "email_address": submission.email_address,
                    "short_bio": submission.short_bio,
                    "status": submission.status,
                    "submitted_at": submission.submitted_at,
                }
            )


def commit_and_push_backup(settings: Settings, export_path: Path) -> None:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    _run_git(["config", "user.name", settings.backup_git_name], env)
    _run_git(["config", "user.email", settings.backup_git_email], env)
    _run_git(["add", str(export_path.relative_to(BASE_DIR))], env)

    status = _run_git(
        ["status", "--short", "--", str(export_path.relative_to(BASE_DIR))],
        env,
        capture_output=True,
    ).stdout.strip()
    if not status:
        logger.info("No backup changes detected for %s", export_path.name)
        return

    timestamp = datetime.now(DUBAI_TZ).strftime("%Y-%m-%d %H:%M")
    _run_git(
        ["commit", "-m", f"Daily submissions backup {timestamp} Dubai"],
        env,
    )
    push_url = (
        f"https://x-access-token:{settings.github_backup_token}"
        f"@github.com/{settings.github_repo}.git"
    )
    _run_git(["push", push_url, f"HEAD:{settings.github_backup_branch}"], env)
    logger.info("Daily GitHub backup pushed successfully")


def _run_git(args: list[str], env: dict[str, str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=BASE_DIR,
        env=env,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return result
