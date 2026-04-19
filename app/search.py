from __future__ import annotations

from dataclasses import dataclass

from app.data_loader import PersonRecord, PriorityRule


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split()).casefold()


def canonical_service_type(value: str) -> str:
    normalized = normalize_text(value)
    if normalized == "interpreter":
        return "Interpreter"
    if normalized == "translator":
        return "Translator"
    raise ValueError("Service type must be Interpreter or Translator.")


def canonical_language(value: str) -> str:
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        raise ValueError("Language cannot be empty.")
    return cleaned.title()


def make_language_pair_key(language_one: str, language_two: str) -> str:
    first = canonical_language(language_one)
    second = canonical_language(language_two)
    if normalize_text(first) == normalize_text(second):
        raise ValueError("Please choose two different languages.")
    return "|".join(sorted([first, second], key=normalize_text))


@dataclass(frozen=True)
class SearchPage:
    items: list[PersonRecord]
    page: int
    page_size: int
    total_pages: int
    total_results: int
    language_pair_key: str


def search_people(
    people: list[PersonRecord],
    rules: list[PriorityRule],
    service_type: str,
    language_one: str,
    language_two: str,
    page: int = 1,
    page_size: int = 5,
) -> SearchPage:
    service = canonical_service_type(service_type)
    requested_key = make_language_pair_key(language_one, language_two)
    requested_languages = {
        normalize_text(canonical_language(language_one)),
        normalize_text(canonical_language(language_two)),
    }

    matched_people = [
        person
        for person in people
        if person.is_active
        and canonical_service_type(person.service_type) == service
        and requested_languages.issubset({normalize_text(language) for language in person.languages})
    ]

    active_rules = sorted(
        [
            rule
            for rule in rules
            if rule.is_active
            and canonical_service_type(rule.service_type) == service
            and normalize_text(rule.language_pair_key) == normalize_text(requested_key)
        ],
        key=lambda rule: (rule.priority_rank, rule.id),
    )
    rank_lookup = {rule.person_id: index for index, rule in enumerate(active_rules)}

    matched_people.sort(
        key=lambda person: (
            0 if person.id in rank_lookup else 1,
            rank_lookup.get(person.id, 999999),
            person.full_name.casefold(),
            person.id,
        )
    )

    total_results = len(matched_people)
    total_pages = max(1, (total_results + page_size - 1) // page_size)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size

    return SearchPage(
        items=matched_people[start:end],
        page=safe_page,
        page_size=page_size,
        total_pages=total_pages,
        total_results=total_results,
        language_pair_key=requested_key,
    )
