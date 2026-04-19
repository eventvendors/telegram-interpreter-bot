from __future__ import annotations

from urllib.parse import quote

UN_LANGUAGES = ["Arabic", "Chinese", "English", "French", "Russian", "Spanish"]


def service_type_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Interpreter", "callback_data": "service:Interpreter"},
                {"text": "Translator", "callback_data": "service:Translator"},
            ]
        ]
    }


def language_keyboard(
    step: str,
    selected_language: str | None = None,
    include_other_languages: bool = False,
) -> dict:
    rows: list[list[dict]] = []
    primary_languages = list(UN_LANGUAGES)
    for index in range(0, len(primary_languages), 3):
        rows.append(
            [
                {
                    "text": f"① {language}" if language == selected_language else language,
                    "callback_data": (
                        "selected-language"
                        if language == selected_language
                        else f"{step}:{language}"
                    ),
                }
                for language in primary_languages[index : index + 3]
            ]
        )
    rows.append([{"text": "Other Languages", "callback_data": f"{step}-other"}])
    return {"inline_keyboard": rows}


def other_languages_keyboard(languages: list[str], step: str) -> dict:
    rows: list[list[dict]] = []
    for index in range(0, len(languages), 3):
        rows.append(
            [
                {"text": language, "callback_data": f"{step}:{language}"}
                for language in languages[index : index + 3]
            ]
        )
    rows.append([{"text": "Back", "callback_data": f"{step}-back"}])
    return {"inline_keyboard": rows}


def _phone_deep_link(phone_number: str, full_name: str) -> str:
    normalized_phone = "".join(
        character for character in phone_number if character.isdigit() or character == "+"
    )
    encoded_name = quote(full_name)
    return f"tg://resolve?phone={normalized_phone}&text=&profile&name={encoded_name}"


def results_keyboard(
    current_page: int,
    total_pages: int,
    people: list[object] | None = None,
) -> dict:
    rows: list[list[dict]] = [
        [{"text": f"Page {current_page} of {total_pages}", "callback_data": "page-status"}]
    ]
    if people:
        for person in people:
            phone = getattr(person, "phone", "")
            full_name = getattr(person, "full_name", "Contact")
            if phone:
                rows.append(
                    [
                        {
                            "text": f"Call {full_name}",
                            "url": _phone_deep_link(phone, full_name),
                        }
                    ]
                )
    buttons: list[dict] = []
    if current_page > 1:
        buttons.append({"text": "Previous", "callback_data": f"page:{current_page - 1}"})

    start_page = max(1, current_page - 2)
    end_page = min(total_pages, current_page + 2)

    if start_page > 1:
        buttons.append({"text": "1", "callback_data": "page:1"})
        if start_page > 2:
            buttons.append({"text": "...", "callback_data": f"page:{start_page - 1}"})

    for page_number in range(start_page, end_page + 1):
        label = f"[{page_number}]" if page_number == current_page else str(page_number)
        buttons.append({"text": label, "callback_data": f"page:{page_number}"})

    if end_page < total_pages:
        if end_page < total_pages - 1:
            buttons.append({"text": "...", "callback_data": f"page:{end_page + 1}"})
        buttons.append({"text": str(total_pages), "callback_data": f"page:{total_pages}"})

    if current_page < total_pages:
        buttons.append({"text": "Next", "callback_data": f"page:{current_page + 1}"})

    if buttons:
        rows.extend(buttons[i : i + 5] for i in range(0, len(buttons), 5))
    rows.append([{"text": "New search", "callback_data": "new-search"}])
    return {"inline_keyboard": rows}
