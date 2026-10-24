"""Building a rulebook whose headings are in capitals (Xanathar's Guide): rules_build calls build() for a book whose
books.json entry says "layout": "caps".

Some scans (Xanathar's, like the Monster Manual) have generic fonts, so there are no small caps to find headings by,
but the headings are still set apart: in capitals, in Times, a size up from the text. Their size is their level
(books.json "levels": e.g. 13pt and up is a section's heading, 10pt a subclass's, 8pt a feature's or spell's). Capitals
in Helvetica are tables' and sidebars' titles, and small capitals at the foot of the page are its running footer;
neither is a heading.

Everything else is the Player's Handbook's build (rules_build): run-in rules in italic, the OCR's words repaired, an
entry per heading. The outline is the PDF's bookmarks rather than a contents page: a top-level bookmark is a chapter,
the ones under it its sections, and a section the scan has no heading for is put back on its page. The PDF's pages
are the book's (less "page_offset").
"""

import json
import re
from collections import Counter
from pathlib import Path

from lawyer.tools import rules_build as rb
from lawyer.tools import statblocks
from lawyer.tools.rules_build import Block, Contents, Run

FOOTER = 45  # Points from the bottom of the page: the running footer ("CHAPTER 1 | CHARACTER OPTIONS")
# Labels that start a line of their own, whatever their font: a spell's, a feat's
LABELS = {"Casting Time", "Range", "Components", "Duration", "Prerequisite"}


def is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) >= 0.85 * len(letters)


def body_size(pages: list[list[Run]]) -> float:
    """The text's size: the one most of the book's letters are in."""
    sizes = Counter()
    for runs in pages:
        for run in runs:
            if not run.italic and not is_caps(run.text):
                sizes[run.size] += len(run.text)
    return sizes.most_common(1)[0][0] if sizes else 9.0


def level_of(size: float, levels: list[list[float]]) -> int:
    """A heading's level from its size: books.json "levels" is [[least size, level], ...], biggest first."""
    return next((level for least, level in levels if size >= least), levels[-1][1])


def heading_of(line: list[Run], body: float, smallest: float = 0.82,
               ignore: frozenset[str] = frozenset()) -> tuple[str, float] | None:
    """(title, size) if the line is a heading: all capitals, in Times (not a table's Helvetica or Arial), at least
    `smallest` of the text's size (not a caption), not the footer, and not one of books.json's "ignore_headings"
    (Tasha's handwritten notes in the art: "TAA", "TAHA")."""
    text = " ".join(r.text.strip() for r in line)
    if not is_caps(text) or len(text) > rb.LONGEST_HEADING or rb.plain(text) in ignore:
        return None
    if statblocks.is_ability_line(text) or statblocks.section_of(text):
        return None  # A stat block's own "CHA" or "ACTIONS"
    sans = sum(len(r.text) for r in line if "Helvetica" in r.font or "Arial" in r.font)
    if sans * 2 > len(text) or any(r.italic for r in line) or line[0].y < FOOTER:
        return None  # Mostly sans serif: a table's title ("INFECTIOUS" "FURY" is a heading with one word in Arial)
    size = max(r.size for r in line)
    if size < body * smallest:
        return None  # A caption, or the footer
    title = re.sub(r"\s+", " ", text).strip()
    if not re.search(r"[A-Z]{2}", title.replace(" ", "")):
        return None
    return title, size


def run_in_of(line: list[Run]) -> tuple[str, list[Run]] | None:
    """(name, the rest) if the line starts with a run-in rule in italic, ending in a full stop: "At Higher Levels."
    (which the OCR may give as three runs)."""
    name, used = "", 0
    for run in line:
        if not run.italic:
            break
        name = f"{name} {run.text.strip()}".strip()
        used += 1
        if name.endswith("."):
            break
    if not name.endswith(".") or not name[0].isupper() or len(name.split()) > rb.LONGEST_RUN_IN + 3:
        return None
    return name[:-1].strip(), line[used:]


def blocks_of(pages: list[list[Run]], levels: list[list[float]], smallest: float = 0.82,
              ignore: frozenset[str] = frozenset()) -> list[Block]:
    body = body_size(pages)
    blocks: list[Block] = []
    for number, runs in enumerate(pages):
        for line in rb.lines_of(runs):
            if line[0].y < FOOTER and is_caps(" ".join(r.text for r in line)):
                continue  # The running footer
            if heading := heading_of(line, body, smallest, ignore):
                title, size = heading
                level = level_of(size, levels)
                last = blocks[-1] if blocks else None
                if last and last.kind == "heading" and last.page == number and last.level == level \
                        and last.text.split()[-1].lower() in rb.CARRY_ON | {"of"}:  # "PATH OF" / "THE STORM HERALD"
                    last.text += " " + title
                    continue
                blocks.append(Block("heading", title.lower(), level, number, line[0].x))
                continue
            if run_in := run_in_of(line):
                name, rest = run_in
                blocks.append(Block("run_in", name, rb.RUN_IN, number, line[0].x))
                if rest:
                    blocks.append(Block("text", " ".join(r.text.strip() for r in rest) + " ", page=number,
                                        x=rest[0].x))
                continue
            first = line[0]
            text = " ".join(r.text.strip() for r in line) + "\n"
            starts = False
            label = re.match(r"([A-Z][A-Za-z ]+):\s*(.*)", text)
            if label and ("Bold" in first.font or label.group(1).strip() in LABELS):  # A spell's "Casting Time: 1 action"
                text = f"**{label.group(1).strip()}:** {label.group(2)}"
                starts = True
            elif first.italic and blocks and blocks[-1].kind == "heading":
                text = f"*{text.strip()}*\n"  # A spell's school, just under its name
                starts = True
            blocks.append(Block("text", text, page=number, x=first.x, starts=starts))
    return blocks


def respace(title: str, vocab: rb.Words) -> str:
    """A heading's words, however the OCR spaced its capitals: "zealouspresen ce" -> "zealous presence", "r a kish
    audacity" -> "rakish audacity", "oath of re demp ti on" -> "oath of redemption". Its letters are split again into
    the fewest words the book uses; punctuation stays where it is. A stretch that won't split stays as it was."""
    def cost(piece: str) -> float | None:
        """A word the book uses costs 1 (a short one that isn't an everyday word a bit more: "due list" shouldn't
        beat "duelist"); one it never prints whole ("rakish") costs more the longer it is; one letter, nothing."""
        if piece in rb.COMMON:
            return 1.0
        if runs_together(piece):
            return None  # "ofthe", "wayofthesun": everyday words the OCR ran together, not a word
        if vocab[piece] >= 2 and len(piece) > 1 and not vocab.fragment(piece):  # Not "desc" of "desc rip tions"
            return 1.5 if len(piece) <= 3 else 1.0
        if len(piece) >= 4:
            return 1.0 + 0.3 * len(piece)
        return None

    def runs_together(piece: str) -> bool:
        """Whether a "word" is really several: two or more everyday words ("ofthe"), and at most one other
        ("wayofthesun"). Not "domain" ("do" + "main") or "guardian" ("guard" + "i" + "an")."""
        best: list[tuple[int, int] | None] = [(0, 0)] + [None] * len(piece)  # (everyday words, others) for piece[:i]
        for end in range(2, len(piece) + 1):
            for start in range(0, end - 1):
                w = piece[start:end]
                if best[start] is None:
                    continue
                if w in rb.COMMON:
                    found = (best[start][0] + 1, best[start][1])
                elif len(w) >= 3 and vocab[w] >= 20 and not vocab.fragment(w):
                    found = (best[start][0], best[start][1] + 1)
                else:
                    continue
                if found[1] <= 1 and (best[end] is None or found[0] > best[end][0]):
                    best[end] = found
        return best[-1] is not None and best[-1][0] >= 2

    def split(letters: str) -> list[str] | None:
        best: list[tuple[float, list[str]] | None] = [(0.0, [])] + [None] * len(letters)
        for end in range(1, len(letters) + 1):
            for start in range(max(0, end - 20), end):
                piece_cost = cost(letters[start:end])
                if piece_cost is None or best[start] is None:
                    continue
                total = best[start][0] + piece_cost
                if best[end] is None or total < best[end][0]:
                    best[end] = (total, best[start][1] + [letters[start:end]])
        return best[-1][1] if best[-1] else None

    parts = re.split(r"([^a-z ]+)", title.lower().replace("_", ""))
    out = []
    for part in parts:
        letters = part.replace(" ", "")
        if all(w in rb.COMMON or (len(w) > 2 and vocab[w] >= 5) for w in part.split()):
            out.append(part)  # Already words ("war magic"): leave it
            continue
        pieces = split(letters) if letters.isalpha() else None
        out.append(f" {' '.join(pieces)} " if pieces else part)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def heading_words(vocab: rb.Words, book_id: str) -> rb.Words:
    """The words to re-split headings with: this book's, and the other built books' (already repaired). This scan
    only ever prints some words split ("vul n erability"), but the Player's Handbook has them whole."""
    words = rb.Words([])
    words.count, words.pairs, words.halves = Counter(vocab.count), vocab.pairs, Counter(vocab.halves)
    for file in sorted(rb.RULES_DIR.glob("*.json")):
        if file.stem == book_id:
            continue
        for entry in json.loads(file.read_text(encoding="utf-8")).get("entries", []):
            words.count.update(w.lower() for w in re.findall(r"[A-Za-z]+", f"{entry['title']} {entry['text']}"))
    return words


def deeper_bookmarks(blocks: list[Block], marks: list[tuple[int, str, int]], vocab: rb.Words) -> list[Block]:
    """Bookmarks below the sections (Tasha's: Barbarian > Path of the Beast, Spells > Booming Blade), as levels below
    them: a subclass at 3, and so on. Each takes its heading on its page (or the next: a bookmark can point at the page
    before), spelled as the bookmark spells it; one with no heading is put back at the start of its page. Then every
    other heading goes under the deepest of them: in Tasha's a subclass's heading is no bigger than its features'."""
    if not marks:
        return blocks
    deepest = 1 + max(depth for depth, _, _ in marks)
    claimed: set[int] = set()
    out = list(blocks)
    for depth, title, page in marks:
        key = rb.plain(title).rstrip("s")  # The heading can be singular: "Optional Class Feature"
        found = next((b for b in out if b.kind == "heading" and id(b) not in claimed and page - 1 <= b.page <= page + 1
                      and rb.plain(b.text).rstrip("s") == key), None)
        if found is None:
            at = next((i for i, b in enumerate(out) if b.page >= page), len(out))
            found = Block("heading", title, 0, page)
            out.insert(at, found)
        found.level, found.text = 1 + depth, title
        claimed.add(id(found))
    for block in out:  # All one level: a bigger heading ("Ranger Archetypes") isn't the features' parent
        if block.kind == "heading" and id(block) not in claimed and block.level > 2:
            block.level = deepest + 1
    return reown(out, [b for b in out if id(b) in claimed and b.level == deepest], deepest + 1)


OWNER = re.compile(r"\d+\s*(?:st|nd|rd|th)\s*[- ]\s*level (.+?) feature", re.IGNORECASE)  # "4 th-level" too


def owner_key(name: str) -> str:
    return rb.plain(re.sub(r"^the ", "", name.strip().lower()))


def reown(blocks: list[Block], subclasses: list[Block], feature_level: int) -> list[Block]:
    """Each feature back under the subclass its own line says it's for ("6th-level Fathomless feature"). The scan
    reads two-column pages out of order, and a subclass whose title is only in the art is put back at the top of
    its page, so a feature can end up under the wrong one. A feature of the class itself ("2nd-level rogue feature")
    stays where it is."""
    keys = {id(b): owner_key(b.text) for b in subclasses}
    units: list[list[Block]] = []
    for block in blocks:
        if block.kind == "heading" or not units:
            units.append([block])
        else:
            units[-1].append(block)

    def owner(unit: list[Block]) -> str | None:
        head = unit[0]
        if head.kind != "heading" or head.level < feature_level:
            return None
        text = " ".join(b.text for b in unit[1:5] if b.kind == "text")[:300]
        match = OWNER.search(text)
        if not match:
            return None
        named = owner_key(match.group(1))
        return next((k for k in keys.values() if k and (k == named or named.endswith(k) or k.endswith(named))), None)

    out: list[tuple[str | None, list[Block]]] = []  # (whose it is, unit)
    current: str | None = None
    for unit in units:
        head = unit[0]
        if id(head) in keys:
            current = keys[id(head)]
            out.append((current, unit))
            continue
        if head.kind == "heading" and head.level < feature_level:
            current = None  # A class's own heading: what follows isn't a subclass's
        mine = owner(unit)
        if mine and mine != current and any(k == mine for k, _ in out):
            last = max(i for i, (k, _) in enumerate(out) if k == mine)
            out.insert(last + 1, (mine, unit))
            continue
        out.append((current if mine is None else mine, unit))
    return [b for _, unit in out for b in unit]


def outline(pdf: Path) -> list[tuple[int, str, int]]:
    """The PDF's bookmarks: (depth, title, PDF page), in order."""
    import pypdf
    reader = pypdf.PdfReader(pdf)
    found = []

    def walk(items, depth):
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                found.append((depth, str(item.title).strip(), reader.get_destination_page_number(item)))
    walk(reader.outline or [], 0)
    return found


def build(book_id: str, book: dict, pdf: Path) -> dict:
    pages = rb.read_runs(pdf)
    ignore = frozenset(rb.plain(t) for t in book.get("ignore_headings", []))
    blocks = blocks_of(pages, book["levels"], book.get("smallest_heading", 0.82), ignore)
    vocab = rb.vocabulary(blocks)
    words = heading_words(vocab, book_id)
    for block in blocks:
        if block.kind == "heading":
            block.text = rb.fix_title(respace(block.text, words), vocab)
        elif block.kind == "run_in":
            block.text = rb.fix_title(rb.repair(block.text, vocab), vocab)
    offset = book.get("page_offset", 0)
    numbers = [n - offset for n in range(len(pages))]
    # The bookmarks under the book's own (Xanathar's Guide to Everything > Ch. 1 > Barbarian): chapters and sections
    marks = outline(pdf)
    # The chapters' depth: the first with several bookmarks (Xanathar's has just its cover and back cover above them)
    depths = Counter(d for d, _, _ in marks)
    top = min((d for d, n in depths.items() if n >= 3), default=0)
    toc = [Contents(title, numbers[page], depth == top) for depth, title, page in marks if depth in (top, top + 1)]
    chapters = [c for c in toc if c.chapter]
    sections = [c for c in toc if not c.chapter]
    blocks = rb.restructure(blocks, sections, numbers, vocab)
    spelled = {rb.plain(c.title): c.title for c in sections}
    for block in blocks:  # A section's heading as its bookmark spells it: "Spell Desc Rip Tions" is Spell Descriptions
        if block.kind == "heading" and block.level == 2 and rb.plain(block.text) in spelled:
            block.text = spelled[rb.plain(block.text)]
    for chapter in sorted(chapters, key=lambda c: c.page, reverse=True):  # A chapter starts on its page
        page = numbers.index(chapter.page)
        at = next((i for i, b in enumerate(blocks) if b.page >= page), len(blocks))
        blocks.insert(at, Block("heading", chapter.title, 1, page))
    for block in blocks:  # A heading the book's size makes a chapter's is a section's, under the bookmarks' chapter
        if block.kind == "heading" and block.level == 1 and block.text not in {c.title for c in chapters}:
            block.level = 2
    blocks = deeper_bookmarks(blocks, [(d - top, t, p) for d, t, p in marks if d >= top + 2], vocab)
    return {"book": book_id, "source": book["source"], "title": book["title"], "edition": book["edition"],
            "entries": rb.entries(rb.tree(blocks), book_id, book, numbers, vocab)}
