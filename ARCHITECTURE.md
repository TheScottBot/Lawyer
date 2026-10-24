# Lawyer architecture and design

How the bot is put together, why, and the rules to follow when changing it. The [README](README.md) is the short
tour and [docs/COMMANDS.md](docs/COMMANDS.md) what every command does; this covers how they work. It's laid out like
[ktdi](https://github.com/TheScottBot/ktdi), and follows its conventions.

**Before changing anything:** read [Rules for changes](#rules-for-changes) and run the tests (`python -m pytest`).

---

## 1. What it is

A Discord bot for our D&D server that answers "what does the book say about…?" from our own rulebooks: `/rule
poison`. It's a lookup, not a chatbot: every answer is the book's own text for one heading, with where it came from
(book, edition, page, chapter and section), so a ruling can be checked. No AI, no outside services, nothing made up.

## 2. Two halves

| Half | When | Reads | Writes |
|---|---|---|---|
| **Build** (`lawyer/tools/rules_build.py`) | Once per book, by hand | `books/<the PDF>`, `lawyer/lib/books.json` | `rules/<book>.json` |
| **Bot** (`lawyer/`) | Always running | `rules/*.json`, `lawyer/lib/aliases.json` | Logs only |

They're split so the bot stays small and fast (no PDF library, no parsing at startup: it loads ~2,000 entries a book
in a fraction of a second) and so the slow, fiddly part can be rerun and checked on its own. `books/` and `rules/` are
never committed (§6).

## 3. Layout

```
bot.py                 launcher
lawyer/
├── __main__.py        python -m lawyer: the same as bot.py
├── bot.py             LawyerBot: startup, loading features, syncing slash commands, command logging, errors
├── config.py          every setting from .env, in one place
├── db.py              SQLite (lawyer.db): each server's settings (guild_settings); additive upgrades only
├── common.py          helpers shared by features (NO_PINGS, choices, clip, Discord's embed limits)
├── features/          one discord.py extension per feature (FEATURES lists them)
│   ├── rule.py        /rule: the lookup, its embed, and the menus (other matches, sections, up). Loads the
│   │                  rulebook every feature reads (rule.rulebook)
│   ├── stats.py       /stats: a stat block's parsed stats as embeds, paged when big
│   ├── character.py   /class and /race: a class's features by level (and its subclasses), a race's traits
│   ├── settings.py    /settings: show them; prefer_newer (Manage Server)
│   └── help.py        /help: commands by section, and one command's page (its docstring)
├── lib/
│   ├── rulebook.py    Rulebook: loads rules/*.json, search() and autocomplete(); Entry, Hit
│   ├── fuzzy.py       loose word matching (words, typos, plurals), copied from ktdi
│   ├── books.json     the books: file, source, edition, contents page, chapter -> category
│   └── aliases.json   other names for entries, by id ("aoo" -> phb.rule.opportunity-attacks)
└── tools/
    ├── rules_build.py the build: PDF -> rules/<book>.json, for books laid out like the PHB
    ├── monsters_build.py  the build for a bestiary ("layout": "monsters"): bookmarks, stat blocks, the stat index
    ├── caps_build.py  the build for a book with headings in capitals ("layout": "caps": Xanathar's)
    └── statblocks.py  reading one stat block's OCR lines into stats (and back to text)
books/                 the PDFs (ours; never committed)
rules/                 what's built from them (never committed)
tests/                 pytest; a made-up rulebook in conftest.py stands in for the real ones
docs/                  COMMANDS.md (every command), SETUP.md (building books, deploying)
deploy/                deploy.sh (phased install in the homelab container), lawyer.service (systemd, sandboxed:
                       writes only logs/ and data/), the hashed dependency lock, INSTALL.md
```

## 4. The data

`rules/<book>.json` is `{"book", "source", "title", "edition", "entries": [...]}`. Every heading in the book is an
entry:

| Field | |
|---|---|
| `id` | `<book>.<category>.<slug>`, e.g. `phb.condition.poisoned`. A name used more than once in a category is qualified by its section: `phb.class.fighter.extra-attack`, `phb.class.monk.extra-attack`. Permanent: aliases and people's habits point at them. |
| `edition`, `source`, `book` | `5e-2014`, `PHB`, `Player's Handbook`: from books.json. |
| `page` | The printed page (§5). |
| `page_to` | Only where the scan lost pages nearby and it can't be pinned: the latest page it can be on (`Entry.where` shows "p. 284–288"). |
| `title` | The heading, as the book prints it. |
| `category` | From the chapter or section it's in (books.json `categories`): `condition`, `rule`, `spell`, `feat`, `class`, `race`, `equipment`, `background`, `creature`, `lore`. |
| `aliases` | Other names: `aliases.json`'s, added when the bot loads. |
| `path` | The headings above it, chapter first: `["Chapter 9: Combat", "Damage and Healing", "Damage Types"]`. |
| `sections` | The headings directly under it, for the Sections menu. |
| `text` | Its own text up to the next heading, run-in rules included (`**Carrying Capacity.** Your carrying…`), as light Markdown: `**label:**`, `*italic school line*`, `•` bullets, paragraphs split by blank lines. A heading's text doesn't include its sections' (they're their own entries), so a chapter is its introduction plus the Sections menu. |

## 5. The build

The books are scans with an OCR text layer, so the text is noisy but **the fonts survived**, and that's what the
parser leans on (pypdf's text visitor gives every run's font, size and position):

1. **Lines**: runs grouped by height, split where two columns' runs sit at the same height (`lines_of`).
2. **Headings** are small caps: a capital, then the rest of the word letter-spaced at ~0.8 of its size ("P" + "o i s
   o n e d"). The capital's size is the level (chapters 15.5pt, sections 10–13, conditions and spells 7.5). Lines
   that look like small caps but aren't headings are rejected: a paragraph's small-caps opening (a comma, or body
   text on the line), table rows the OCR ran together (`heading_of`).
3. **Run-in rules**: a line starting in italic ≥ 8pt and ending in a full stop ("*Barding.* Barding is armor…"). Each
   is an entry and part of its heading's text. One used more than four times ("At Higher Levels.") is a label, not a
   rule, and isn't an entry.
4. **The contents page is the outline** (`restructure`): what it lists under a chapter is a section (level 2) and
   everything else goes under one. A section whose heading the scan lost (Barbarian's and Tiefling's title pages are
   missing) is put back at the start of its printed page, so Rage is still Barbarian's.
5. **Printed pages**: each contents entry is found among the headings (`contents_anchors`), which anchors that PDF
   page to its printed number. With books.json `index_pages`, the book's index adds far more (`index_terms`,
   `index_anchors`): a term that names exactly one heading ("Action Surge (fighter), 72", a sub-entry with its term:
   "ability check contest") anchors its page, choosing among its listed pages the one within a dozen of the contents
   count. Anchors that contradict each other are dropped (`consistent`: printed pages rise with PDF pages and the gap
   never shrinks, since a scan loses pages but never gains them; the largest agreeing set, contents anchors counting
   three times). Pages between count on from the anchor before (`fill`). Where pages are lost between two anchors,
   nothing says which, so an entry there also gets `page_to`, counted back from the next (`latest`): it's somewhere
   from `page` to `page_to` ("PHB p. 284–288"). The PHB's index doesn't list spells, so the spells chapter, which
   lost four art pages somewhere, is the widest.
6. **Repairing the OCR** (`repair`, `clean`): it splits words ("dam age", "m ore", "su ccessfu l") and splits them in
   the wrong place ("tow orry"). Pieces are joined when the book prints the joined word, or a piece is mostly seen as
   half of a word; a split is moved when neither piece is a word and moving it makes two the book uses. Two everyday
   words side by side ("a way", "in to") are left alone. All dashes, apostrophes and bullets come out of the OCR as
   one unknown character; `clean` guesses which from context.

Creatures (the PHB's Appendix D) are stat blocks: their traits and actions (run-in rules to the parser) aren't
entries of their own, and the block is parsed into `stats` (§5b).

Known limits: some OCR damage survives (a few "comm oners" in ~1.2M characters), tables come through as run-together
text, and a sidebar's heading can nest the next few headings under it in `path`. None of it stops a lookup.

**A new book** may be laid out differently (the Monster Manual is mostly stat blocks). Build it, then check the top
level (`len(path) <= 1`), random entries, the category counts and lookups you know. Fix the parser for the layout,
with a test in `tests/test_rules_build.py` built from made-up runs in the book's fonts, rather than editing `rules/`
by hand: it's rebuilt from scratch every time.

### 5a. Bestiaries (`monsters_build.py`)

The Monster Manual's scan is complete but uses generic fonts (no small caps to go by), and it's built another way:

- **Its PDF bookmarks are the outline**: "A" › "Angels" › "Deva", with pages. Each bookmark's pages are a `lore`
  entry (books.json `categories` can make one something else: the introduction is `rule`). The alphabet's bookmarks
  are left out of paths.
- **Each stat block is a `monster` entry** under its bookmark (`path` ["Dragons", "Red Dragon"]). One starts at
  "Armor Class" (with the size-and-type line above it) and ends at the next heading in capitals or stat block.
- **Names come from the book's Index of Stat Blocks** (`statblock_index_pages`): the name above a stat block is in a
  display font the OCR often loses ("~0"), so each stat block on a page takes the index's name for that page
  closest to what's above it, or the one left over. The build reports index names no stat block took (mostly
  templates, which aren't stat blocks). With no index (Monsters of the Multiverse), every creature is bookmarked
  instead (`name_from_bookmarks`): a name the OCR ran together ("REDABISHAI") takes the bookmark with the same
  letters, in the stat block's order ("Abishai, Red" is Red Abishai), and a lost one takes its page's bookmark that
  no stat block has.
- **Headings in the lore are entries of their own** under their bookmark: a race's "Changeling Traits" (which
  `/race` reads), a sidebar. Lair actions and regional effects are named for the monster ("Aboleth Lair Actions"),
  and the monsters under that bookmark list them in `stats["lair"]`. A heading that's the bookmark's own name
  carries on its text; the running footer ("44 Chapter 2 | Bestiary") is never a heading.
- **The book's own bookmark** (one top-level bookmark with everything under it: "Mordenkainen Presents...") is
  dropped, and **a page several bookmarks start on** belongs to the first (Genasi, Earth / Fire / Water).

### 5c. Headings in capitals (`caps_build.py`)

Xanathar's scan is like the Monster Manual's (generic fonts, complete, bookmarked), but laid out like the Player's
Handbook, so it's the PHB's pipeline (`rules_build`'s tree, entries, word repair) with another front end:

- **Headings** are lines all in capitals, in Times, at least ~0.8 of the text's size. Their size is their level,
  from books.json `levels` ([[least size, level], ...]: Xanathar's 13pt sections' own headings, 10pt subclasses,
  8.5pt features and spells). Capitals in Helvetica (tables', sidebars' titles) and the running footer aren't.
- **The bookmarks are the outline**: the first depth with several bookmarks is the chapters, the one under it the
  sections (`restructure`, as the PHB's contents page). A section heading takes its bookmark's spelling.
- **Headings are re-spaced** (`respace`): the OCR spaces capitals at random ("r a kish audacity", "zealouspresen ce"),
  so a heading's letters are split again into the cheapest words: one the book uses costs 1 (a short one that isn't
  everyday, 1.5), one it never prints whole costs more the longer it is, and "words" that are just everyday words
  run together ("ofthe") don't count. The words come from this book and every other built book (`heading_words`),
  since this scan prints some words only split. A heading already in words is left alone, and a "word" with an
  everyday one stuck on ("axeof") doesn't count either.
- A heading needs a word of three letters or more (the DMG's treasure tables' "CP SP" columns aren't headings), and
  an item's or spell's italic line under its name can run onto a second line ("*Weapon (any sword...),*"
  "*legendary (requires attunement)*"): it's one line.

Supplements' subclasses join their class: `/class` finds every book's heading for the same class, and its
subclasses (Xanathar's Barbarian > Primal Paths > Path of the Zealot) go in the menu with their source.

**Deeper bookmarks** (Tasha's bookmarks every subclass, spell and magic item, the DMG its chapters' sections:
`deeper_bookmarks`): in such a book every bookmark below the chapters, sections included, is matched on its own page
(the DMG has "Doors" in its Dungeons chapter and in Appendix A), each depth a level (a subclass 3), and every other
heading goes one below the deepest, all at the same level,
because Tasha's headings' sizes don't say much (a subclass's is no bigger than its features', and "Ranger
Archetypes" is bigger than both). A bookmark finds its heading on its page or either side; one with no heading (The
Genie's title is only in the art) is put back at the top of its page. Then **`reown`** moves each feature to the
subclass its italic line names ("6th-level Fathomless feature"), since two-column pages are read out of order;
a class's own ("2nd-level rogue feature") stays put. books.json can also lower `smallest_heading` (Tasha's 8pt
features against 10pt text) and list `ignore_headings` (Tasha's handwritten notes in the art: "TAA", "Taha").

Stat blocks inside features and spells (Tasha's Wildfire Spirit, the Summon spells' spirits, Mighty Servant of
Leuk-o) are parsed too (`has_stat_block`): any heading whose first lines are Armor Class and Hit Points. Summons
have no alignment, hit points as a formula ("5 + five times your druid level") and no challenge rating; none of
that is flagged as a misread.

### 5b. Stat blocks (`statblocks.py`)

`parse(lines)` turns a stat block's lines into `stats`: size, type, alignment, AC, HP and dice, speed, the six
scores, saves, skills, damage and condition immunities, senses, languages, CR and XP, and lists of traits, actions,
reactions and legendary actions (`{"name", "text"}`). The OCR is fought three ways:

- **Digits read as letters** ("Sd6", "1S", "SO XP", "ld4") are put back only where a number must be (`fix_numbers`).
- **The rules check the numbers**: a score against its modifier, HP against its dice's average, XP from the CR's
  table. What doesn't add up is fixed if it can be and listed in `stats["checks"]` either way; `/stats` warns about
  the ones that matter (no actions read) with the page to check.
- **Lost structure**: the ability column comes interleaved with other lines, so scores are picked out wherever they
  are; an item's name must be in title case and follow a finished sentence (so "...saving throw. On a failure"
  carries on); and when the OCR lost the ACTIONS heading, actions start at the first attack or Multiattack (traits
  always come first).

`render()` writes the stats back as Markdown, the entry's `text`, so `/rule` shows stat blocks too and searching
their words works. About 6% of the Monster Manual's blocks are still incomplete (a caption or column break through
them); they say so.

## 6. The books are ours, not the repo's

The PDFs are the maintainer's own copies. **Nothing from them is ever committed**: `books/` and `rules/` are in
`.gitignore` (`test_registration.py` checks), the tests use a made-up stand-in (`tests/conftest.py`'s `BOOK`), and
`aliases.json` / `books.json` hold ids, names and settings only (`test_rulebook.py` checks aliases are short names).
No quotes from the books in docs, tests or commit messages either.

## 7. Searching

`Rulebook.search(query, book, category)` (in `lib/rulebook.py`), best first, at most 25 (a Discord menu):

1. An entry's **id** (what autocomplete sends) is that entry.
2. **Exact names**: the words typed (filler like "the" and "my" aside) are one of the entry's names: its title, an
   alias, its title with its heading ("Poison Damage Types"), or its section with its title ("Fighter Extra Attack").
3. **Close names**: `name_score` = how much of the name the typed words cover × how many typed words it uses, with a
   small typo (or swapped letters: "posion") worth a bit less. ≥ 0.5 counts. Multiplying (rather than ktdi's weighted
   sum) is what makes "poison damage" the damage type (2/3 of "Poison Damage Types") over the condition aliased
   "poison" (it uses half of what was typed).
4. **Text**: entries whose text uses every typed word (each at least three letters), only when names found fewer
   than 25.

Ties go by `CATEGORY_ORDER` (conditions first: at the table, "poison" usually means poisoned), then the shallower
entry, then the earlier page. A search is ~30 ms over the PHB, fast enough for autocomplete on every keystroke.

## 8. /rule

A hybrid command (`/rule` and `!rule`). The answer is public by default (it's a ruling for the table) unless
`private`. Under it, `RuleView` has up to three rows: **Other matches** (the search's other hits), **Sections under
…** (`Rulebook.sections_of`) and **⬆️ Up to …** (the heading above, if it's an entry). Picking one edits the message in
place. Only whoever asked can use them (`interaction_check`), for `MENU_TIMEOUT`, then they're greyed out. Text past
`TEXT_SHOWN` characters is cut at a sentence with the page to read on.

## 8a. /stats, /class and /race

All three read `rule.rulebook` (so the tests' stand-in book reaches them too):

- **/stats** searches only entries with `stats` (`Rulebook.search(only=...)`), and lays them out as embeds: AC, HP and
  CR inline, the scores in a code block so they line up, then a field per part (as many items to a field as fit,
  "(continued)" after). Over one embed's 6,000 characters, it's pages with ◀ ▶.
- **/class**: a class is a `class` entry with "Class Features" among its sections. Its features are the sections under
  that, in level order (the level is read from the text: "Beginning at 5th level"; 1st if it doesn't say), with Hit
  Points, Proficiencies and Equipment first (beside Class Features, for Tasha's Artificer) and sidebars ("The
  Fighter") left out. Its subclasses are headings with two or more features of their own, either under a heading of
  them (Martial Archetypes) or straight under the class (Tasha's), never a list of options ("Optional Class
  Features", "Maneuver Options": `NOT_SUBCLASSES`).
- **/race**: a race is a `race` entry with "<Race> Traits" among its sections. Its traits are that entry's run-in
  rules, one field each; its subraces are the sections under it.

A race the book has no heading for, only its kinds' traits (Monsters of the Multiverse's Genasi: Air Genasi Traits
and the rest), is found by `traits_named`: every race traits heading with all the words typed (`/race genasi` is
all four, `/race fire genasi` one).

Typing "fighter battle master" finds the shortest start that's a class by name, and the rest is the subclass. With a
subclass, `/class` shows both collapsed into one list (`subclass_pages`): every feature in level order, the
subclass's marked 🔸 and cut shorter (`COMPACT_TEXT`); a subclass feature that doesn't say its level (Maneuvers) goes
at the subclass's first.

## 8b. Server settings and prefer_newer

`lawyer.db` (SQLite, `DB_PATH`) has one table, `guild_settings`: a row per server, a column per setting, each
defaulting to the old behaviour (so a server with no row has every setting off). `/settings prefer_newer` (Manage
Server) sets `prefer_newer`; `/rule` and `/stats` pass it to `Rulebook.search(newer_first=...)`, which sorts ties
newest book first by books.json `published`. A tie is what matters: the same name in two books (Falling). `/rule` says
which older books have it, and `book:phb` (any book) gets that one.

## 9. Startup and deployment

Like ktdi: `bot.py` → `lawyer.bot.main()`; `config` loads `.env` (`.env.dev` with `--dev`); `setup_hook` loads
`FEATURES` and syncs slash commands to each server in `GUILD_IDS` (instant), clearing the global copies. `rule.py`
loads `rules/` when it's imported, and logs how many entries from which books (or warns there are none).

Deployed like CritDeckPy (`deploy/`, [deploy/INSTALL.md](deploy/INSTALL.md)): `deploy.sh`'s phases make a `lawyer`
user, a checkout at `/opt/Lawyer`, a venv from the hashed lock (the same two dependencies as CritDeckPy, so the same
lock), `.env` (readable only by root and the service), and the sandboxed `lawyer.service` running `python -m lawyer`,
which can write only `logs/` and `data/` (where `DB_PATH` puts `lawyer.db`). The books are built on the PC with the
PDFs and only `rules/*.json` is copied over; the `rules` phase stops until it has been.

## 10. Testing

```bash
pip install -e ".[dev]"
python -m pytest            # ~2 seconds
```

- `tests/conftest.py` never reads the real `.env` (`LAWYER_NO_DOTENV=1`), and swaps `/rule`'s rulebook for `BOOK`.
- `tests/fakes.py`: `User`, `Guild`, `Ctx`, `Interaction`. Call commands directly: `run(rule.rule.callback(ctx,
  what="poison"))`, then check `ctx.last.embed`, `.view`, `.private`.
- `test_rules_build.py` builds entries from made-up pages of runs (fonts and sizes as the scans have them).
- `test_registration.py` loads every feature onto a real `LawyerBot` and checks the command list, Discord's limits,
  `/help` pages, that docs/COMMANDS.md and the README mention every command, that this file's layout mentions every
  file, and that `.env.example` has every setting.

## Rules for changes

1. **Run the tests before and after.** Add tests for new behaviour.
2. **New feature** → new `lawyer/features/<name>.py` with `setup(bot)`, added to `FEATURES`, with a `HELP_CATEGORY`.
   New settings go in `config.py` and `.env.example`.
3. **Help and docs stay accurate**: a description ≤ 100 characters, a docstring (the `/help` page), `describe` for
   every option, a row in docs/COMMANDS.md, a line in the README, and this file's layout for a new file.
4. **Never commit the books** (§6), or anything quoted from them.
5. **Ids are permanent**; a parser change that renames them updates `aliases.json` (the build lists lost ids).
6. **Discord limits:** descriptions ≤ 100 characters, ≤ 25 choices/menu options, embed description ≤ 4096, fields
   ≤ 1024, embeds ≤ 6000, a reply within 3 seconds.
7. **Commits are made by the maintainer.**

## Decisions and their reasons

| Decision | Why |
|---|---|
| Build once, offline, to JSON | The bot stays small and quick to start; the slow, fiddly parsing can be rerun and inspected on its own. |
| pypdf, not PyMuPDF | Pure Python: installs anywhere (PyMuPDF has no wheel for the maintainer's Windows on ARM + Python 3.14), and only the build needs it. |
| Headings from fonts, not text | The OCR mangles heading text ("U sing T his B o o k") but kept the fonts, which say exactly what's a heading and its level. |
| The contents page as the outline | The scan dropped the class and race title pages; without the outline, every class's Extra Attack would be one muddle. |
| One entry per heading, sections as a menu | Discord shows ~4,000 characters; a chapter's whole text wouldn't fit, and the right answer is usually one heading. |
| No AI | A rules lawyer has to quote the book. Every answer is the book's text, with its page. |
| Public answers by default | A ruling is for the whole table. `private` is there for checking quietly. |
| Aliases in a committed file, merged at load | Table slang ("aoo") isn't in the books, isn't the books' text, and shouldn't need a rebuild. |
