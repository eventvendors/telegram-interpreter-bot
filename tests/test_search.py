from __future__ import annotations

import unittest

from app.data_loader import CsvRepository, PersonRecord, PriorityRule
from app.formatters import format_results_message
from app.search import make_language_pair_key, search_people


class StubRepository(CsvRepository):
    def __init__(self, people: list[PersonRecord]) -> None:
        self._people = people

    def load_people(self) -> list[PersonRecord]:
        return self._people

    def load_priority_rules(self) -> list[PriorityRule]:
        return []


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.people = [
            PersonRecord(
                id=1,
                full_name="John Jones",
                service_type="Interpreter",
                short_bio="",
                languages=("English", "French"),
                phone="",
                email="",
                telegram_link="",
                whatsapp_link="",
                is_active=True,
            ),
            PersonRecord(
                id=2,
                full_name="Alice Martin",
                service_type="Interpreter",
                short_bio="",
                languages=("French", "English"),
                phone="",
                email="",
                telegram_link="",
                whatsapp_link="",
                is_active=True,
            ),
            PersonRecord(
                id=3,
                full_name="Nadia Karim",
                service_type="Translator",
                short_bio="",
                languages=("Arabic", "English"),
                phone="",
                email="",
                telegram_link="",
                whatsapp_link="",
                is_active=True,
            ),
        ]
        self.rules = [
            PriorityRule(
                id=1,
                service_type="Interpreter",
                language_pair_key="English|French",
                person_id=1,
                priority_rank=1,
                is_active=True,
            )
        ]

    def test_language_pair_key_ignores_order(self) -> None:
        self.assertEqual(
            make_language_pair_key("French", "English"),
            "English|French",
        )

    def test_priority_rule_moves_person_to_top(self) -> None:
        result = search_people(
            people=self.people,
            rules=self.rules,
            service_type=None,
            language_one="French",
            language_two="English",
        )
        self.assertEqual([person.id for person in result.items], [1, 2])

    def test_search_now_includes_both_interpreters_and_translators(self) -> None:
        result = search_people(
            people=self.people,
            rules=self.rules,
            service_type=None,
            language_one="Arabic",
            language_two="English",
        )
        self.assertEqual(result.total_results, 1)

    def test_duplicate_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_language_pair_key("English", "english")

    def test_results_message_includes_total_matches(self) -> None:
        result = search_people(
            people=self.people,
            rules=self.rules,
            service_type=None,
            language_one="English",
            language_two="French",
        )
        message = format_results_message(result)
        self.assertIn("Total matches: 2", message)

    def test_available_languages_can_be_filtered_by_service_type(self) -> None:
        repo = StubRepository(
            [
                PersonRecord(
                    id=1,
                    full_name="One",
                    service_type="Interpreter",
                    short_bio="",
                    languages=("English", "Thai"),
                    phone="",
                    email="",
                    telegram_link="",
                    whatsapp_link="",
                    is_active=True,
                ),
                PersonRecord(
                    id=2,
                    full_name="Two",
                    service_type="Translator",
                    short_bio="",
                    languages=("English", "Russian"),
                    phone="",
                    email="",
                    telegram_link="",
                    whatsapp_link="",
                    is_active=True,
                ),
            ]
        )

        self.assertEqual(repo.available_languages(service_type="Interpreter"), ["English", "Thai"])
        self.assertEqual(repo.available_languages(service_type="Translator"), ["English", "Russian"])

    def test_second_language_options_can_be_filtered_by_first_language(self) -> None:
        repo = StubRepository(
            [
                PersonRecord(
                    id=1,
                    full_name="One",
                    service_type="Interpreter",
                    short_bio="",
                    languages=("English", "Arabic"),
                    phone="",
                    email="",
                    telegram_link="",
                    whatsapp_link="",
                    is_active=True,
                ),
                PersonRecord(
                    id=2,
                    full_name="Two",
                    service_type="Interpreter",
                    short_bio="",
                    languages=("English", "French"),
                    phone="",
                    email="",
                    telegram_link="",
                    whatsapp_link="",
                    is_active=True,
                ),
                PersonRecord(
                    id=3,
                    full_name="Three",
                    service_type="Interpreter",
                    short_bio="",
                    languages=("Russian", "French"),
                    phone="",
                    email="",
                    telegram_link="",
                    whatsapp_link="",
                    is_active=True,
                ),
            ]
        )

        self.assertEqual(
            repo.available_languages(
                service_type="Interpreter",
                required_language="English",
                exclude_language="English",
            ),
            ["Arabic", "French"],
        )


if __name__ == "__main__":
    unittest.main()
