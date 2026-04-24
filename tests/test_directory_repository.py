from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from app.data_loader import STANDARD_SHORT_BIO, SqliteDirectoryRepository


class DirectoryRepositoryTests(unittest.TestCase):
    def test_bootstrap_from_csv_and_crud(self) -> None:
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        unique = uuid.uuid4().hex
        interpreters_csv = storage_dir / f"interpreters-{unique}.csv"
        priority_rules_csv = storage_dir / f"priority-{unique}.csv"
        db_path = storage_dir / f"directory-{unique}.db"

        interpreters_csv.write_text(
            "\n".join(
                [
                    "id,full_name,service_type,short_bio,languages,phone,email,telegram_link,whatsapp_link,is_active",
                    '1,John Jones,Interpreter,Conference interpreter,"English, French",+971500000001,john@example.com,,,true',
                ]
            ),
            encoding="utf-8",
        )
        priority_rules_csv.write_text(
            "id,service_type,language_pair_key,person_id,priority_rank,is_active\n",
            encoding="utf-8",
        )

        repository = SqliteDirectoryRepository(interpreters_csv, priority_rules_csv, db_path)
        people = repository.load_people()
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].full_name, "John Jones")
        self.assertEqual(people[0].short_bio, STANDARD_SHORT_BIO)

        new_id = repository.create_person(
            full_name="Jane Doe",
            languages="Arabic, English",
            phone="+971500000002",
            email="jane@example.com",
            short_bio="Interpreter in Dubai.",
        )
        created = repository.get_person(new_id)
        self.assertIsNotNone(created)
        self.assertEqual(created.full_name, "Jane Doe")

        repository.update_person(
            person_id=new_id,
            full_name="Jane Smith",
            languages="Arabic, English, French",
            phone="+971500000003",
            email="jane.smith@example.com",
            short_bio="Updated bio.",
        )
        updated = repository.get_person(new_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.full_name, "Jane Smith")
        self.assertEqual(updated.languages, ("Arabic", "English", "French"))

        repository.delete_person(new_id)
        self.assertIsNone(repository.get_person(new_id))


if __name__ == "__main__":
    unittest.main()
