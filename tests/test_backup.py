from __future__ import annotations

import csv
import uuid
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.backup import _next_backup_run, export_submissions_csv
from app.submissions import RegistrationSubmission, SubmissionRepository


class BackupTests(unittest.TestCase):
    def test_next_backup_run_moves_to_next_day_after_cutoff(self) -> None:
        now = datetime(2026, 4, 24, 3, 15, tzinfo=ZoneInfo("Asia/Dubai"))
        next_run = _next_backup_run(now=now, hour=3, minute=0)
        self.assertEqual(next_run.scheduled_at.day, 25)
        self.assertEqual(next_run.scheduled_at.hour, 3)
        self.assertEqual(next_run.scheduled_at.minute, 0)

    def test_export_submissions_csv_writes_statuses(self) -> None:
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        db_path = storage_dir / f"test-{uuid.uuid4().hex}.db"
        export_path = storage_dir / f"export-{uuid.uuid4().hex}.csv"
        repository = SubmissionRepository(db_path)

        submission_id = repository.create_submission(
            RegistrationSubmission(
                full_name="Backup Test",
                working_languages="Arabic, English",
                phone_number="+971500000001",
                email_address="backup@example.com",
                short_bio="Interpreter for testing.",
            )
        )
        repository.update_status(submission_id, "approved")

        export_submissions_csv(repository, export_path)

        with export_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "Backup Test")
        self.assertEqual(rows[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
