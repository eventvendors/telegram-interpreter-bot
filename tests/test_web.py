from __future__ import annotations

from io import BytesIO
from pathlib import Path
import unittest
import uuid

from app.config import Settings
from app.data_loader import SqliteDirectoryRepository
from app.submissions import RegistrationSubmission, SubmissionRepository
from app.web import (
    REGISTRATION_LANGUAGE_OPTIONS,
    _auth_cookie_value,
    _available_language_options,
    _validate_directory_values,
    create_web_app,
)


class WebValidationTests(unittest.TestCase):
    def test_validate_directory_values_enforces_limits(self) -> None:
        values, errors = _validate_directory_values(
            {
                "full_name": "A" * 41,
                "working_languages": "Arabic, MadeUp",
                "phone_number": "+971 50 123 4567 ext",
                "email_address": "not-an-email",
                "short_bio": "B" * 91,
            },
            ["Arabic", "English", "Russian"],
        )

        self.assertEqual(values["working_languages"], "Arabic, MadeUp")
        self.assertEqual(errors["full_name"], "Maximum 40 characters.")
        self.assertEqual(
            errors["working_languages"],
            "Select languages from the dropdown only.",
        )
        self.assertEqual(
            errors["phone_number"],
            "Use digits, spaces, +, -, ( and ) only.",
        )
        self.assertEqual(errors["email_address"], "Enter a valid email address.")
        self.assertEqual(
            errors["short_bio"],
            "Maximum 90 characters including spaces.",
        )

    def test_validate_directory_values_limits_languages_to_four(self) -> None:
        _, errors = _validate_directory_values(
            {
                "full_name": "Jane Doe",
                "working_languages": "Arabic, English, Russian, French, Hindi",
                "phone_number": "+971501234567",
                "email_address": "jane@example.com",
                "short_bio": "Interpreter in Dubai.",
            },
            ["Arabic", "English", "Russian", "French", "Hindi"],
        )

        self.assertEqual(errors["working_languages"], "Maximum 4 languages.")

    def test_available_language_options_include_extra_registration_languages(self) -> None:
        unique = uuid.uuid4().hex
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        interpreters_csv = storage_dir / f"interpreters-options-{unique}.csv"
        priority_rules_csv = storage_dir / f"priority-options-{unique}.csv"
        db_path = storage_dir / f"options-{unique}.db"

        interpreters_csv.write_text(
            "\n".join(
                [
                    "id,full_name,service_type,short_bio,languages,phone,email,telegram_link,whatsapp_link,is_active",
                    '1,John Jones,Interpreter,Conference interpreter,"Arabic, English",+971500000001,john@example.com,,,true',
                ]
            ),
            encoding="utf-8",
        )
        priority_rules_csv.write_text(
            "id,service_type,language_pair_key,person_id,priority_rank,is_active\n",
            encoding="utf-8",
        )

        directory_repository = SqliteDirectoryRepository(interpreters_csv, priority_rules_csv, db_path)
        language_options = _available_language_options(directory_repository)

        for language in REGISTRATION_LANGUAGE_OPTIONS:
            self.assertIn(language, language_options)

    def test_approve_does_not_publish_invalid_submission(self) -> None:
        unique = uuid.uuid4().hex
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        interpreters_csv = storage_dir / f"interpreters-{unique}.csv"
        priority_rules_csv = storage_dir / f"priority-{unique}.csv"
        db_path = storage_dir / f"web-{unique}.db"

        interpreters_csv.write_text(
            "\n".join(
                [
                    "id,full_name,service_type,short_bio,languages,phone,email,telegram_link,whatsapp_link,is_active",
                    '1,John Jones,Interpreter,Conference interpreter,"Arabic, English",+971500000001,john@example.com,,,true',
                ]
            ),
            encoding="utf-8",
        )
        priority_rules_csv.write_text(
            "id,service_type,language_pair_key,person_id,priority_rank,is_active\n",
            encoding="utf-8",
        )

        settings = Settings(
            telegram_bot_token="test-token",
            interpreters_csv=interpreters_csv,
            priority_rules_csv=priority_rules_csv,
            submissions_db=db_path,
            public_base_url="https://example.com",
            admin_password="secret",
            github_backup_token="",
            github_repo="eventvendors/telegram-interpreter-bot",
            github_backup_branch="main",
            backup_git_name="Test",
            backup_git_email="test@example.com",
        )

        submission_repository = SubmissionRepository(db_path)
        submission_id = submission_repository.create_submission(
            RegistrationSubmission(
                full_name="Bad Data",
                working_languages="Arabic, nonsense123",
                phone_number="+971500000002",
                email_address="bad@example.com",
                short_bio="Still looks plausible.",
            )
        )
        app = create_web_app(settings)

        status_headers: dict[str, object] = {}

        def start_response(status, headers):
            status_headers["status"] = status
            status_headers["headers"] = headers

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/admin/action",
            "CONTENT_LENGTH": str(len(f"submission_id={submission_id}&action=approved")),
            "wsgi.input": BytesIO(f"submission_id={submission_id}&action=approved".encode("utf-8")),
            "HTTP_COOKIE": f"admin_auth={_auth_cookie_value('secret')}",
        }

        response = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual(status_headers["status"], "400 Bad Request")
        self.assertIn("cannot be approved", response)
        pending = submission_repository.list_submissions(status="pending")
        self.assertEqual(len(pending), 1)
        directory_repository = SqliteDirectoryRepository(interpreters_csv, priority_rules_csv, db_path)
        people = directory_repository.load_people()
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].full_name, "John Jones")


if __name__ == "__main__":
    unittest.main()
