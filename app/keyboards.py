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
    primary_languages = [
        language for language in UN_LANGUAGES if language != selected_language
    ]
    for index in range(0, len(primary_languages), 3):
        rows.append(
            [
                {"text": language, "callback_data": f"{step}:{language}"}
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


def results_keyboard(current_page: int, total_pages: int) -> dict:
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

    rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    rows.append([{"text": "New search", "callback_data": "new-search"}])
    return {"inline_keyboard": rows}
