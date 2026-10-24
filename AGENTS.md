# Lawyer: notes for AI coding assistants

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing code. It covers the structure, the data and the rules; this
file is only the working rules. (CLAUDE.md imports this file, so this is the one copy.)

- **Never commit or push.** Make and verify changes; the maintainer commits.
- **Run the tests** (`python -m pytest`, ~2 s) before and after changes, and add tests for new behaviour.
- **The rulebooks are the maintainer's own copies, never the repo's.** Nothing from them is committed: not the PDFs
  (`books/`), not what's built from them (`rules/`), not quotes in tests, docs or commit messages. Tests use the
  made-up `BOOK` in `tests/conftest.py`. `lawyer/lib/aliases.json` and `lawyer/lib/books.json` hold names and
  settings only.
- **Keep /help, the README and docs/COMMANDS.md accurate** after every change. Every new or changed command needs:
  a one-line `description=` (≤ 100 characters), its feature's `HELP_CATEGORY` (one of `help.CATEGORIES`), a
  docstring written for the people using it (its `/help` page), `@app_commands.describe(...)` for each option, a row
  in `docs/COMMANDS.md`, a line in the README, and a line in ARCHITECTURE.md's layout for a new file.
  `tests/test_registration.py` checks these; add new commands to its `SLASH_COMMANDS`.
- **Adding a book** is a `lawyer/lib/books.json` entry (its file, source, edition, contents page and which chapters
  are which category), then `python -m lawyer.tools.rules_build <id>`, then a look at what came out (see
  ARCHITECTURE.md §5). Fix the parser for the layout, not the output by hand: `rules/` is rebuilt from scratch.
- **Entry ids are permanent** once people use them (`phb.condition.poisoned`): aliases point at them. If a parser
  change renames ids, update `lawyer/lib/aliases.json` (the build lists any alias whose id no longer exists).
- **Don't run the bot with the live token** from `.env`. Use `.env.dev` (a separate dev bot) or the tests.
- On the maintainer's Windows machine, `python` may resolve to the Microsoft Store alias; use
  `.venv\Scripts\python.exe` (`py` works to make the venv).
