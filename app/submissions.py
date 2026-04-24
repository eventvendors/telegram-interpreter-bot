from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RegistrationSubmission:
    full_name: str
    working_languages: str
    phone_number: str
    email_address: str
    short_bio: str


@dataclass(frozen=True)
class StoredSubmission:
    id: int
    full_name: str
    working_languages: str
    phone_number: str
    email_address: str
    short_bio: str
    status: str
    submitted_at: str


class SubmissionRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registration_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    working_languages TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    email_address TEXT NOT NULL,
                    short_bio TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    submitted_at TEXT NOT NULL
                )
                """
            )

    def create_submission(self, submission: RegistrationSubmission) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO registration_submissions (
                    full_name,
                    working_languages,
                    phone_number,
                    email_address,
                    short_bio,
                    status,
                    submitted_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    submission.full_name,
                    submission.working_languages,
                    submission.phone_number,
                    submission.email_address,
                    submission.short_bio,
                    datetime.now(UTC).isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def list_submissions(self, status: str | None = None) -> list[StoredSubmission]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    """
                    SELECT id, full_name, working_languages, phone_number, email_address, short_bio, status, submitted_at
                    FROM registration_submissions
                    ORDER BY id DESC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, full_name, working_languages, phone_number, email_address, short_bio, status, submitted_at
                    FROM registration_submissions
                    WHERE status = ?
                    ORDER BY id DESC
                    """,
                    (status,),
                ).fetchall()
        return [
            StoredSubmission(
                id=int(row["id"]),
                full_name=row["full_name"],
                working_languages=row["working_languages"],
                phone_number=row["phone_number"],
                email_address=row["email_address"],
                short_bio=row["short_bio"],
                status=row["status"],
                submitted_at=row["submitted_at"],
            )
            for row in rows
        ]

    def update_status(self, submission_id: int, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE registration_submissions
                SET status = ?
                WHERE id = ?
                """,
                (status, submission_id),
            )
