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

    if values["full_name"] and len(values["full_name"]) > 40:
        errors["full_name"] = "Maximum 40 characters."

    if values["working_languages"]:
        allowed_languages = {language.casefold() for language in language_options}
        selected_languages = [language.strip() for language in values["working_languages"].split(",")]
        if not selected_languages or any(not language for language in selected_languages):
            errors["working_languages"] = "Select at least one language."
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

    if values["short_bio"] and len(values["short_bio"]) > 90:
        errors["short_bio"] = "Maximum 90 characters including spaces."

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


def _render_page(title: str, body: str, wide: bool = False) -> str:
    main_width = "1200px" if wide else "620px"
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
      background: #07111f;
      color: #f3f7fb;
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 24px;
    }}
    main {{
      width: min(100%, {main_width});
      background: #0d1b2e;
      border: 1px solid #22344b;
      border-radius: 14px;
      padding: 28px 22px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28);
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
    .small {{
      color: #b8c7d8;
      font-size: 13px;
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
  </style>
</head>
<body>
  <main>
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
<h1>UAE Translator Finder</h1>
<div class="line">This bot helps users quickly find translators and interpreters by language pair.</div>
<div class="line">To be included in the directory, submit the following details:</div>
<div class="line small">Your submission will be reviewed before approval.</div>
<form method="post" action="/register">
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"), maxlength=40)}
  {_render_language_select(form_values["working_languages"], errors.get("working_languages"), language_options)}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel", maxlength=20)}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email", maxlength=50)}
  {_render_textarea("Short bio/tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Max 90 characters including spaces", maxlength=90)}
  <button class="button" type="submit">Register now</button>
</form>
"""
    return _render_page("Register", body)


def _render_success_page() -> str:
    body = """
<h1>Thank you</h1>
<div class="line">Your submission has been received.</div>
<div class="line">It is now pending review.</div>
<a class="button" href="/register">Back to registration</a>
"""
    return _render_page("Submission received", body)


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


def _render_directory_page(people: list[PersonRecord]) -> str:
    people = sorted(people, key=lambda person: person.full_name.casefold())
    if not people:
        content = '<div class="line">No live directory records right now.</div>'
    else:
        content = _render_directory_table(people)
    body = f"""
<h1>Admin review</h1>
{_render_admin_nav("directory")}
<div class="line">Live directory</div>
<div class="line small">Records are shown in alphabetical order.</div>
{content}
"""
    return _render_page("Live directory", body, wide=True)


def _render_directory_table(people: list[PersonRecord]) -> str:
    rows = "".join(_render_directory_row(person) for person in people)
    return f"""
<div class="table-wrap">
  <table>
    <thead>
      <tr>
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


def _render_directory_row(person: PersonRecord) -> str:
    return f"""
<tr>
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
        <button class="reject" type="submit">Delete</button>
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
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"), maxlength=40)}
  {_render_language_select(form_values["working_languages"], errors.get("working_languages"), language_options)}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel", maxlength=20)}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email", maxlength=50)}
  {_render_textarea("Short bio/tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Max 90 characters including spaces", maxlength=90)}
  <button class="button" type="submit">Update record</button>
</form>
<a class="button" href="/admin/directory">Back to directory</a>
"""
    return _render_page("Edit directory record", body, wide=True)


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
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <input id="{escape(name)}" name="{escape(name)}" type="{escape(input_type)}" value="{escape(value, quote=True)}" placeholder="{escape(placeholder, quote=True)}"{maxlength_attr}>
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
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    maxlength_attr = f' maxlength="{maxlength}"' if maxlength is not None else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <textarea id="{escape(name)}" name="{escape(name)}" placeholder="{escape(placeholder, quote=True)}"{maxlength_attr}>{escape(value)}</textarea>
  {error_html}
</div>
"""


def _render_language_select(
    selected_value: str,
    error: str | None,
    language_options: list[str],
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    selected_languages = {
        language.strip().casefold() for language in selected_value.split(",") if language.strip()
    }
    option_html = "".join(
        f'<option value="{escape(language, quote=True)}"{" selected" if language.casefold() in selected_languages else ""}>{escape(language)}</option>'
        for language in language_options
    )
    return f"""
<div class="block">
  <label class="label" for="working_languages">Working languages</label>
  <div class="line small">Choose from the approved dropdown only.</div>
  <select id="working_languages" name="working_languages" multiple size="8">
    {option_html}
  </select>
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
