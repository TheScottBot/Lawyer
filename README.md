# Lawyer
A rules lawyer for our D&D server

A Discord bot that looks rules up in our own rulebooks, so nobody has to dig through a PDF mid-fight.
`/rule poison` gives the Poisoned condition, word for word from the book, with the page it's on;
`/rule poison damage` gives the poison damage type. Commands work as slash commands (`/rule`) and typed
(`!rule`; the prefix is `COMMAND_PREFIX` in `.env`).

It reads only from books we've built it (see [docs/SETUP.md](docs/SETUP.md)): no AI, no internet, nothing made up.
Every answer says which book and page it came from. Right now that's the 2014 Player's Handbook, Monster Manual,
Xanathar's Guide to Everything, Tasha's Cauldron of Everything and Monsters of the Multiverse; the Dungeon Master's
Guide is next.

To run it on the homelab, see [deploy/INSTALL.md](deploy/INSTALL.md).

## Commands

The [full command reference](docs/COMMANDS.md) has every option and example.

### 📜 Rules
- `/rule <what>`: look up a rule, condition, spell, feat, class feature or anything else in the books. Type it
  however you'd say it (`grappled`, `aoo`, `fighter extra attack`, `posion` works too). Menus under the answer show
  the other matches and the sections under it.
- `/stats <monster>`: a monster's stat block, ready to run (AC, HP, abilities, actions, legendary actions).
- `/class <name> [subclass]`: a class's features all together, by level; with a subclass, both in one list.
- `/race <name>`: a race's traits all together, with its subraces.

### 🔧 Utilities
- `/help [command]`: every command, or one in detail.
- `/settings`: this server's settings, like `prefer_newer` (the newest book's rules first).

## Quick start

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env              # then add DISCORD_TOKEN and GUILD_IDS
.venv/Scripts/python -m lawyer.tools.rules_build phb   # needs books/<the PHB's PDF>; see docs/SETUP.md
.venv/Scripts/python bot.py
```

On Linux it's `.venv/bin/python`. The bot needs the **Message Content Intent** for typed commands, and to be invited
with the `bot` and `applications.commands` scopes.

## For whoever changes it

[ARCHITECTURE.md](ARCHITECTURE.md) is how it fits together and the rules for changing it; [AGENTS.md](AGENTS.md) is
the short version for AI assistants. Run the tests with `python -m pytest`.

The books' text is never committed: `books/` (the PDFs) and `rules/` (what's built from them) are in `.gitignore`.
