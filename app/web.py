from __future__ import annotations

from hashlib import sha256
from html import escape
from http.cookies import SimpleCookie
import re
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app.config import Settings
from app.data_loader import PersonRecord, SqliteDirectoryRepository
from app.submissions import RegistrationSubmission, StoredSubmission, SubmissionRepository

ALLOWED_PHONE_CHARACTERS = set("0123456789 +-()")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REGISTRATION_LANGUAGE_OPTIONS = [
    "Hindi",
    "Japanese",
    "Kazakh",
    "Ukrainian",
    "Urdu",
    "Uzbek",
]


def create_web_app(settings: Settings):
    repository = SubmissionRepository(settings.submissions_db)
    directory_repository = SqliteDirectoryRepository(
        settings.interpreters_csv,
        settings.priority_rules_csv,
        settings.submissions_db,
    )

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        language_options = _available_language_options(directory_repository)

        if method == "GET" and path in {"/", "/info", "/register"}:
            return _html_response(
                start_response,
                200,
                _render_register_page(language_options=language_options),
            )
        if method == "POST" and path == "/register":
            submission, errors = _parse_submission(environ, language_options)
            if errors:
                return _html_response(
                    start_response,
                    400,
                    _render_register_page(
                        errors=errors,
                        form_values=submission,
                        language_options=language_options,
                    ),
                )
            repository.create_submission(
                RegistrationSubmission(
                    full_name=submission["full_name"],
                    working_languages=submission["working_languages"],
                    phone_number=submission["phone_number"],
                    email_address=submission["email_address"],
                    short_bio=submission["short_bio"],
                )
            )
            return _redirect(start_response, "/register/success")
        if method == "GET" and path == "/register/success":
            return _html_response(start_response, 200, _render_success_page())
        if method == "GET" and path == "/admin":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if _is_admin_authenticated(environ, settings.admin_password):
                pending = repository.list_submissions(status="pending")
                return _html_response(
                    start_response,
                    200,
                    _render_admin_page("Pending", "pending", pending),
                )
            return _html_response(start_response, 200, _render_admin_login_page())
        if method == "GET" and path == "/admin/approved":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if _is_admin_authenticated(environ, settings.admin_password):
                approved = repository.list_submissions(status="approved")
                return _html_response(
                    start_response,
                    200,
                    _render_admin_page("Approved", "approved", approved),
                )
            return _html_response(start_response, 200, _render_admin_login_page())
        if method == "GET" and path == "/admin/rejected":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if _is_admin_authenticated(environ, settings.admin_password):
                rejected = repository.list_submissions(status="rejected")
                return _html_response(
                    start_response,
                    200,
                    _render_admin_page("Rejected", "rejected", rejected),
                )
            return _html_response(start_response, 200, _render_admin_login_page())
        if method == "GET" and path == "/admin/directory":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if _is_admin_authenticated(environ, settings.admin_password):
                people = directory_repository.load_people()
                return _html_response(
                    start_response,
                    200,
                    _render_directory_page(people),
                )
            return _html_response(start_response, 200, _render_admin_login_page())
        if method == "GET" and path == "/admin/directory/new":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _html_response(start_response, 200, _render_admin_login_page())
            return _html_response(
                start_response,
                200,
                _render_directory_create_page(language_options=language_options),
            )
        if method == "GET" and path == "/admin/directory/edit":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _html_response(start_response, 200, _render_admin_login_page())
            query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
            try:
                person_id = int(query.get("id", ["0"])[0])
            except ValueError:
                person_id = 0
            person = directory_repository.get_person(person_id)
            if person is None:
                return _html_response(start_response, 404, _render_not_found_page())
            return _html_response(
                start_response,
                200,
                _render_directory_edit_page(person, language_options=language_options),
            )
        if method == "POST" and path == "/admin/login":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            payload = _parse_form_body(environ)
            if _first_value(payload, "password") == settings.admin_password:
                return _redirect_with_cookie(
                    start_response,
                    "/admin",
                    "admin_auth",
                    _auth_cookie_value(settings.admin_password),
                )
            return _html_response(
                start_response,
                401,
                _render_admin_login_page(error="Incorrect password."),
            )
        if method == "POST" and path == "/admin/action":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _redirect(start_response, "/admin")
            payload = _parse_form_body(environ)
            action = _first_value(payload, "action").lower()
            try:
                submission_id = int(_first_value(payload, "submission_id") or "0")
            except ValueError:
                submission_id = 0
            if submission_id > 0 and action in {"approved", "rejected"}:
                if action == "approved":
                    submission = repository.get_submission(submission_id)
                    if submission is None:
                        return _redirect(start_response, "/admin")
                    _, errors = _validate_directory_values(
                        {
                            "full_name": submission.full_name,
                            "working_languages": submission.working_languages,
                            "phone_number": submission.phone_number,
                            "email_address": submission.email_address,
                            "short_bio": submission.short_bio,
                        },
                        language_options,
                    )
                    if errors:
                        pending = repository.list_submissions(status="pending")
                        return _html_response(
                            start_response,
                            400,
                            _render_admin_page(
                                "Pending",
                                "pending",
                                pending,
                                error_message="This submission cannot be approved until its data matches the form rules.",
                            ),
                        )
                    repository.update_status(submission_id, action)
                    directory_repository.create_person(
                        full_name=submission.full_name,
                        languages=submission.working_languages,
                        phone=submission.phone_number,
                        email=submission.email_address,
                        short_bio=submission.short_bio,
                    )
                else:
                    repository.update_status(submission_id, action)
            return _redirect(start_response, "/admin")
        if method == "POST" and path == "/admin/directory/edit":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _redirect(start_response, "/admin")
            payload = _parse_form_body(environ)
            form_values, errors = _parse_directory_form(payload, language_options)
            try:
                person_id = int(_first_value(payload, "person_id") or "0")
            except ValueError:
                person_id = 0
            person = directory_repository.get_person(person_id)
            if person is None:
                return _html_response(start_response, 404, _render_not_found_page())
            if errors:
                return _html_response(
                    start_response,
                    400,
                    _render_directory_edit_page(
                        person,
                        errors=errors,
                        form_values=form_values,
                        language_options=language_options,
                    ),
                )
            directory_repository.update_person(
                person_id=person_id,
                full_name=form_values["full_name"],
                languages=form_values["working_languages"],
                phone=form_values["phone_number"],
                email=form_values["email_address"],
                short_bio=form_values["short_bio"],
            )
            return _redirect(start_response, "/admin/directory")
        if method == "POST" and path == "/admin/directory/new":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _redirect(start_response, "/admin")
            payload = _parse_form_body(environ)
            form_values, errors = _parse_directory_form(payload, language_options)
            if errors:
                return _html_response(
                    start_response,
                    400,
                    _render_directory_create_page(
                        errors=errors,
                        form_values=form_values,
                        language_options=language_options,
                    ),
                )
            directory_repository.create_person(
                full_name=form_values["full_name"],
                languages=form_values["working_languages"],
                phone=form_values["phone_number"],
                email=form_values["email_address"],
                short_bio=form_values["short_bio"],
            )
            return _redirect(start_response, "/admin/directory")
        if method == "POST" and path == "/admin/directory/delete":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            if not _is_admin_authenticated(environ, settings.admin_password):
                return _redirect(start_response, "/admin")
            payload = _parse_form_body(environ)
            try:
                person_id = int(_first_value(payload, "person_id") or "0")
            except ValueError:
                person_id = 0
            if person_id > 0:
                directory_repository.delete_person(person_id)
            return _redirect(start_response, "/admin/directory")

        return _html_response(start_response, 404, _render_not_found_page())

    return application


def serve_web_app(settings: Settings) -> None:
    application = create_web_app(settings)
    with make_server(settings.web_host, settings.web_port, application) as server:
        server.serve_forever()


def _parse_submission(
    environ,
    language_options: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    payload = _parse_form_body(environ)
    return _parse_directory_form(payload, language_options)


def _parse_directory_form(
    payload: dict[str, list[str]],
    language_options: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    values = {
        "full_name": _first_value(payload, "full_name"),
        "working_languages": _normalize_language_selection(payload),
        "phone_number": _first_value(payload, "phone_number"),
        "email_address": _first_value(payload, "email_address"),
        "short_bio": _first_value(payload, "short_bio"),
    }
    return _validate_directory_values(values, language_options)


def _validate_directory_values(
    values: dict[str, str],
    language_options: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    values = dict(values)

    errors: dict[str, str] = {}
    for field_name, field_value in values.items():
        if not field_value:
            errors[field_name] = "This field is required."

    if values["full_name"] and len(values["full_name"]) > 30:
        errors["full_name"] = "Maximum 30 characters."

    if values["working_languages"]:
        allowed_languages = {language.casefold() for language in language_options}
        selected_languages = [language.strip() for language in values["working_languages"].split(",")]
        if not selected_languages or any(not language for language in selected_languages):
            errors["working_languages"] = "Select at least one language."
        elif len(selected_languages) > 4:
            errors["working_languages"] = "Maximum 4 languages."
        elif any(language.casefold() not in allowed_languages for language in selected_languages):
            errors["working_languages"] = "Select languages from the dropdown only."

    if values["phone_number"]:
        if len(values["phone_number"]) > 20:
            errors["phone_number"] = "Maximum 20 characters."
        elif any(character not in ALLOWED_PHONE_CHARACTERS for character in values["phone_number"]):
            errors["phone_number"] = "Use digits, spaces, +, -, ( and ) only."

    if values["email_address"]:
        if len(values["email_address"]) > 50:
            errors["email_address"] = "Maximum 50 characters."
        elif not EMAIL_PATTERN.match(values["email_address"]):
            errors["email_address"] = "Enter a valid email address."

    if values["short_bio"] and len(values["short_bio"]) > 100:
        errors["short_bio"] = "Maximum 100 characters including spaces."

    return values, errors


def _parse_form_body(environ) -> dict[str, list[str]]:
    content_length = int(environ.get("CONTENT_LENGTH") or "0")
    raw_body = environ["wsgi.input"].read(content_length).decode("utf-8")
    return parse_qs(raw_body, keep_blank_values=True)


def _first_value(payload: dict[str, list[str]], key: str) -> str:
    return payload.get(key, [""])[0].strip()


def _normalize_language_selection(payload: dict[str, list[str]]) -> str:
    selected = [value.strip() for value in payload.get("working_languages", []) if value.strip()]
    seen: set[str] = set()
    unique = []
    for language in selected:
        normalized = language.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(language)
    return ", ".join(unique)


def _available_language_options(directory_repository: SqliteDirectoryRepository) -> list[str]:
    unique_languages = {
        language
        for person in directory_repository.load_people()
        for language in person.languages
        if language.strip()
    }
    unique_languages.update(REGISTRATION_LANGUAGE_OPTIONS)
    return sorted(unique_languages, key=str.casefold)


def _html_response(start_response, status_code: int, html: str):
    status_map = {
        200: "200 OK",
        400: "400 Bad Request",
        401: "401 Unauthorized",
        404: "404 Not Found",
        503: "503 Service Unavailable",
    }
    body = html.encode("utf-8")
    start_response(
        status_map[status_code],
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location)])
    return [b""]


def _redirect_with_cookie(start_response, location: str, key: str, value: str):
    cookie = SimpleCookie()
    cookie[key] = value
    cookie[key]["path"] = "/"
    cookie[key]["httponly"] = True
    start_response(
        "303 See Other",
        [
            ("Location", location),
            ("Set-Cookie", cookie.output(header="").strip()),
        ],
    )
    return [b""]


def _render_page(title: str, body: str, wide: bool = False, theme: str = "default") -> str:
    main_width = "1200px" if wide else "620px"
    body_class = "theme-register" if theme == "register" else "theme-default"
    main_class = "panel-register" if theme == "register" else "panel-default"
    register_script = """
  <script>
    document.addEventListener("DOMContentLoaded", function () {
      const widgets = document.querySelectorAll("[data-language-widget]");
      widgets.forEach(function (widget) {
        const toggle = widget.querySelector("[data-language-toggle]");
        const menu = widget.querySelector("[data-language-menu]");
        const summary = widget.querySelector("[data-language-summary]");
        const counter = widget.querySelector("[data-language-counter]");
        const checkboxes = Array.from(widget.querySelectorAll('input[type="checkbox"][data-language-option]'));
        const hiddenSelect = widget.querySelector("select[name='working_languages']");
        const maxSelection = Number(widget.getAttribute("data-max-selection") || "4");

        if (!toggle || !menu || !summary || !counter || !hiddenSelect || !checkboxes.length) {
          return;
        }

        function syncSelection() {
          const checked = checkboxes.filter(function (checkbox) { return checkbox.checked; });
          const selectedValues = checked.map(function (checkbox) { return checkbox.value; });

          Array.from(hiddenSelect.options).forEach(function (option) {
            option.selected = selectedValues.includes(option.value);
          });

          if (!selectedValues.length) {
            summary.textContent = "Select languages";
          } else if (selectedValues.length === 1) {
            summary.textContent = selectedValues[0];
          } else {
            summary.textContent = selectedValues.slice(0, 2).join(", ") + (selectedValues.length > 2 ? " +" + (selectedValues.length - 2) : "");
          }

          widget.classList.toggle("has-selection", selectedValues.length > 0);
          counter.textContent = selectedValues.length ? selectedValues.length + " of " + maxSelection + " selected" : "Choose up to " + maxSelection + " working languages.";

          const limitReached = selectedValues.length >= maxSelection;
          checkboxes.forEach(function (checkbox) {
            checkbox.disabled = !checkbox.checked && limitReached;
          });
        }

        function closeMenu() {
          widget.classList.remove("is-open");
          toggle.setAttribute("aria-expanded", "false");
        }

        toggle.addEventListener("click", function () {
          const isOpen = widget.classList.toggle("is-open");
          toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        checkboxes.forEach(function (checkbox) {
          checkbox.addEventListener("change", syncSelection);
        });

        document.addEventListener("click", function (event) {
          if (!widget.contains(event.target)) {
            closeMenu();
          }
        });

        document.addEventListener("keydown", function (event) {
          if (event.key === "Escape") {
            closeMenu();
          }
        });

        syncSelection();
      });
    });
  </script>""" if theme == "register" else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    main {{
      width: min(100%, {main_width});
      padding: 28px 22px;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 28px;
      line-height: 1.2;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 20px;
      line-height: 1.25;
    }}
    .line {{
      margin: 0 0 12px;
      white-space: pre-line;
    }}
    .helper {{
      margin: 8px 0 0;
      color: inherit;
      font-size: 13px;
      opacity: 0.85;
    }}
    .block {{
      margin-top: 18px;
    }}
    .label {{
      display: block;
      margin: 0 0 6px;
      font-size: 14px;
      color: #b8c7d8;
    }}
    input, textarea, select {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid #31465f;
      background: #081321;
      color: #f3f7fb;
      font: inherit;
    }}
    select {{
      min-height: 220px;
    }}
    textarea {{
      min-height: 88px;
      resize: vertical;
    }}
    .error {{
      margin-top: 6px;
      color: #ffb1b1;
      font-size: 13px;
    }}
    .button {{
      display: inline-block;
      width: 100%;
      margin-top: 22px;
      padding: 13px 16px;
      border: 0;
      border-radius: 10px;
      background: #f3f7fb;
      color: #07111f;
      text-align: center;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }}
    .button-inline {{
      display: inline-block;
      width: auto;
      margin-top: 0;
      padding: 9px 14px;
      border-radius: 8px;
      background: #f3f7fb;
      color: #07111f;
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
    }}
    .button-row {{
      display: flex;
      gap: 12px;
      margin-top: 22px;
    }}
    .button-row .button,
    .button-row .button-inline {{
      flex: 0 0 auto;
      min-width: 180px;
      margin-top: 0;
      text-align: center;
    }}
    .small {{
      color: #b8c7d8;
      font-size: 13px;
    }}
    .nav-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin: 0 0 12px;
    }}
    .nav-row .line {{
      margin: 0;
    }}
    .card {{
      margin-top: 18px;
      padding: 16px;
      border: 1px solid #22344b;
      border-radius: 12px;
      background: #081321;
    }}
    .table-wrap {{
      margin-top: 18px;
      overflow-x: auto;
      border: 1px solid #22344b;
      border-radius: 12px;
      background: #081321;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #22344b;
      vertical-align: top;
      text-align: left;
      font-size: 13px;
      line-height: 1.35;
      word-break: break-word;
    }}
    th {{
      color: #b8c7d8;
      font-weight: 700;
      background: #0b1626;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }}
    .actions form {{
      flex: 1;
    }}
    .actions button {{
      width: 100%;
      padding: 11px 12px;
      border: 0;
      border-radius: 10px;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }}
    .approve {{
      background: #dff7e5;
      color: #08210f;
    }}
    .reject {{
      background: #f9dede;
      color: #2a0c0c;
    }}
    .row-actions {{
      display: flex;
      gap: 8px;
      min-width: 140px;
    }}
    .row-actions form {{
      margin: 0;
      flex: 1;
    }}
    .row-actions button {{
      width: 100%;
      padding: 8px 10px;
      border: 0;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }}
    body.theme-default {{
      background: #07111f;
      color: #f3f7fb;
      align-items: flex-start;
    }}
    body.theme-default main.panel-default {{
      background: #0d1b2e;
      border: 1px solid #22344b;
      border-radius: 14px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28);
    }}
    body.theme-default .label {{
      color: #b8c7d8;
    }}
    body.theme-default input,
    body.theme-default textarea,
    body.theme-default select {{
      border: 1px solid #31465f;
      background: #081321;
      color: #f3f7fb;
    }}
    body.theme-default select {{
      min-height: 220px;
    }}
    body.theme-default textarea {{
      min-height: 88px;
      resize: vertical;
    }}
    body.theme-default .error {{
      color: #ffb1b1;
      font-size: 13px;
    }}
    body.theme-default .button {{
      display: inline-block;
      width: 100%;
      margin-top: 22px;
      padding: 13px 16px;
      border: 0;
      border-radius: 10px;
      background: #f3f7fb;
      color: #07111f;
      text-align: center;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }}
    body.theme-default .small {{
      color: #b8c7d8;
      font-size: 13px;
    }}
    body.theme-default .card {{
      border: 1px solid #22344b;
      background: #081321;
    }}
    body.theme-default .table-wrap {{
      border: 1px solid #22344b;
      background: #081321;
    }}
    body.theme-default th,
    body.theme-default td {{
      border-bottom: 1px solid #22344b;
    }}
    body.theme-default th {{
      color: #b8c7d8;
      background: #0b1626;
    }}
    body.theme-register {{
      color-scheme: light;
      color: #163145;
      background:
        radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0) 34%),
        linear-gradient(180deg, #edf8fb 0%, #d9eff2 44%, #eff7fa 100%);
      position: relative;
      overflow-x: hidden;
    }}
    body.theme-register::before,
    body.theme-register::after {{
      content: "";
      position: fixed;
      inset: auto 0 0 0;
      pointer-events: none;
    }}
    body.theme-register::before {{
      height: 36vh;
      opacity: 0.38;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0), rgba(183, 219, 226, 0.4)),
        linear-gradient(90deg,
          transparent 0 8%,
          rgba(110, 156, 171, 0.18) 8% 9%,
          transparent 9% 17%,
          rgba(110, 156, 171, 0.14) 17% 19%,
          transparent 19% 28%,
          rgba(110, 156, 171, 0.22) 28% 29.6%,
          transparent 29.6% 41%,
          rgba(110, 156, 171, 0.12) 41% 43%,
          transparent 43% 59%,
          rgba(110, 156, 171, 0.18) 59% 60.5%,
          transparent 60.5% 73%,
          rgba(110, 156, 171, 0.12) 73% 75.5%,
          transparent 75.5% 86%,
          rgba(110, 156, 171, 0.2) 86% 87.5%,
          transparent 87.5% 100%);
      clip-path: polygon(0 100%, 0 67%, 6% 67%, 6% 51%, 9% 51%, 9% 61%, 13% 61%, 13% 40%, 17% 40%, 17% 59%, 24% 59%, 24% 35%, 28% 35%, 28% 60%, 40% 60%, 40% 47%, 42% 47%, 42% 58%, 58% 58%, 58% 31%, 61% 31%, 61% 59%, 72% 59%, 72% 43%, 76% 43%, 76% 59%, 86% 59%, 86% 23%, 88% 23%, 88% 59%, 100% 59%, 100% 100%);
    }}
    body.theme-register::after {{
      height: 28vh;
      background: linear-gradient(180deg, rgba(216, 238, 242, 0), rgba(207, 232, 236, 0.62));
    }}
    body.theme-register main.panel-register {{
      position: relative;
      width: min(100%, 540px);
      padding: 34px 30px 28px;
      border-radius: 34px;
      border: 1px solid rgba(255, 255, 255, 0.68);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.5));
      box-shadow:
        0 28px 80px rgba(64, 116, 132, 0.15),
        inset 0 1px 0 rgba(255, 255, 255, 0.72);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
    }}
    body.theme-register h1 {{
      margin-bottom: 10px;
      color: #163145;
      font-size: clamp(30px, 5vw, 34px);
      letter-spacing: -0.03em;
    }}
    body.theme-register .line {{
      color: #36576b;
      margin-bottom: 10px;
    }}
    body.theme-register .label {{
      margin-bottom: 8px;
      color: #163145;
      font-size: 14px;
      font-weight: 600;
    }}
    body.theme-register .block {{
      margin-top: 20px;
    }}
    body.theme-register input,
    body.theme-register textarea,
    body.theme-register select,
    body.theme-register .language-toggle {{
      border: 1px solid rgba(140, 176, 188, 0.6);
      background: rgba(255, 255, 255, 0.88);
      color: #163145;
      border-radius: 14px;
      padding: 13px 16px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
      transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
    }}
    body.theme-register input::placeholder,
    body.theme-register textarea::placeholder {{
      color: #6f8797;
    }}
    body.theme-register input:focus,
    body.theme-register textarea:focus,
    body.theme-register select:focus,
    body.theme-register .language-toggle:focus,
    body.theme-register .button:focus {{
      outline: none;
      border-color: #2d9aa0;
      box-shadow: 0 0 0 4px rgba(45, 154, 160, 0.14);
    }}
    body.theme-register textarea {{
      min-height: 108px;
      resize: vertical;
    }}
    body.theme-register .error {{
      margin-top: 8px;
      color: #9f3044;
      font-size: 13px;
      font-weight: 500;
    }}
    body.theme-register .button {{
      display: inline-block;
      width: 100%;
      margin-top: 24px;
      padding: 16px 18px;
      border: 0;
      border-radius: 999px;
      background: linear-gradient(135deg, #2e9fa2 0%, #237f8f 100%);
      color: #ffffff;
      text-align: center;
      font-weight: 700;
      letter-spacing: 0.01em;
      text-decoration: none;
      cursor: pointer;
      box-shadow: 0 18px 36px rgba(35, 127, 143, 0.18);
      transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }}
    body.theme-register .button:hover {{
      transform: translateY(-1px);
      box-shadow: 0 22px 42px rgba(35, 127, 143, 0.24);
      filter: saturate(1.03);
    }}
    body.theme-register .small {{
      color: #537385;
      font-size: 13px;
    }}
    .register-hero {{
      display: flex;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 8px;
    }}
    .register-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: linear-gradient(180deg, rgba(220, 243, 246, 0.95), rgba(202, 233, 238, 0.78));
      color: #1f7d8d;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
      flex: 0 0 60px;
    }}
    .register-badge svg {{
      width: 28px;
      height: 28px;
    }}
    .register-title-group {{
      min-width: 0;
    }}
    .register-subtitle {{
      margin: 0 0 8px;
      color: #36576b;
      font-size: 16px;
    }}
    .register-helper {{
      margin: 0;
      color: #5d7d8d;
      font-size: 14px;
    }}
    .register-footer-note {{
      margin: 14px 4px 0;
      text-align: center;
      color: #4e6f81;
      font-size: 13px;
    }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .language-select {{
      position: relative;
    }}
    .language-toggle {{
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }}
    .language-summary {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #557081;
    }}
    .language-widget.has-selection .language-summary {{
      color: #163145;
    }}
    .language-caret {{
      width: 10px;
      height: 10px;
      border-right: 2px solid #6f8797;
      border-bottom: 2px solid #6f8797;
      transform: rotate(45deg) translateY(-2px);
      transition: transform 0.2s ease;
      flex: 0 0 auto;
      margin-right: 4px;
    }}
    .language-widget.is-open .language-caret {{
      transform: rotate(-135deg) translateY(-1px);
    }}
    .language-menu {{
      position: absolute;
      inset: calc(100% + 10px) 0 auto;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(140, 176, 188, 0.45);
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 24px 44px rgba(55, 102, 117, 0.16);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      display: none;
      z-index: 20;
    }}
    .language-widget.is-open .language-menu {{
      display: block;
    }}
    .language-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      max-height: 252px;
      overflow-y: auto;
      padding-right: 4px;
    }}
    .language-option {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 44px;
      padding: 10px 12px;
      border-radius: 14px;
      background: #f6fbfc;
      border: 1px solid rgba(185, 213, 220, 0.7);
      cursor: pointer;
      color: #163145;
      font-size: 14px;
    }}
    .language-option input {{
      width: 18px;
      height: 18px;
      margin: 0;
      flex: 0 0 auto;
      accent-color: #2d9aa0;
      box-shadow: none;
      padding: 0;
    }}
    .language-option span {{
      line-height: 1.2;
    }}
    .language-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 10px;
      color: #5c7a8b;
      font-size: 12px;
    }}
    @media (max-width: 640px) {{
      body {{
        padding: 14px;
      }}
      body.theme-register main.panel-register {{
        width: 100%;
        padding: 24px 16px 22px;
        border-radius: 24px;
      }}
      .register-hero {{
        gap: 12px;
      }}
      .register-badge {{
        width: 52px;
        height: 52px;
        flex-basis: 52px;
      }}
      .language-grid {{
        grid-template-columns: 1fr;
        max-height: 224px;
      }}
      .button-row {{
        flex-direction: column;
      }}
      .button-row .button,
      .button-row .button-inline {{
        width: 100%;
        min-width: 0;
      }}
    }}
    /* FAQ section can be added here later. */
  </style>{register_script}
</head>
<body class="{body_class}">
  <main class="{main_class}">
    {body}
  </main>
</body>
</html>"""


def _render_register_page(
    errors: dict[str, str] | None = None,
    form_values: dict[str, str] | None = None,
    language_options: list[str] | None = None,
) -> str:
    errors = errors or {}
    language_options = language_options or []
    form_values = form_values or {
        "full_name": "",
        "working_languages": "",
        "phone_number": "",
        "email_address": "",
        "short_bio": "",
    }
    body = f"""
<div class="register-hero">
  <div class="register-badge" aria-hidden="true">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" role="presentation">
      <circle cx="8" cy="8" r="3.2"></circle>
      <circle cx="16.5" cy="9.5" r="2.6"></circle>
      <path d="M3.5 18.2c.9-2.5 3.2-4 5.9-4 2.6 0 4.8 1.4 5.7 3.8"></path>
      <path d="M14.2 17.3c.7-1.8 2.2-2.9 4-2.9 1.1 0 2.1.4 2.9 1.1"></path>
    </svg>
  </div>
  <div class="register-title-group">
    <h1>UAE Translator Finder</h1>
    <p class="register-subtitle">Get listed in a simple UAE directory for translators and interpreters.</p>
  </div>
</div>
<form method="post" action="/register">
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"), maxlength=30)}
  {_render_language_select(form_values["working_languages"], errors.get("working_languages"), language_options, helper_text="Choose up to 4 working languages.")}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel", maxlength=20)}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email", maxlength=50)}
  {_render_textarea("Short bio / tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Maximum 100 characters.", maxlength=100, helper_text="Maximum 100 characters.")}
  <button class="button" type="submit">Register now</button>
</form>
<div class="register-footer-note">Submissions are reviewed before publication.</div>
"""
    return _render_page("Register", body, theme="register")


def _render_success_page() -> str:
    body = """
<h1>Thank you</h1>
<div class="line">Your submission has been received.</div>
<div class="line">It is now pending review.</div>
<button class="button" type="button" onclick="window.close()">Close this window</button>
"""
    return _render_page("Submission received", body, theme="register")


def _render_admin_login_page(error: str | None = None) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    body = f"""
<h1>Admin review</h1>
<div class="line">Enter the password to view pending registrations.</div>
<form method="post" action="/admin/login">
  <div class="block">
    <label class="label" for="password">Password</label>
    <input id="password" name="password" type="password">
    {error_html}
  </div>
  <button class="button" type="submit">Open admin page</button>
</form>
"""
    return _render_page("Admin login", body, wide=True)


def _render_admin_page(
    title: str,
    active_tab: str,
    submissions: list[StoredSubmission],
    error_message: str | None = None,
) -> str:
    alert_html = f'<div class="error">{escape(error_message)}</div>' if error_message else ""
    if not submissions:
        cards = f'<div class="line">No {escape(title.lower())} submissions right now.</div>'
    else:
        cards = "".join(
            _render_submission_card(submission, show_actions=(active_tab == "pending"))
            for submission in submissions
        )
    nav = _render_admin_nav(active_tab)
    body = f"""
<h1>Admin review</h1>
{nav}
{alert_html}
<div class="line">{escape(title)} registrations</div>
{cards}
"""
    return _render_page("Admin review", body, wide=True)


def _render_submission_card(submission: StoredSubmission, show_actions: bool) -> str:
    actions_html = ""
    if show_actions:
        actions_html = f"""
  <div class="actions">
    <form method="post" action="/admin/action">
      <input type="hidden" name="submission_id" value="{submission.id}">
      <input type="hidden" name="action" value="approved">
      <button class="approve" type="submit">Approve</button>
    </form>
    <form method="post" action="/admin/action">
      <input type="hidden" name="submission_id" value="{submission.id}">
      <input type="hidden" name="action" value="rejected">
      <button class="reject" type="submit">Reject</button>
    </form>
  </div>
"""
    return f"""
<section class="card">
  <h2>{escape(submission.full_name)}</h2>
  <div class="line"><strong>Languages:</strong> {escape(submission.working_languages)}</div>
  <div class="line"><strong>Phone:</strong> {escape(submission.phone_number)}</div>
  <div class="line"><strong>Email:</strong> {escape(submission.email_address)}</div>
  <div class="line"><strong>Bio:</strong> {escape(submission.short_bio)}</div>
  <div class="line small">Status: {escape(submission.status.title())}</div>
  <div class="line small">Submitted: {escape(submission.submitted_at)}</div>
  {actions_html}
</section>
"""


def _render_admin_nav(active_tab: str) -> str:
    tabs = [
        ("Pending", "/admin", "pending"),
        ("Approved", "/admin/approved", "approved"),
        ("Rejected", "/admin/rejected", "rejected"),
        ("Directory", "/admin/directory", "directory"),
    ]
    links = []
    for label, href, key in tabs:
        if key == active_tab:
            links.append(f'<strong>{escape(label)}</strong>')
        else:
            links.append(f'<a href="{escape(href, quote=True)}">{escape(label)}</a>')
    return f'<div class="line">{" | ".join(links)}</div>'


def _render_directory_header() -> str:
    return (
        '<div class="nav-row">'
        f'{_render_admin_nav("directory")}'
        '<a class="button-inline" href="/admin/directory/new">Add interpreter</a>'
        "</div>"
    )


def _render_directory_page(people: list[PersonRecord]) -> str:
    people = sorted(people, key=lambda person: person.full_name.casefold())
    if not people:
        content = '<div class="line">No live directory records right now.</div>'
    else:
        content = _render_directory_table(people)
    body = f"""
<h1>Admin review</h1>
{_render_directory_header()}
<div class="line">Live directory</div>
<div class="line small">Records are shown in alphabetical order.</div>
{content}
"""
    return _render_page("Live directory", body, wide=True)


def _render_directory_table(people: list[PersonRecord]) -> str:
    rows = "".join(_render_directory_row(index, person) for index, person in enumerate(people, start=1))
    return f"""
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Name</th>
        <th>Languages</th>
        <th>Phone</th>
        <th>Email</th>
        <th>Bio</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>
"""


def _render_directory_row(index: int, person: PersonRecord) -> str:
    return f"""
<tr>
  <td>{index}</td>
  <td>{escape(person.full_name)}</td>
  <td>{escape(", ".join(person.languages))}</td>
  <td>{escape(person.phone or "Not provided")}</td>
  <td>{escape(person.email or "Not provided")}</td>
  <td>{escape(person.short_bio)}</td>
  <td>
    <div class="row-actions">
      <form method="get" action="/admin/directory/edit">
        <input type="hidden" name="id" value="{person.id}">
        <button class="approve" type="submit">Edit</button>
      </form>
      <form method="post" action="/admin/directory/delete">
        <input type="hidden" name="person_id" value="{person.id}">
        <button class="reject" type="submit" onclick="return confirm('Are you sure you want to delete this interpreter?')">Delete</button>
      </form>
    </div>
  </td>
</tr>
"""


def _render_directory_edit_page(
    person: PersonRecord,
    errors: dict[str, str] | None = None,
    form_values: dict[str, str] | None = None,
    language_options: list[str] | None = None,
) -> str:
    errors = errors or {}
    language_options = language_options or []
    form_values = form_values or {
        "full_name": person.full_name,
        "working_languages": ", ".join(person.languages),
        "phone_number": person.phone,
        "email_address": person.email,
        "short_bio": person.short_bio,
    }
    body = f"""
<h1>Admin review</h1>
{_render_admin_nav("directory")}
<div class="line">Edit live directory record</div>
<form method="post" action="/admin/directory/edit">
  <input type="hidden" name="person_id" value="{person.id}">
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"), maxlength=30)}
  {_render_language_select(form_values["working_languages"], errors.get("working_languages"), language_options)}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel", maxlength=20)}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email", maxlength=50)}
  {_render_textarea("Short bio/tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Max 100 characters including spaces", maxlength=100)}
  <div class="button-row">
    <button class="button-inline" type="submit">Update record</button>
    <a class="button-inline" href="/admin/directory">Back to directory</a>
  </div>
</form>
"""
    return _render_page("Edit directory record", body, wide=True)


def _render_directory_create_page(
    errors: dict[str, str] | None = None,
    form_values: dict[str, str] | None = None,
    language_options: list[str] | None = None,
) -> str:
    errors = errors or {}
    language_options = language_options or []
    form_values = form_values or {
        "full_name": "",
        "working_languages": "",
        "phone_number": "",
        "email_address": "",
        "short_bio": "",
    }
    body = f"""
<h1>Admin review</h1>
{_render_admin_nav("directory")}
<div class="line">Add interpreter</div>
<form method="post" action="/admin/directory/new">
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"), maxlength=30)}
  {_render_language_select(form_values["working_languages"], errors.get("working_languages"), language_options)}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel", maxlength=20)}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email", maxlength=50)}
  {_render_textarea("Short bio/tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Max 100 characters including spaces", maxlength=100)}
  <div class="button-row">
    <button class="button-inline" type="submit">Add interpreter</button>
    <a class="button-inline" href="/admin/directory">Back to directory</a>
  </div>
</form>
"""
    return _render_page("Add interpreter", body, wide=True)


def _render_admin_unconfigured_page() -> str:
    body = """
<h1>Admin review</h1>
<div class="line">ADMIN_PASSWORD is not configured yet.</div>
"""
    return _render_page("Admin unavailable", body, wide=True)


def _render_not_found_page() -> str:
    body = """
<h1>Page not found</h1>
<a class="button" href="/register">Back to registration</a>
"""
    return _render_page("Page not found", body)


def _render_input(
    label: str,
    name: str,
    value: str,
    error: str | None,
    input_type: str = "text",
    placeholder: str = "",
    maxlength: int | None = None,
    helper_text: str | None = None,
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    helper_html = f'<div class="helper">{escape(helper_text)}</div>' if helper_text else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <input id="{escape(name)}" name="{escape(name)}" type="{escape(input_type)}" value="{escape(value, quote=True)}" placeholder="{escape(placeholder, quote=True)}"{maxlength_attr}>
  {helper_html}
  {error_html}
</div>
"""


def _render_textarea(
    label: str,
    name: str,
    value: str,
    error: str | None,
    placeholder: str = "",
    maxlength: int | None = None,
    helper_text: str | None = None,
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    helper_html = f'<div class="helper">{escape(helper_text)}</div>' if helper_text else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <textarea id="{escape(name)}" name="{escape(name)}" placeholder="{escape(placeholder, quote=True)}"{maxlength_attr}>{escape(value)}</textarea>
  {helper_html}
  {error_html}
</div>
"""


def _render_language_select(
    selected_value: str,
    error: str | None,
    language_options: list[str],
    helper_text: str | None = None,
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    helper_html = f'<div class="helper">{escape(helper_text)}</div>' if helper_text else ""
    selected_languages = [
        language.strip() for language in selected_value.split(",") if language.strip()
    ]
    selected_language_keys = {language.casefold() for language in selected_languages}
    option_html = "".join(
        f'<option value="{escape(language, quote=True)}"{" selected" if language.casefold() in selected_language_keys else ""}>{escape(language)}</option>'
        for language in language_options
    )
    checkbox_html = "".join(
        f"""
    <label class="language-option">
      <input type="checkbox" value="{escape(language, quote=True)}" data-language-option{" checked" if language.casefold() in selected_language_keys else ""}>
      <span>{escape(language)}</span>
    </label>"""
        for language in language_options
    )
    summary_text = (
        escape(", ".join(selected_languages[:2]) + (f" +{len(selected_languages) - 2}" if len(selected_languages) > 2 else ""))
        if selected_languages
        else "Select languages"
    )
    counter_text = (
        f"{len(selected_languages)} of 4 selected"
        if selected_languages
        else "Choose up to 4 working languages."
    )
    selected_class = " has-selection" if selected_languages else ""
    return f"""
<div class="block language-select">
  <label class="label" for="working_languages">Working languages</label>
  {helper_html}
  <div class="language-widget{selected_class}" data-language-widget data-max-selection="4">
    <button class="language-toggle" type="button" data-language-toggle aria-haspopup="listbox" aria-expanded="false">
      <span class="language-summary" data-language-summary>{summary_text}</span>
      <span class="language-caret" aria-hidden="true"></span>
    </button>
    <div class="language-menu" data-language-menu>
      <div class="language-grid">
        {checkbox_html}
      </div>
      <div class="language-meta">
        <span data-language-counter>{escape(counter_text)}</span>
        <span>Maximum 4</span>
      </div>
    </div>
    <select id="working_languages" class="sr-only" name="working_languages" multiple size="8" aria-hidden="true" tabindex="-1">
      {option_html}
    </select>
  </div>
  {error_html}
</div>
"""


def _auth_cookie_value(admin_password: str) -> str:
    return sha256(admin_password.encode("utf-8")).hexdigest()


def _is_admin_authenticated(environ, admin_password: str) -> bool:
    cookies = SimpleCookie()
    cookies.load(environ.get("HTTP_COOKIE", ""))
    admin_cookie = cookies.get("admin_auth")
    return bool(admin_cookie and admin_cookie.value == _auth_cookie_value(admin_password))
