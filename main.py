from __future__ import annotations

import threading

from app.bot import BotRunner
from app.config import get_settings
from app.web import serve_web_app


def main() -> None:
    settings = get_settings()
    runner = BotRunner(settings)
    bot_thread = threading.Thread(target=runner.run, daemon=True)
    bot_thread.start()
    serve_web_app(settings)


if __name__ == "__main__":
    main()
