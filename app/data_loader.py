from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

STANDARD_SHORT_BIO = (
    "Professional interpreter available for simultaneous and consecutive assignments in the UAE."
)


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _split_languages(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def _canonical_service_type(value: str) -> str:
    normalized = _normalize_text(value)
    if normalized == "interpreter":
        return "Interpreter"
    if normalized == "translator":
        return "Translator"
    raise ValueError("Service type must be Interpreter or Translator.")


@dataclass(frozen=True)
class PersonRecord:
    id: int
    full_name: str
    service_type: str
    short_bio: str
    languages: tuple[str, ...]
    phone: str
    email: str
    telegram_link: str
    whatsapp_link: str
    is_active: bool


@dataclass(frozen=True)
class PriorityRule:
    id: int
    service_type: str
    language_pair_key: str
    person_id: int
    priority_rank: int
    is_active: bool


class CsvRepository:
    def __init__(self, interpreters_csv: Path, priority_rules_csv: Path) -> None:
        self.interpreters_csv = Path(interpreters_csv)
        self.priority_rules_csv = Path(priority_rules_csv)

    def load_people(self) -> list[PersonRecord]:
        with self.interpreters_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                PersonRecord(
                    id=int(row["id"]),
                    full_name=row["full_name"].strip(),
                    service_type=row["service_type"].strip(),
                    short_bio=row["short_bio"].strip(),
                    languages=tuple(_split_languages(row["languages"])),
                    phone=row.get("phone", "").strip(),
                    email=row.get("email", "").strip(),
                    telegram_link=row.get("telegram_link", "").strip(),
                    whatsapp_link=row.get("whatsapp_link", "").strip(),
                    is_active=_is_truthy(row.get("is_active", "")),
                )
                for row in reader
            ]

    def load_priority_rules(self) -> list[PriorityRule]:
        with self.priority_rules_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                PriorityRule(
                    id=int(row["id"]),
                    service_type=row["service_type"].strip(),
                    language_pair_key=row["language_pair_key"].strip(),
                    person_id=int(row["person_id"]),
                    priority_rank=int(row["priority_rank"]),
                    is_active=_is_truthy(row.get("is_active", "")),
                )
                for row in reader
            ]

    def available_languages(
        self,
        service_type: str | None = None,
        required_language: str | None = None,
        exclude_language: str | None = None,
    ) -> list[str]:
        unique_languages: set[str] = set()
        normalized_service_type = (
            _canonical_service_type(service_type) if service_type is not None else None
        )
        normalized_required_language = (
            _normalize_text(required_language) if required_language is not None else None
        )
        normalized_exclude_language = (
            _normalize_text(exclude_language) if exclude_language is not None else None
        )

        for person in self.load_people():
            if not person.is_active:
                continue
            if (
                normalized_service_type is not None
                and _canonical_service_type(person.service_type) != normalized_service_type
            ):
                continue
            normalized_person_languages = {_normalize_text(language) for language in person.languages}
            if (
                normalized_required_language is not None
                and normalized_required_language not in normalized_person_languages
            ):
                continue
            for language in person.languages:
                if (
                    normalized_exclude_language is not None
                    and _normalize_text(language) == normalized_exclude_language
                ):
                    continue
                unique_languages.add(language)
        return sorted(unique_languages)

    def has_language(
        self,
        language: str,
        service_type: str | None = None,
        required_language: str | None = None,
        exclude_language: str | None = None,
    ) -> bool:
        normalized = language.strip().casefold()
        return any(
            candidate.casefold() == normalized
            for candidate in self.available_languages(
                service_type=service_type,
                required_language=required_language,
                exclude_language=exclude_language,
            )
        )


class SqliteDirectoryRepository(CsvRepository):
    def __init__(
        self,
        interpreters_csv: Path,
        priority_rules_csv: Path,
        db_path: Path,
    ) -> None:
        super().__init__(interpreters_csv, priority_rules_csv)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._bootstrap_from_csv_if_empty()
        self._apply_migrations()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS directory_people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    short_bio TEXT NOT NULL,
                    languages TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telegram_link TEXT NOT NULL,
                    whatsapp_link TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS applied_migrations (
                    migration_key TEXT PRIMARY KEY
                )
                """
            )

    def _bootstrap_from_csv_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM directory_people").fetchone()[0]
            if count:
                return
            for person in super().load_people():
                connection.execute(
                    """
                    INSERT INTO directory_people (
                        id,
                        full_name,
                        service_type,
                        short_bio,
                        languages,
                        phone,
                        email,
                        telegram_link,
                        whatsapp_link,
                        is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        person.id,
                        person.full_name,
                        person.service_type,
                        person.short_bio,
                        ", ".join(person.languages),
                        person.phone,
                        person.email,
                        person.telegram_link,
                        person.whatsapp_link,
                        1 if person.is_active else 0,
                    ),
                )

    def _apply_migrations(self) -> None:
        migration_key = "2026_04_24_standardize_short_bio"
        with self._connect() as connection:
            already_applied = connection.execute(
                "SELECT 1 FROM applied_migrations WHERE migration_key = ?",
                (migration_key,),
            ).fetchone()
            if already_applied:
                return
            connection.execute(
                """
                UPDATE directory_people
                SET short_bio = ?
                """,
                (STANDARD_SHORT_BIO,),
            )
            connection.execute(
                "INSERT INTO applied_migrations (migration_key) VALUES (?)",
                (migration_key,),
            )

    def load_people(self) -> list[PersonRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, full_name, service_type, short_bio, languages, phone, email, telegram_link, whatsapp_link, is_active
                FROM directory_people
                ORDER BY id ASC
                """
            ).fetchall()
        return [
            PersonRecord(
                id=int(row["id"]),
                full_name=row["full_name"],
                service_type=row["service_type"],
                short_bio=row["short_bio"],
                languages=tuple(_split_languages(row["languages"])),
                phone=row["phone"],
                email=row["email"],
                telegram_link=row["telegram_link"],
                whatsapp_link=row["whatsapp_link"],
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def create_person(
        self,
        full_name: str,
        languages: str,
        phone: str,
        email: str,
        short_bio: str,
        service_type: str = "Interpreter",
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO directory_people (
                    full_name,
                    service_type,
                    short_bio,
                    languages,
                    phone,
                    email,
                    telegram_link,
                    whatsapp_link,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, '', '', 1)
                """,
                (
                    full_name.strip(),
                    service_type.strip(),
                    short_bio.strip(),
                    ", ".join(_split_languages(languages)),
                    phone.strip(),
                    email.strip(),
                ),
            )
            return int(cursor.lastrowid)

    def get_person(self, person_id: int) -> PersonRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, full_name, service_type, short_bio, languages, phone, email, telegram_link, whatsapp_link, is_active
                FROM directory_people
                WHERE id = ?
                """,
                (person_id,),
            ).fetchone()
        if row is None:
            return None
        return PersonRecord(
            id=int(row["id"]),
            full_name=row["full_name"],
            service_type=row["service_type"],
            short_bio=row["short_bio"],
            languages=tuple(_split_languages(row["languages"])),
            phone=row["phone"],
            email=row["email"],
            telegram_link=row["telegram_link"],
            whatsapp_link=row["whatsapp_link"],
            is_active=bool(row["is_active"]),
        )

    def update_person(
        self,
        person_id: int,
        full_name: str,
        languages: str,
        phone: str,
        email: str,
        short_bio: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE directory_people
                SET full_name = ?, languages = ?, phone = ?, email = ?, short_bio = ?
                WHERE id = ?
                """,
                (
                    full_name.strip(),
                    ", ".join(_split_languages(languages)),
                    phone.strip(),
                    email.strip(),
                    short_bio.strip(),
                    person_id,
                ),
            )

    def delete_person(self, person_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM directory_people WHERE id = ?",
                (person_id,),
            )
