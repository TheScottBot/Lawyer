"""Building a bestiary (the Monster Manual) for /rule and /stats: rules_build calls build() for a book whose
books.json entry says "layout": "monsters".

A bestiary isn't laid out like the Player's Handbook, and its scan is different too (generic fonts, so no small caps
to go by), so it's read another way:

- **Its bookmarks are the outline**: "A" > "Angels" > "Deva", each with its page. Every bookmark's pages are its
  lore, an entry of category "lore" (or what books.json's categories say: the introduction is "rule").
- **Every stat block is an entry** of category "monster", with its stats parsed (statblocks.parse) as well as its
  text. A stat block starts at "Armor Class" (with the size-and-type line above it), and ends at the next heading in
  capitals ("AARAKOCRA", a lore section) or the next stat block.
- **Its names come from the book's Index of Stat Blocks** ("Barbed Devil, 70"): the stat block's own name is in a
  display font the OCR often loses. Each stat block on a page takes the index's name for that page that's closest to
  whatever's above it, or the one left over.
- A monster's lair actions and regional effects are entries of their own ("Aboleth Lair Actions"), and the stat
  block says it has them.

The PDF's pages are the book's (the Monster Manual scan is complete), so page numbers are the PDF's, less
books.json's "page_offset" (pages before the book's page 1).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from lawyer.tools import rules_build as rb
from lawyer.tools import statblocks

LAIR = {"lairactions": "Lair Actions", "regionaleffects": "Regional Effects"}


@dataclass
class Bookmark:
    title: str
    page: int  # The PDF's page (0 = the first)
    depth: int
    parent: "Bookmark | None" = None
    children: list["Bookmark"] = field(default_factory=list)

    def path(self) -> list[str]:
        titles, node = [], self.parent
        while node:
            if not is_letter(node.title):
                titles.append(node.title)
            node = node.parent
        return titles[::-1]


def is_letter(title: str) -> bool:
    """The bestiary's "A", "B"... bookmarks: just the alphabet, not part of a monster's place in the book."""
    return len(title.strip()) == 1


@dataclass
class Block:
    """A stat block found on a page: its lines, and the name above it, if the OCR read one."""
    page: int
    lines: list[str]
    above: str
    name: str = ""


def read(pdf: Path) -> tuple[list[str], list[Bookmark]]:
    """Every page's text, and the bookmarks in order."""
    import pypdf
    reader = pypdf.PdfReader(pdf)
    marks: list[Bookmark] = []

    def walk(outline, depth, parent):
        last = parent
        for item in outline:
            if isinstance(item, list):
                walk(item, depth + 1, last)
                continue
            mark = Bookmark(str(item.title).strip(), reader.get_destination_page_number(item), depth, parent)
            if parent:
                parent.children.append(mark)
            marks.append(mark)
            last = mark
    walk(reader.outline or [], 0, None)
    return [page.extract_text() or "" for page in reader.pages], marks


def is_heading(line: str) -> bool:
    """A heading in capitals: "AARAKOCRA", "LAIR ACTIONS", "SUMMONING AIR ElEM .ENTALS". Not ACTIONS (a stat block's
    own), not an ability's "STR"."""
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 4 or statblocks.section_of(line) or len(line.split()) > 7:
        return False
    return sum(c.isupper() for c in letters) >= 0.75 * len(letters)


def find_blocks(page: int, text: str) -> tuple[list[Block], list[str]]:
    """The page's stat blocks, and the rest of its lines (its lore)."""
    lines = [l.rstrip() for l in text.splitlines()]
    starts = [i for i, l in enumerate(lines) if (found := statblocks.label_of(l)) and found[0] == "ac"]
    blocks, used = [], set()
    for n, at in enumerate(starts):
        begin = at - 1 if at and statblocks.is_type_line(lines[at - 1]) else at
        above = lines[begin - 1].strip() if begin and is_heading(lines[begin - 1]) else ""
        if above:
            begin -= 1
        end = starts[n + 1] - 1 if n + 1 < len(starts) else len(lines)
        for i in range(at + 4, end):  # A heading after the properties ends it: lore, or the next one's name
            if is_heading(lines[i]) and not statblocks.label_of(lines[i]):
                end = i
                break
        if n + 1 < len(starts):  # Don't take the next block's type line or name
            nxt = starts[n + 1]
            end = min(end, nxt - 1 if statblocks.is_type_line(lines[nxt - 1]) else nxt)
            if end and is_heading(lines[end - 1]):
                end -= 1
        blocks.append(Block(page, lines[begin + (1 if above else 0):end], above))
        used.update(range(begin, end))
    return blocks, [l for i, l in enumerate(lines) if i not in used]


def stat_block_index(pages: list[str], index_pages: list[int], words: rb.Words) -> dict[int, list[str]]:
    """The Index of Stat Blocks: page -> names. "Adult Copper Dragon , Ill" is page 111; "Barb ed Devil" is
    "Barbed Devil"; "Courtier. See Noble." is only a pointer."""
    found: dict[int, list[str]] = {}
    for number in index_pages:
        for line in pages[number].splitlines():
            match = re.fullmatch(rf"\s*(.+?)\s*[,.]\s*([{statblocks.DIGITISH} ]{{1,5}})\s*", line)
            if not match or "See " in line:
                continue
            page = statblocks.digits(match.group(2).replace(" ", ""))
            if not page.isdigit():
                continue
            name = rb.tidy_title(rb.repair(match.group(1), words))
            found.setdefault(int(page), []).append(name)
    return found


def letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def name_blocks(blocks: list[Block], index: dict[int, list[str]], offset: int) -> list[str]:
    """Give every stat block its name from the index; returns the index's names no stat block took."""
    by_page: dict[int, list[Block]] = {}
    for block in blocks:
        by_page.setdefault(block.page, []).append(block)
    unused = []
    for page, names in index.items():
        here = by_page.get(page + offset, [])
        left = list(names)
        for block in here:  # First, the ones whose own name the OCR read
            if block.above and left:
                best = max(left, key=lambda n: SequenceMatcher(None, letters(n), letters(block.above)).ratio())
                if SequenceMatcher(None, letters(best), letters(block.above)).ratio() >= 0.6:
                    block.name = best
                    left.remove(best)
        for block in here:  # Then the rest, in order
            if not block.name and left:
                block.name = left.pop(0)
        unused += left
    for block in blocks:  # Not in the index: its own name, if it has one
        if not block.name:
            block.name = block.above.title() if block.above else f"Unnamed creature (p. {block.page - offset})"
    return unused


def paragraphs(lines: list[str], words: rb.Words) -> list[tuple[str, str]]:
    """Lore lines as ("heading", title) and ("text", paragraph). A line in capitals on its own is a heading; several in
    a row are a quote's opening words. A paragraph ends at a run-in ("Eternal Memories. Aboleths have...")."""
    out: list[tuple[str, str]] = []
    para: list[str] = []

    def close():
        if para:
            text = rb.clean(rb.repair(rb.unbreak("\n".join(para)), words))
            if text:
                out.append(("text", text))
            para.clear()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or (len(stripped) <= 3 and re.search(r"\d", stripped)):
            continue  # Page numbers, as the OCR reads them: "12", "I2", "T4"
        caps_run = is_heading(stripped) and ((i and is_heading(lines[i - 1].strip()))
                                            or (i + 1 < len(lines) and is_heading(lines[i + 1].strip())))
        if is_heading(stripped) and not caps_run:
            close()
            out.append(("heading", rb.fix_title(rb.repair(rb.tidy_title(stripped.lower()), words), words)))
            continue
        run_in = statblocks.ITEM.match(stripped)
        if run_in and len(run_in.group(1).split()) <= 4 and para and re.search(r"[.!?]\s*$", para[-1]):
            close()
            para.append(f"**{statblocks.tidy(run_in.group(1))}.** {run_in.group(2)}")
            continue
        para.append(stripped)
    close()
    return out


def build(book_id: str, book: dict, pdf: Path) -> dict:
    pages, marks = read(pdf)
    offset = book.get("page_offset", 0)
    words = rb.Words(pages)
    categories = {rb.plain(k): v for k, v in book["categories"].items()}
    starts = sorted({m.page for m in marks})

    all_blocks: list[Block] = []
    lore_lines: dict[int, list[str]] = {}
    skip_pages = set(book.get("statblock_index_pages", []))
    for number, text in enumerate(pages):
        if number in skip_pages:
            continue
        blocks, rest = find_blocks(number, text)
        all_blocks += blocks
        lore_lines[number] = rest
    index = stat_block_index(pages, book.get("statblock_index_pages", []), words)
    unused = name_blocks(all_blocks, index, offset)

    def owner(page: int) -> Bookmark | None:
        """The deepest bookmark whose pages this is on."""
        here = [m for m in marks if m.page <= page]
        return max(here, key=lambda m: (m.page, m.depth)) if here else None

    def category_of(mark: Bookmark | None, default: str) -> str:
        while mark:
            if (found := categories.get(rb.plain(mark.title))) is not None:
                return found
            mark = mark.parent
        return default

    entries: list[dict] = []
    ids: Counter = Counter()

    def add(title: str, category: str, page: int, path: list[str], text: str, **more) -> dict:
        key = f"{book_id}.{category}.{rb.slug(title)}"
        ids[key] += 1
        if ids[key] > 1:
            key = f"{key}-{ids[key]}"
        entry = {"id": key, "edition": book["edition"], "source": book["source"], "book": book["title"],
                 "page": page - offset, "title": title, "category": category, "aliases": [], "path": path,
                 "sections": [], "text": text, **more}
        entries.append(entry)
        return entry

    # Lore: each bookmark's pages, up to the next bookmark's
    lore_of: dict[int, dict] = {}
    lairs: dict[str, list[str]] = {}
    for n, mark in enumerate(marks):
        category = category_of(mark, "lore")
        if category == "skip" or is_letter(mark.title):
            continue
        later = [p for p in starts if p > mark.page]
        pages_of = range(mark.page, later[0] if later else len(pages))
        if mark.children:
            pages_of = range(mark.page, min(c.page for c in mark.children) or mark.page + 1)
        lines = [l for p in pages_of for l in lore_lines.get(p, [])]
        sections, text, lair = [], [], None
        for kind, value in paragraphs(lines, words):
            if kind == "heading":
                lair = LAIR.get(rb.plain(value))
                if lair:
                    sections.append((lair, []))
                elif not letters(value) == letters(mark.title):
                    text.append(f"**{value}**")
                continue
            (sections[-1][1] if lair and sections else text).append(value)
        path = mark.path()
        entry = add(mark.title, category, mark.page, path, "\n\n".join(text))
        lore_of[id(mark)] = entry
        for name, body in sections:
            add(f"{mark.title} {name}", category, mark.page, path + [mark.title], "\n\n".join(body))
            entry["sections"].append(f"{mark.title} {name}")
            lairs.setdefault(rb.plain(mark.title), []).append(f"{mark.title} {name}")

    # Stat blocks: under the bookmark whose pages they're on
    for block in all_blocks:
        mark = owner(block.page)
        stats = statblocks.parse(block.lines, lambda t: rb.repair(t, words))
        category = "monster"
        path = (mark.path() + [mark.title]) if mark and not is_letter(mark.title) else []
        entry = add(block.name, category, block.page, path, statblocks.render(block.name, stats), stats=stats)
        if mark and id(mark) in lore_of:
            lore_of[id(mark)]["sections"].append(block.name)
        if mark and (found := lairs.get(rb.plain(mark.title))):
            stats["lair"] = found
    for mark in marks:  # A bookmark's sections: its own (lair, stat blocks), then the bookmarks under it
        if id(mark) in lore_of:
            lore_of[id(mark)]["sections"] += [c.title for c in mark.children if id(c) in lore_of]
            lore_of[id(mark)]["sections"] = list(dict.fromkeys(lore_of[id(mark)]["sections"]))
    return {"book": book_id, "source": book["source"], "title": book["title"], "edition": book["edition"],
            "entries": entries, "unmatched_index_names": unused}
