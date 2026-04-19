from __future__ import annotations

from html import escape

from app.data_loader import PersonRecord
from app.search import SearchPage


def _contact_line(label: str, value: str) -> str:
    if not value:
        return f"<b>{label}:</b> Not provided"
    return f"<b>{label}:</b> {escape(value)}"


def _phone_line(value: str) -> str:
    if not value:
        return "<b>Phone:</b> Not provided"
    display_value = escape(value)
    dial_value = "".join(character for character in value if character.isdigit() or character == "+")
    safe_dial_value = escape(dial_value, quote=True)
    return f"<b>Phone:</b> <code>{display_value}</code>\n<a href=\"tel:{safe_dial_value}\">Call this number</a>"


def _link_line(label: str, value: str) -> str:
    if not value:
        return f"<b>{label}:</b> Not provided"
    safe_value = escape(value, quote=True)
    return f'<b>{label}:</b> <a href="{safe_value}">{safe_value}</a>'


def _email_line(value: str) -> str:
    if not value:
        return "<b>Email:</b> Not provided"
    safe_value = escape(value, quote=True)
    return f'<b>Email:</b> <a href="mailto:{safe_value}">{safe_value}</a>'


def format_result_card(person: PersonRecord, index: int) -> str:
    lines = [
        f"<b>{index}. {escape(person.full_name)}</b>",
        escape(person.short_bio),
        f"<b>Languages:</b> {escape(', '.join(person.languages))}",
        _phone_line(person.phone),
        _email_line(person.email),
        _link_line("Telegram", person.telegram_link),
        _link_line("WhatsApp", person.whatsapp_link),
    ]
    return "\n".join(lines)


def format_results_message(search_page: SearchPage) -> str:
    if not search_page.items:
        return (
            "No matches found for that search.\n\n"
            "Try a different service type or language pair."
        )

    header = (
        f"<b>Results</b>\n"
        f"Language pair: {escape(search_page.language_pair_key.replace('|', ' + '))}\n"
        f"Page {search_page.page} of {search_page.total_pages}\n"
        f"Total matches: {search_page.total_results}"
    )

    start_index = (search_page.page - 1) * search_page.page_size + 1
    cards = [
        format_result_card(person, start_index + offset)
        for offset, person in enumerate(search_page.items)
    ]
    return header + "\n\n" + "\n\n".join(cards)
