"""The rulebooks, as built by lawyer.tools.rules_build, and finding a rule in them however it's typed. No AI.

Each book is rules/<id>.json: {"book", "source", "title", "edition", "entries": [entry, ...]}, where an entry is

    {"id": "phb.condition.poisoned", "edition": "5e-2014", "source": "PHB", "book": "Player's Handbook",
     "page": 292, "title": "Poisoned", "category": "condition", "aliases": ["poison"],
     "path": ["Appendix A: Conditions"], "sections": [], "text": "..."}

search() ranks what's typed against every entry's names: its title, its aliases (from the book and from
lawyer/lib/aliases.json), and its title with the heading it's under ("poison damage" is Damage Types > Poison,
"fighter extra attack" is Fighter's). A name typed exactly wins; then the closest names (any word order, small typos);
then entries whose text uses every word typed. Ties go to the categories people look up most (conditions first).
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

from lawyer.lib import fuzzy

ALIASES_FILE = Path(__file__).resolve().parent / "aliases.json"
BOOKS_FILE = Path(__file__).resolve().parent / "books.json"
# Which kind of entry wins a tie: "poison" is the condition before it's the damage type.
CATEGORY_ORDER = ["condition", "rule", "spell", "feat", "class", "race", "equipment", "background", "monster",
                  "creature", "item", "lore"]
EXACT, CLOSE, TEXT = "exact", "close", "text"
CLOSE_ENOUGH = 0.5  # The lowest name score that counts as a match ("posion damage" is 0.51 of Poison Damage Types)
SHORTEST_TEXT_WORD = 3  # Searching the text for "po" would find everything
MOST_RESULTS = 25  # Discord's limit for a menu


@dataclass
class Entry:
    id: str
    title: str
    source: str
    book: str
    edition: str
    page: int
    category: str
    text: str
    path: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    book_id: str = ""
    stats: dict | None = None  # A stat block's, parsed (see lawyer/tools/statblocks.py): monsters and creatures

    @classmethod
    def from_json(cls, data: dict, book_id: str) -> "Entry":
        return cls(data["id"], data["title"], data["source"], data["book"], data["edition"], data["page"],
                   data["category"], data.get("text", ""), list(data.get("path", [])),
                   list(data.get("sections", [])), list(data.get("aliases", [])), book_id, data.get("stats"))

    @property
    def where(self) -> str:
        """Where it is in the book: "PHB p. 292"."""
        return f"{self.source} p. {self.page}"

    def names(self) -> list[str]:
        """Every name it could be asked for by."""
        names = [self.title, *self.aliases]
        if self.path:
            names.append(f"{self.title} {self.path[-1]}")  # "Poison Damage Types"
        if len(self.path) >= 2:
            names.append(f"{self.path[1]} {self.title}")  # "Fighter Extra Attack"
        return names


@dataclass
class Hit:
    entry: Entry
    score: float
    how: str  # EXACT, CLOSE or TEXT
    name: str = ""  # The name that matched


@lru_cache(maxsize=200_000)
def word_match(a: str, b: str) -> float:
    """fuzzy.word_match, and letters swapped round counts as a typo too ("posion" for "poison")."""
    score = fuzzy.word_match(a, b)
    if not score and len(a) == len(b) >= 4 and a[0] == b[0] and sorted(a) == sorted(b):
        return fuzzy.TYPO
    return score


def name_score(typed: list[str], name: list[str]) -> float:
    """How well the words typed are the name: how much of the name they cover, times how many of them it uses. A
    word a small typo away counts for a bit less. "poison damage" is 2/3 of "poison damage types" (0.67), but
    "poison" is only half of what was typed (0.5)."""
    if not typed or not name:
        return 0.0
    covered = sum(max(word_match(w, n) for w in typed) for n in name) / len(name)
    if not covered:
        return 0.0
    used = sum(max(word_match(w, n) for n in name) for w in typed) / len(typed)
    return covered * used


class Rulebook:
    """Every entry from every built book."""

    def __init__(self, entries: list[Entry], books: dict[str, dict] | None = None):
        self.entries = entries
        self.books = books or {}  # id -> {"source", "title", "edition"}
        self.by_id = {e.id: e for e in entries}
        self.children: dict[tuple, list[Entry]] = {}
        for entry in entries:
            self.children.setdefault((entry.book_id, *entry.path), []).append(entry)
        self.names = [(entry, name, tuple(fuzzy.words(name))) for entry in entries
                      for name in dict.fromkeys(entry.names())]
        self.plain_text = {e.id: fuzzy.plain(e.text) for e in entries}  # For the words-in-the-text search

    @classmethod
    def load(cls, folder: Path, aliases_file: Path = ALIASES_FILE, books_file: Path = BOOKS_FILE) -> "Rulebook":
        """Every book in the folder (rules/*.json), with lawyer/lib/aliases.json's names added, and when each came
        out (lawyer/lib/books.json), for newer_first."""
        extra = json.loads(aliases_file.read_text(encoding="utf-8"))["aliases"] if aliases_file.exists() else {}
        published = json.loads(books_file.read_text(encoding="utf-8"))["books"] if books_file.exists() else {}
        entries, books = [], {}
        for file in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            data = json.loads(file.read_text(encoding="utf-8"))
            book_id = data.get("book", file.stem)
            books[book_id] = {k: data.get(k, "") for k in ("source", "title", "edition")}
            books[book_id]["published"] = published.get(book_id, {}).get("published", "")
            for item in data["entries"]:
                entry = Entry.from_json(item, book_id)
                entry.aliases = list(dict.fromkeys(entry.aliases + extra.get(entry.id, [])))
                entries.append(entry)
        return cls(entries, books)

    def age(self, entry: Entry) -> int:
        """Sorts newest book first: minus the book's place in publication order (a book with no date is oldest)."""
        dates = sorted({b.get("published", "") for b in self.books.values()})
        return -dates.index(self.books.get(entry.book_id, {}).get("published", "")) \
            if self.books.get(entry.book_id, {}).get("published", "") in dates else 0

    def __len__(self) -> int:
        return len(self.entries)

    def sections_of(self, entry: Entry) -> list[Entry]:
        """The entries for the headings under this one, in the book's order."""
        under = self.children.get((entry.book_id, *entry.path, entry.title), [])
        wanted = set(entry.sections)
        return [e for e in under if e.title in wanted]

    def search(self, query: str, book: str | None = None, category: str | None = None,
               only: Callable[[Entry], bool] | None = None, newer_first: bool = False) -> list[Hit]:
        """The entries that best match what was typed, best first. An entry's id ("phb.condition.poisoned", what
        autocomplete sends) finds just that entry. `only` narrows it further (/stats: only stat blocks)."""
        query = query.strip()
        if query in self.by_id and (not only or only(self.by_id[query])):
            return [Hit(self.by_id[query], 1.0, EXACT, self.by_id[query].title)]
        typed = fuzzy.words(query)
        if not typed:
            return []

        def wanted(entry: Entry) -> bool:
            return (not book or entry.book_id == book) and (not category or entry.category == category)                 and (not only or only(entry))

        best: dict[str, Hit] = {}
        for entry, name, name_words in self.names:
            if not wanted(entry) or not name_words:
                continue
            if list(name_words) == typed:
                hit = Hit(entry, 1.0, EXACT, name)
            else:
                score = name_score(typed, list(name_words))
                if score < CLOSE_ENOUGH:
                    continue
                hit = Hit(entry, score * 0.99, CLOSE, name)  # Never quite as good as exact
            if entry.id not in best or hit.score > best[entry.id].score:
                best[entry.id] = hit
        hits = list(best.values())
        if len(hits) < MOST_RESULTS and all(len(word) >= SHORTEST_TEXT_WORD for word in typed):
            patterns = [re.compile(rf"\b{re.escape(word)}\w*", re.IGNORECASE) for word in typed]
            for entry in self.entries:
                if entry.id in best or not wanted(entry):
                    continue
                text = self.plain_text[entry.id]
                if all(p.search(text) for p in patterns):
                    uses = sum(len(p.findall(text)) for p in patterns)
                    hits.append(Hit(entry, min(0.5, 0.2 + 0.03 * uses), TEXT))
        # Ties: with newer_first (a server's /settings prefer_newer), the newest book's version of a rule first
        # (Xanathar's Falling before the PHB's); then by kind (conditions first), the shallower, the earlier page.
        hits.sort(key=lambda h: (-round(h.score, 3), self.age(h.entry) if newer_first else 0, rank(h.entry.category),
                                 len(h.entry.path), h.entry.page))
        return hits[:MOST_RESULTS]

    def autocomplete(self, typed: str, book: str | None = None, limit: int = 25,
                     only: Callable[[Entry], bool] | None = None) -> list[Entry]:
        """For autocomplete: entries whose title starts with what's typed, then ones containing it; or, when
        nothing starts that way, the best search results. Nothing typed: the conditions (or, with `only`, the
        first of what it allows)."""
        pool = [e for e in self.entries if (not book or e.book_id == book) and (not only or only(e))]
        if not typed.strip():
            first = [e for e in pool if e.category == "condition"] if not only else pool
            return sorted(first, key=lambda e: e.title)[:limit]
        found = fuzzy.starting_first(typed, pool, limit=limit, key=lambda e: e.title)
        if len(found) < limit:
            seen = {e.id for e in found}
            found += [h.entry for h in self.search(typed, book, only=only) if h.entry.id not in seen][:limit - len(found)]
        return found[:limit]


def rank(category: str) -> int:
    return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
