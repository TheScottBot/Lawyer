"""Settings from .env (or .env.dev with --dev). Relative paths are resolved from the repo root."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Run with --dev (e.g. "python bot.py --dev") to use the dev bot's settings in .env.dev.
DEV = "--dev" in sys.argv
ENV_FILE = ".env.dev" if DEV else ".env"
if not os.getenv("LAWYER_NO_DOTENV"):  # The tests set this so they never read your real .env.
    load_dotenv(BASE_DIR / ENV_FILE)


def parse_ids(*env_names: str) -> list[int]:
    """Comma-separated IDs from the first of these env vars that is set. Skips (and warns about) typos."""
    raw = next((os.getenv(name) for name in env_names if os.getenv(name)), "")
    ids = []
    for item in raw.replace(" ", "").split(","):
        if item.isdigit():
            ids.append(int(item))
        elif item:
            logging.getLogger("lawyer").warning("Ignoring %r in %s: server IDs are numbers only.", item, env_names[0])
    return ids


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# Comma-separated server IDs to register slash commands to (GUILD_ID also accepted).
GUILD_IDS = parse_ids("GUILD_IDS", "GUILD_ID")

# The built rulebooks: one JSON file per book, written by python -m lawyer.tools.rules_build <book>.
RULES_DIR = BASE_DIR / os.getenv("RULES_DIR", "rules")
# Each server's settings (/settings), in one SQLite file.
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "lawyer.db"))
# Rolling log file. Rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/lawyer-dev.log" if DEV else "logs/lawyer.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 1_000_000))
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", 5))
