from __future__ import annotations

import unittest

from app.data_loader import PersonRecord, PriorityRule
from app.formatters import format_results_message
from app.search import make_language_pair_key, search_people


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
            service_type="Interpreter",
            language_one="French",
            language_two="English",
        )
        self.assertEqual([person.id for person in result.items], [1, 2])

    def test_service_type_must_match(self) -> None:
        result = search_people(
            people=self.people,
            rules=self.rules,
            service_type="Translator",
            language_one="English",
            language_two="French",
        )
        self.assertEqual(result.total_results, 0)

    def test_duplicate_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_language_pair_key("English", "english")

    def test_results_message_includes_total_matches(self) -> None:
        result = search_people(
            people=self.people,
            rules=self.rules,
            service_type="Interpreter",
            language_one="English",
            language_two="French",
        )
        message = format_results_message(result)
        self.assertIn("Total matches: 2", message)


if __name__ == "__main__":
    unittest.main()
