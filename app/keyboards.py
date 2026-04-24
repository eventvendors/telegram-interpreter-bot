from __future__ import annotations

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


def results_keyboard(
    current_page: int,
    total_pages: int,
) -> dict:
    rows: list[list[dict]] = []
    if total_pages > 1:
        rows.append(
            [
                (
                    {"text": "Previous", "callback_data": f"page:{current_page - 1}"}
                    if current_page > 1
                    else {"text": "Previous", "callback_data": "page-status"}
                ),
                {"text": f"Page {current_page} of {total_pages}", "callback_data": "page-status"},
                (
                    {"text": "Next", "callback_data": f"page:{current_page + 1}"}
                    if current_page < total_pages
                    else {"text": "Next", "callback_data": "page-status"}
                ),
            ]
        )
    rows.append([{"text": "New search", "callback_data": "new-search"}])
    return {"inline_keyboard": rows}
