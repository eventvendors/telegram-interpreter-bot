from __future__ import annotations

from hashlib import sha256
from html import escape
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app.config import Settings
from app.submissions import RegistrationSubmission, StoredSubmission, SubmissionRepository


def create_web_app(settings: Settings):
    repository = SubmissionRepository(settings.submissions_db)

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")

        if method == "GET" and path in {"/", "/info", "/register"}:
            return _html_response(start_response, 200, _render_register_page())
        if method == "POST" and path == "/register":
            submission, errors = _parse_submission(environ)
            if errors:
                return _html_response(
                    start_response,
                    400,
                    _render_register_page(errors=errors, form_values=submission),
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
                return _html_response(start_response, 200, _render_admin_page(pending))
            return _html_response(start_response, 200, _render_admin_login_page())
        if method == "POST" and path == "/admin/login":
            if not settings.admin_password:
                return _html_response(start_response, 503, _render_admin_unconfigured_page())
            payload = _parse_form_body(environ)
            if payload.get("password", "").strip() == settings.admin_password:
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
            action = payload.get("action", "").strip().lower()
            try:
                submission_id = int(payload.get("submission_id", "0"))
            except ValueError:
                submission_id = 0
            if submission_id > 0 and action in {"approved", "rejected"}:
                repository.update_status(submission_id, action)
            return _redirect(start_response, "/admin")

        return _html_response(start_response, 404, _render_not_found_page())

    return application


def serve_web_app(settings: Settings) -> None:
    application = create_web_app(settings)
    with make_server(settings.web_host, settings.web_port, application) as server:
        server.serve_forever()


def _parse_submission(environ) -> tuple[dict[str, str], dict[str, str]]:
    payload = _parse_form_body(environ)

    values = {
        "full_name": payload.get("full_name", "").strip(),
        "working_languages": payload.get("working_languages", "").strip(),
        "phone_number": payload.get("phone_number", "").strip(),
        "email_address": payload.get("email_address", "").strip(),
        "short_bio": payload.get("short_bio", "").strip(),
    }

    errors: dict[str, str] = {}
    for field_name, field_value in values.items():
        if not field_value:
            errors[field_name] = "This field is required."

    if values["short_bio"] and len(values["short_bio"]) > 90:
        errors["short_bio"] = "Maximum 90 characters including spaces."

    return values, errors


def _parse_form_body(environ) -> dict[str, str]:
    content_length = int(environ.get("CONTENT_LENGTH") or "0")
    raw_body = environ["wsgi.input"].read(content_length).decode("utf-8")
    payload = parse_qs(raw_body, keep_blank_values=True)
    return {key: values[0] for key, values in payload.items()}


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


def _render_page(title: str, body: str) -> str:
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
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    main {{
      width: min(100%, 620px);
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
    input, textarea {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid #31465f;
      background: #081321;
      color: #f3f7fb;
      font: inherit;
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
) -> str:
    errors = errors or {}
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
  {_render_input("Full name", "full_name", form_values["full_name"], errors.get("full_name"))}
  {_render_input("Working languages", "working_languages", form_values["working_languages"], errors.get("working_languages"))}
  {_render_input("Phone number", "phone_number", form_values["phone_number"], errors.get("phone_number"), input_type="tel")}
  {_render_input("Email address", "email_address", form_values["email_address"], errors.get("email_address"), input_type="email")}
  {_render_textarea("Short bio/tag line", "short_bio", form_values["short_bio"], errors.get("short_bio"), placeholder="Max 90 characters including spaces")}
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
    return _render_page("Admin login", body)


def _render_admin_page(pending_submissions: list[StoredSubmission]) -> str:
    if not pending_submissions:
        cards = '<div class="line">No pending submissions right now.</div>'
    else:
        cards = "".join(_render_submission_card(submission) for submission in pending_submissions)
    body = f"""
<h1>Admin review</h1>
<div class="line">Pending registrations</div>
{cards}
"""
    return _render_page("Admin review", body)


def _render_submission_card(submission: StoredSubmission) -> str:
    return f"""
<section class="card">
  <h2>{escape(submission.full_name)}</h2>
  <div class="line"><strong>Languages:</strong> {escape(submission.working_languages)}</div>
  <div class="line"><strong>Phone:</strong> {escape(submission.phone_number)}</div>
  <div class="line"><strong>Email:</strong> {escape(submission.email_address)}</div>
  <div class="line"><strong>Bio:</strong> {escape(submission.short_bio)}</div>
  <div class="line small">Submitted: {escape(submission.submitted_at)}</div>
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
</section>
"""


def _render_admin_unconfigured_page() -> str:
    body = """
<h1>Admin review</h1>
<div class="line">ADMIN_PASSWORD is not configured yet.</div>
"""
    return _render_page("Admin unavailable", body)


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
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <input id="{escape(name)}" name="{escape(name)}" type="{escape(input_type)}" value="{escape(value, quote=True)}" placeholder="{escape(placeholder, quote=True)}">
  {error_html}
</div>
"""


def _render_textarea(
    label: str,
    name: str,
    value: str,
    error: str | None,
    placeholder: str = "",
) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    return f"""
<div class="block">
  <label class="label" for="{escape(name)}">{escape(label)}</label>
  <textarea id="{escape(name)}" name="{escape(name)}" placeholder="{escape(placeholder, quote=True)}">{escape(value)}</textarea>
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
