from __future__ import annotations

from app.bot import BotRunner
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    runner = BotRunner(settings)
    runner.run()


if __name__ == "__main__":
    main()
