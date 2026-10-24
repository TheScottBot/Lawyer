"""Loading every feature onto a real bot registers the expected commands, /help fits Discord's limits, and the docs
mention every command."""

import asyncio
import re
from pathlib import Path

import pytest

from lawyer import config
from lawyer.bot import LawyerBot, describe_options
from lawyer.features import help as help_feature
from tests.fakes import Ctx, User, run

ROOT = Path(__file__).resolve().parent.parent
SLASH_COMMANDS = ["class", "help", "race", "rule", "settings", "stats"]


@pytest.fixture
def loaded_bot():
    bot = LawyerBot()
    asyncio.run(bot.load_features())
    return bot


def test_slash_commands(loaded_bot):
    assert sorted(c.name for c in loaded_bot.tree.get_commands()) == SLASH_COMMANDS
    assert sorted(c.name for c in loaded_bot.commands) == SLASH_COMMANDS


def test_descriptions_fit(loaded_bot):
    for command in loaded_bot.tree.get_commands():
        assert 0 < len(command.description) <= 100, command.name
        for option in getattr(command, "parameters", []):
            assert 0 < len(option.description) <= 100, f"{command.name} {option.name}"


def test_every_command_has_a_section_and_a_page(loaded_bot):
    for command in loaded_bot.commands:
        assert help_feature.category_of(command) in help_feature.CATEGORIES, command.name
        page = (command.help or "").strip()
        assert page and page != command.description, f"/{command.name} needs a docstring for its /help page"


def test_help_pages_fit(loaded_bot):
    pages = [help_feature.front_page(loaded_bot)] + [help_feature.command_page(c) for c in loaded_bot.commands]
    for embed in pages:
        assert len(embed) <= 6000 and all(len(f.value) <= 1024 for f in embed.fields), embed.title


def test_help_command(loaded_bot):
    ctx = Ctx(User(1, "scott"), bot=loaded_bot)
    run(help_feature.help_command.callback(ctx, "rule"))
    assert ctx.last.embed.title == "/rule" and ctx.last.private
    run(help_feature.help_command.callback(ctx, "nope"))
    assert "There's no `nope` command" in ctx.last.content


def test_docs_mention_every_command(loaded_bot):
    commands_md = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for command in loaded_bot.commands:
        assert f"/{command.name}" in commands_md, f"docs/COMMANDS.md doesn't mention /{command.name}"
        assert f"/{command.name}" in readme, f"README.md doesn't mention /{command.name}"


def test_architecture_mentions_every_file():
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for file in sorted((ROOT / "lawyer").rglob("*.py")):
        if file.name != "__init__.py":
            assert file.name in architecture, f"ARCHITECTURE.md's layout doesn't mention {file.name}"


def test_env_example_has_every_setting():
    settings = set(re.findall(r'os\.getenv\("([A-Z_]+)"', (ROOT / "lawyer" / "config.py").read_text(encoding="utf-8")))
    settings |= set(re.findall(r'parse_ids\("([A-Z_]+)"', (ROOT / "lawyer" / "config.py").read_text(encoding="utf-8")))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    missing = {s for s in settings - {"LAWYER_NO_DOTENV", "GUILD_ID"} if s not in example}
    assert not missing, f".env.example is missing {missing}"


def test_describe_options():
    assert describe_options([{"name": "what", "value": "poison"}, {"name": "private", "value": True}]) == \
        "what=poison private=True"


def test_books_and_rules_are_never_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert "books/" in ignored and "rules/" in ignored and ".env" in ignored
    assert config.RULES_DIR == ROOT / "rules"
