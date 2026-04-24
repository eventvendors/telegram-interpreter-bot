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


if __name__ == "__main__":
    unittest.main()
