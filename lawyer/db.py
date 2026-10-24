"""The bot's one SQLite file: each server's settings. Opened once by init() (bot startup, or ":memory:" in tests).

Like ktdi's, every row records the server it's for, and upgrades are additive: a setting is a column with a default
that keeps the old behaviour, added in _upgrade() if an older file doesn't have it.
"""

import sqlite3

conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    prefer_newer INTEGER NOT NULL DEFAULT 0
);
"""


def init(path: str) -> None:
    global conn
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _upgrade()
    conn.commit()


def _upgrade() -> None:
    """Columns added since a table was made (none yet). Additive only: never drop or rewrite."""


def prefer_newer(guild_id: int | None) -> bool:
    """Whether this server wants the newest book's version of a rule first (Xanathar's before the PHB)."""
    if guild_id is None or conn is None:
        return False
    row = conn.execute("SELECT prefer_newer FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    return bool(row and row["prefer_newer"])


def set_prefer_newer(guild_id: int, on: bool) -> None:
    conn.execute("INSERT INTO guild_settings (guild_id, prefer_newer) VALUES (?, ?) "
                 "ON CONFLICT(guild_id) DO UPDATE SET prefer_newer = excluded.prefer_newer", (guild_id, int(on)))
    conn.commit()
