from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import escape
from typing import Any

from app.config import Settings
from app.data_loader import CsvRepository
from app.formatters import format_results_message
from app.keyboards import (
    UN_LANGUAGES,
    language_keyboard,
    other_languages_keyboard,
    results_keyboard,
)
from app.search import SearchPage, canonical_language, search_people


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

FIRST_LANGUAGE = "first_language"
SECOND_LANGUAGE = "second_language"


@dataclass
class IncomingMessage:
    chat_id: int
    text: str
    message_id: int


@dataclass
class CallbackPayload:
    callback_query_id: str
    chat_id: int
    message_id: int
    data: str


class TelegramBotClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}/"

    def _call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        request_timeout: int = 15,
    ) -> dict[str, Any]:
        data = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + method,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error for {method}: {body}")
        return body["result"]

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, request_timeout=timeout + 5)

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)

    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call("editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._call("answerCallbackQuery", payload)

    def get_me(self) -> dict[str, Any]:
        return self._call("getMe")


class BotRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TelegramBotClient(settings.telegram_bot_token)
        self.repository = CsvRepository(settings.interpreters_csv, settings.priority_rules_csv)
        self.user_state: dict[int, dict[str, Any]] = {}

    def run(self) -> None:
        while True:
            try:
                me = self.client.get_me()
                logger.info("Bot connected as @%s", me.get("username", "unknown"))
                break
            except urllib.error.URLError as exc:
                logger.warning("Telegram connection failed during startup: %s", exc)
                time.sleep(2)
            except Exception:
                logger.exception("Unexpected startup error while connecting to Telegram")
                time.sleep(2)

        offset = self._initial_offset()
        while True:
            try:
                updates = self.client.get_updates(offset=offset, timeout=10)
                for update in updates:
                    try:
                        offset = update["update_id"] + 1
                        self.process_update(update)
                    except Exception:
                        logger.exception("Failed to process a Telegram update")
            except urllib.error.URLError as exc:
                logger.warning("Network error while polling Telegram: %s", exc)
                time.sleep(1)
            except Exception:
                logger.exception("Unexpected bot error")
                time.sleep(1)

    def _initial_offset(self) -> int | None:
        while True:
            try:
                pending_updates = self.client.get_updates(timeout=0)
                if not pending_updates:
                    return None

                offset = pending_updates[-1]["update_id"] + 1
                logger.info(
                    "Skipping %s stale queued Telegram update(s) on startup",
                    len(pending_updates),
                )
                return offset
            except urllib.error.URLError as exc:
                logger.warning("Telegram update sync failed during startup: %s", exc)
                time.sleep(2)
            except Exception:
                logger.exception("Unexpected startup error while syncing Telegram updates")
                time.sleep(2)

    def process_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            callback = self._parse_callback(update["callback_query"])
            self.handle_callback(callback)
            return

        message_data = update.get("message")
        if not message_data or "text" not in message_data:
            return

        message = self._parse_message(message_data)
        self.handle_message(message)

    @staticmethod
    def _parse_message(data: dict[str, Any]) -> IncomingMessage:
        return IncomingMessage(
            chat_id=data["chat"]["id"],
            text=data.get("text", ""),
            message_id=data["message_id"],
        )

    @staticmethod
    def _parse_callback(data: dict[str, Any]) -> CallbackPayload:
        return CallbackPayload(
            callback_query_id=data["id"],
            chat_id=data["message"]["chat"]["id"],
            message_id=data["message"]["message_id"],
            data=data["data"],
        )

    def handle_message(self, message: IncomingMessage) -> None:
        text = message.text.strip()
        lowered = text.casefold()

        if lowered in {"/start", "/search"}:
            self.start_search(message.chat_id)
            return
        if lowered == "/help":
            self.send_help(message.chat_id)
            return
        if lowered == "/languages":
            self.send_languages(message.chat_id)
            return
        if lowered == "/about":
            self.send_about(message.chat_id)
            return
        if lowered == "/cancel":
            self.cancel_search(message.chat_id)
            return

        state = self.user_state.get(message.chat_id, {})
        current_step = state.get("step")

        if current_step == FIRST_LANGUAGE:
            self.client.send_message(
                message.chat_id,
                "Please choose the FIRST language using the buttons in the chat.",
                reply_markup=language_keyboard(
                    step="lang1",
                    include_other_languages=self._has_other_languages(),
                ),
            )
            return
        if current_step == SECOND_LANGUAGE:
            self.client.send_message(
                message.chat_id,
                "Please choose the SECOND language using the buttons in the chat.",
                reply_markup=language_keyboard(
                    step="lang2",
                    selected_language=state["language_one"],
                    include_other_languages=bool(state.get("available_languages")),
                ),
            )
            return

        self.client.send_message(
            message.chat_id,
            "Use /start to begin a search.",
        )

    def handle_callback(self, callback: CallbackPayload) -> None:
        self.client.answer_callback_query(callback.callback_query_id)

        if callback.data.startswith("lang1:"):
            language = callback.data.split(":", maxsplit=1)[1]
            self.handle_first_language(callback.chat_id, language)
            return

        if callback.data.startswith("lang2:"):
            language = callback.data.split(":", maxsplit=1)[1]
            self.handle_second_language(callback.chat_id, language)
            return

        if callback.data == "lang1-other":
            self.show_other_languages(callback.chat_id, step=FIRST_LANGUAGE)
            return

        if callback.data == "lang2-other":
            self.show_other_languages(callback.chat_id, step=SECOND_LANGUAGE)
            return

        if callback.data == "lang1-back":
            self.show_primary_languages(callback.chat_id, step=FIRST_LANGUAGE)
            return

        if callback.data == "lang2-back":
            self.show_primary_languages(callback.chat_id, step=SECOND_LANGUAGE)
            return

        if callback.data == "selected-language":
            self.client.answer_callback_query(
                callback.callback_query_id,
                text="This is your first selected language.",
            )
            return

        if callback.data == "page-status":
            self.client.answer_callback_query(
                callback.callback_query_id,
                text="This shows your current results page.",
            )
            return

        if callback.data.startswith("page:"):
            page = int(callback.data.split(":", maxsplit=1)[1])
            self.handle_pagination(callback.chat_id, callback.message_id, page)
            return

        if callback.data == "new-search":
            self.start_search(callback.chat_id)

    def start_search(self, chat_id: int) -> None:
        self.user_state[chat_id] = {"step": FIRST_LANGUAGE}
        info_link = escape(self.settings.public_base_url + "/register", quote=True)
        self.client.send_message(
            chat_id,
            (
                "Welcome to UAE Translator Finder.\n\n"
                "I help you find translators/interpreters by language pair.\n"
                f'To register as a translator/interpreter, <a href="{info_link}">click here</a>.\n\n'
                "<b>How it works</b>\n"
                "1. Choose the first language\n"
                "2. Choose the second language\n"
                "3. I will show matching professionals with contact details\n\n"
                "<b>Example</b>\n"
                "Arabic -> English\n\n"
                "Choose the FIRST language to begin."
            ),
            reply_markup=language_keyboard(
                step="lang1",
                include_other_languages=self._has_other_languages(),
            ),
        )

    def send_help(self, chat_id: int) -> None:
        self.client.send_message(
            chat_id,
            (
                "<b>Quick Guide</b>\n"
                "Use /start to begin a new search.\n\n"
                "<b>Search steps</b>\n"
                "1. Choose the first language\n"
                "2. Choose the second language\n\n"
                "<b>Useful commands</b>\n"
                "/languages - show all available languages\n"
                "/about - learn what this bot does\n"
                "/cancel - stop the current search"
            ),
        )

    def send_languages(self, chat_id: int) -> None:
        languages = self.repository.available_languages()
        self.client.send_message(
            chat_id,
            "Available languages:\n" + "\n".join(f"- {language}" for language in languages),
        )

    def send_about(self, chat_id: int) -> None:
        self.client.send_message(
            chat_id,
            (
                "This bot helps users find interpreters and translators.\n\n"
                "Current MVP filters:\n"
                "- language pair\n\n"
                "Search direction is ignored in this MVP, so English + Arabic is the same as Arabic + English."
            ),
        )

    def cancel_search(self, chat_id: int) -> None:
        self.user_state.pop(chat_id, None)
        self.client.send_message(
            chat_id,
            "Search cancelled. Use /start whenever you want to begin again.",
            reply_markup={"remove_keyboard": True},
        )

    def handle_first_language(self, chat_id: int, raw_language: str) -> None:
        state = self.user_state[chat_id]
        try:
            language = self._validate_language_input(
                raw_language,
                allow_un_language=True,
            )
        except ValueError:
            self.client.send_message(
                chat_id,
                "Please choose the FIRST language using the buttons in the chat.",
                reply_markup=language_keyboard(
                    step="lang1",
                    include_other_languages=self._has_other_languages(),
                ),
            )
            return

        state["language_one"] = language
        state["step"] = SECOND_LANGUAGE
        state["available_languages"] = self.repository.available_languages(
            required_language=language,
            exclude_language=language,
        )
        self.client.send_message(
            chat_id,
            (
                "Choose the SECOND language using the buttons in the chat.\n\n"
                f"Your FIRST selected language is {language}.\n"
                "Use Other Languages to see additional available options."
            ),
            reply_markup=language_keyboard(
                step="lang2",
                selected_language=language,
                include_other_languages=bool(state["available_languages"]),
            ),
        )

    def handle_second_language(self, chat_id: int, raw_language: str) -> None:
        state = self.user_state[chat_id]
        try:
            language = self._validate_language_input(
                raw_language,
                required_language=state["language_one"],
                exclude_language=state["language_one"],
                other_language=state["language_one"],
                allow_un_language=True,
            )
        except ValueError:
            self.client.send_message(
                chat_id,
                "Please choose the SECOND language using the buttons in the chat.",
                reply_markup=language_keyboard(
                    step="lang2",
                    selected_language=state["language_one"],
                    include_other_languages=bool(state.get("available_languages")),
                ),
            )
            return

        state["language_two"] = language
        search_page = self.run_search(chat_id, page=1)
        self.send_results(chat_id, search_page)

    def handle_pagination(self, chat_id: int, message_id: int, page: int) -> None:
        if chat_id not in self.user_state or "language_one" not in self.user_state[chat_id]:
            self.client.send_message(chat_id, "Your last search has expired. Use /start to search again.")
            return

        search_page = self.run_search(chat_id, page=page)
        self.client.edit_message(
            chat_id,
            message_id,
            format_results_message(search_page),
            reply_markup=results_keyboard(search_page.page, search_page.total_pages),
        )

    def run_search(self, chat_id: int, page: int) -> SearchPage:
        state = self.user_state[chat_id]
        return search_people(
            people=self.repository.load_people(),
            rules=self.repository.load_priority_rules(),
            service_type=None,
            language_one=state["language_one"],
            language_two=state["language_two"],
            page=page,
            page_size=self.settings.results_per_page,
        )

    def send_results(self, chat_id: int, search_page: SearchPage) -> None:
        self.client.send_message(
            chat_id,
            format_results_message(search_page),
            reply_markup=results_keyboard(search_page.page, search_page.total_pages),
        )
        self.client.send_message(
            chat_id,
            "Start another search any time with /start.",
            reply_markup={"remove_keyboard": True},
        )

    def show_primary_languages(self, chat_id: int, step: str) -> None:
        state = self.user_state[chat_id]
        if step == FIRST_LANGUAGE:
            self.client.send_message(
                chat_id,
                "Choose the FIRST language.",
                reply_markup=language_keyboard(
                    step="lang1",
                    include_other_languages=self._has_other_languages(),
                ),
            )
            return

        self.client.send_message(
            chat_id,
            "Choose the SECOND language.",
            reply_markup=language_keyboard(
                step="lang2",
                selected_language=state["language_one"],
                include_other_languages=bool(state.get("available_languages")),
            ),
        )

    def show_other_languages(self, chat_id: int, step: str) -> None:
        state = self.user_state[chat_id]
        if step == FIRST_LANGUAGE:
            other_languages = self._other_languages()
            if not other_languages:
                self.client.send_message(chat_id, "No other languages are available right now.")
                return
            self.client.send_message(
                chat_id,
                "Other available first-language options:",
                reply_markup=other_languages_keyboard(other_languages, step="lang1"),
            )
            return

        other_languages = self._other_languages(
            required_language=state["language_one"],
            exclude_language=state["language_one"],
        )
        if not other_languages:
            self.client.send_message(chat_id, "No other second-language options are available right now.")
            return
        self.client.send_message(
            chat_id,
            "Other available second-language options:",
            reply_markup=other_languages_keyboard(other_languages, step="lang2"),
        )

    def _other_languages(
        self,
        service_type: str | None = None,
        required_language: str | None = None,
        exclude_language: str | None = None,
    ) -> list[str]:
        available_languages = self.repository.available_languages(
            service_type=service_type,
            required_language=required_language,
            exclude_language=exclude_language,
        )
        return [
            language for language in available_languages if language not in UN_LANGUAGES
        ]

    def _has_other_languages(
        self,
        service_type: str | None = None,
        required_language: str | None = None,
        exclude_language: str | None = None,
    ) -> bool:
        return bool(
            self._other_languages(
                service_type=service_type,
                required_language=required_language,
                exclude_language=exclude_language,
            )
        )

    def _validate_language_input(
        self,
        raw_value: str,
        service_type: str | None = None,
        required_language: str | None = None,
        exclude_language: str | None = None,
        other_language: str | None = None,
        allow_un_language: bool = False,
    ) -> str:
        language = canonical_language(raw_value)
        if other_language and language.casefold() == other_language.casefold():
            raise ValueError("Please choose two different languages.")
        if allow_un_language and language in UN_LANGUAGES:
            return language
        if not self.repository.has_language(
            language,
            service_type=service_type,
            required_language=required_language,
            exclude_language=exclude_language,
        ):
            raise ValueError(
                f"'{language}' is not in the current language list. Use /languages to see the available options."
            )
        return language
