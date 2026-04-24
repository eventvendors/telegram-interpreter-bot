from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    interpreters_csv: Path
    priority_rules_csv: Path
    submissions_db: Path
    public_base_url: str
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    results_per_page: int = 5


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is missing. Add it to your .env file.")

    interpreters_csv = Path(
        os.getenv("INTERPRETERS_CSV", BASE_DIR / "data" / "interpreters.csv")
    )
    priority_rules_csv = Path(
        os.getenv("PRIORITY_RULES_CSV", BASE_DIR / "data" / "priority_rules.csv")
    )
    submissions_db = Path(
        os.getenv("SUBMISSIONS_DB", BASE_DIR / "storage" / "submissions.db")
    )
    web_port = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))
    railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    default_public_base_url = (
        f"https://{railway_public_domain}" if railway_public_domain else f"http://localhost:{web_port}"
    )
    public_base_url = os.getenv("PUBLIC_BASE_URL", default_public_base_url).strip().rstrip("/")

    return Settings(
        telegram_bot_token=token,
        interpreters_csv=interpreters_csv,
        priority_rules_csv=priority_rules_csv,
        submissions_db=submissions_db,
        public_base_url=public_base_url,
        web_port=web_port,
    )
