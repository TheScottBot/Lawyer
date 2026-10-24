"""Small helpers shared by several features."""

import logging

import discord
from discord import app_commands

log = logging.getLogger("lawyer")

NO_PINGS = discord.AllowedMentions.none()

EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_LIMIT = 1024
EMBED_TOTAL_LIMIT = 6000


def choices(pairs: list[tuple[str, str]]) -> list[app_commands.Choice[str]]:
    """Autocomplete options from (shown, value) pairs, within Discord's limits (25 of them, 100 characters each)."""
    return [app_commands.Choice(name=name[:100], value=value[:100]) for name, value in pairs[:25]]


def clip(text: str, limit: int, more: str = "…") -> str:
    """Text cut to fit `limit` characters, at a paragraph or sentence if one's near the end, with `more` after."""
    if len(text) <= limit:
        return text
    room = limit - len(more)
    cut = text[:room]
    for mark in ("\n\n", ". ", "\n", " "):
        at = cut.rfind(mark)
        if at > room * 0.6:
            cut = cut[:at + (1 if mark == ". " else 0)]
            break
    return cut.rstrip() + more
