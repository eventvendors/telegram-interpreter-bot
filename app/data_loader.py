from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


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
