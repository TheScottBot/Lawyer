# Setting up and running

The [README](../README.md) has the quick start. This is the rest: building the rulebooks, adding a book, running a
second bot for testing, and deploying.

## The rulebooks

The bot never reads a PDF. Each book is built once, on any machine with the PDF, into `rules/<book>.json`, and the
bot loads every file in `rules/` when it starts. Neither `books/` nor `rules/` is ever committed: they're our copies
of the books, not the repo's.

1. Put the PDF in `books/` (the file name `lawyer/lib/books.json` gives it).
2. `pip install -e ".[build]"` (pypdf, only needed for building).
3. `python -m lawyer.tools.rules_build phb`. It takes about 20 seconds and says how many entries it found of each
   kind, and whether any of `lawyer/lib/aliases.json`'s ids are gone.
4. Restart the bot.

`--pdf path/to/file.pdf` builds from a PDF somewhere else.

Each entry records where it came from:

```json
{
  "id": "phb.condition.poisoned",
  "edition": "5e-2014",
  "source": "PHB",
  "book": "Player's Handbook",
  "page": 292,
  "title": "Poisoned",
  "category": "condition",
  "aliases": ["poison", "poison condition"],
  "path": ["Appendix A: Conditions"],
  "sections": [],
  "text": "• A poisoned creature has disadvantage on attack rolls and ability checks."
}
```

`page` is the book's printed page, worked out from its contents page (the scans have dropped blank and art pages, so
the PDF's own page numbers are off). `aliases` from `lawyer/lib/aliases.json` are added when the bot loads, so adding
one is an edit and a restart, no rebuild.

### Adding a book

1. Add it to `lawyer/lib/books.json`: an id (`mm`), `source` (as players cite it: `MM`), `title`, `edition`
   (`5e-2014`), `file`, `contents_pages` (the PDF page numbers of its contents, counting the first as 1),
   `default_category`, and `categories`: each chapter or section title, as the book prints it, and the category its
   entries get (`"skip"` leaves it out: prefaces, indexes).
2. Build it, then look at what came out: the top-level entries and their pages, a few random entries, and some
   lookups you know the answer to. The parser was written against the Player's Handbook scan; a book laid out
   differently (the Monster Manual's stat blocks) may need the parser taught its layout. See ARCHITECTURE.md §5.
3. Add any aliases people will use to `lawyer/lib/aliases.json`.

Give every book its `published` date (YYYY-MM-DD): `/settings prefer_newer` uses it to put the newest book's rules
first.

A book whose scan has generic fonts and headings in capitals (Xanathar's, Tasha's) is `"layout": "caps"`, with
`page_offset` and `levels`: heading sizes to levels, biggest first (look at a few pages' heading sizes; see
Xanathar's entry). The PDF's bookmarks are its outline, as deep as they go. If small feature headings are missed,
lower `smallest_heading` (a fraction of the text's size; 0.82 unless set); if notes in the art are read as
headings, list them in `ignore_headings` (see Tasha's entry).

A bestiary (lots of stat blocks, PDF bookmarks for its monsters) is built differently: give it `"layout":
"monsters"`, `page_offset` (PDF pages before the book's page 1) and `statblock_index_pages` (its Index of Stat
Blocks, 0 = the PDF's first page; `[]` if it has none and bookmarks every creature, like Monsters of the
Multiverse). See the Monster Manual's entry. The build says how many stat blocks it found and
which index names it couldn't place.

## A second bot for testing

Make a second application in the Discord Developer Portal, put its token in `.env.dev`, and run `python bot.py
--dev`. Never run a copy with the live token while the real one is running: both get every event and fight over the
slash commands.

## Deploying

[deploy/INSTALL.md](../deploy/INSTALL.md): `deploy/deploy.sh` installs it in the homelab container in phases, like
CritDeckPy's (a checkout at `/opt/Lawyer`, a `lawyer` user and systemd service, a hashed dependency lock). Build the
books here and copy `rules/*.json` over; the PDFs stay on this PC.

Logs go to `logs/lawyer.log` (rotating, 1 MB × 5) and the journal; each server's settings to `data/lawyer.db`.
