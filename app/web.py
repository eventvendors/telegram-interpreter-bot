from __future__ import annotations

from html import escape
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app.config import Settings
from app.submissions import RegistrationSubmission, SubmissionRepository


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

        return _html_response(start_response, 404, _render_not_found_page())

    return application


def serve_web_app(settings: Settings) -> None:
    application = create_web_app(settings)
    with make_server(settings.web_host, settings.web_port, application) as server:
        server.serve_forever()


def _parse_submission(environ) -> tuple[dict[str, str], dict[str, str]]:
    content_length = int(environ.get("CONTENT_LENGTH") or "0")
    raw_body = environ["wsgi.input"].read(content_length).decode("utf-8")
    payload = parse_qs(raw_body, keep_blank_values=True)

    values = {
        "full_name": payload.get("full_name", [""])[0].strip(),
        "working_languages": payload.get("working_languages", [""])[0].strip(),
        "phone_number": payload.get("phone_number", [""])[0].strip(),
        "email_address": payload.get("email_address", [""])[0].strip(),
        "short_bio": payload.get("short_bio", [""])[0].strip(),
    }

    errors: dict[str, str] = {}
    for field_name, field_value in values.items():
        if not field_value:
            errors[field_name] = "This field is required."

    if values["short_bio"] and len(values["short_bio"]) > 90:
        errors["short_bio"] = "Maximum 90 characters including spaces."

    return values, errors


def _html_response(start_response, status_code: int, html: str):
    status_map = {200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found"}
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
      width: min(100%, 520px);
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
    p, .line {{
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
<a class="button" href="/info">Back to info page</a>
"""
    return _render_page("Submission received", body)


def _render_not_found_page() -> str:
    body = """
<h1>Page not found</h1>
<a class="button" href="/info">Back to info page</a>
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
