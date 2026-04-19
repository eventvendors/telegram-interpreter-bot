from __future__ import annotations

def service_type_keyboard() -> dict:
    return {
        "keyboard": [
            [{"text": "Interpreter"}, {"text": "Translator"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def language_keyboard(languages: list[str]) -> dict:
    rows: list[list[dict]] = []
    row: list[dict] = []
    for language in languages:
        row.append({"text": language})
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


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
