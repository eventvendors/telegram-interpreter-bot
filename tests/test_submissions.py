from __future__ import annotations

import uuid
import unittest
from pathlib import Path

from app.submissions import RegistrationSubmission, SubmissionRepository


class SubmissionRepositoryTests(unittest.TestCase):
    def test_create_submission_writes_pending_record(self) -> None:
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        db_path = storage_dir / f"test-{uuid.uuid4().hex}.db"
        repository = SubmissionRepository(db_path)

        submission_id = repository.create_submission(
            RegistrationSubmission(
                full_name="Jane Doe",
                working_languages="Arabic, English",
                phone_number="+971500000000",
                email_address="jane@example.com",
                short_bio="Conference interpreter in Dubai.",
            )
        )

        self.assertEqual(submission_id, 1)
        self.assertTrue(db_path.exists())
        pending = repository.list_submissions(status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].full_name, "Jane Doe")

    def test_update_status_removes_submission_from_pending_list(self) -> None:
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        db_path = storage_dir / f"test-{uuid.uuid4().hex}.db"
        repository = SubmissionRepository(db_path)

        submission_id = repository.create_submission(
            RegistrationSubmission(
                full_name="John Doe",
                working_languages="Russian, English",
                phone_number="+971511111111",
                email_address="john@example.com",
                short_bio="Interpreter in Abu Dhabi.",
            )
        )

        repository.update_status(submission_id, "approved")

        self.assertEqual(repository.list_submissions(status="pending"), [])
        approved = repository.list_submissions(status="approved")
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0].id, submission_id)


if __name__ == "__main__":
    unittest.main()
