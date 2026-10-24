"""Build a rulebook's entries for /rule from its PDF: python -m lawyer.tools.rules_build phb [--pdf path]

Reads the PDF named in lawyer/lib/books.json (from books/, unless --pdf says otherwise) and writes rules/<id>.json:
every heading in the book as an entry, with where it came from (book, edition, printed page, chapter and section) and
its text. Neither the PDFs nor rules/ are ever committed: the books are the maintainer's own copies.

How a page is read (the books are scans with an OCR text layer, but the fonts survived):
- Headings are small caps: a capital in one size, then the rest of the word, letter-spaced, a size smaller
  ("P" + "o i s o n e d"). The capital's size is the heading's level: chapters are biggest, conditions and spells
  smallest. Each heading is an entry.
- Run-in rules start a paragraph in italic and end with a full stop ("Carrying Capacity. Your Strength score...").
  Each is an entry too, under its heading, and part of its heading's text.
- OCR splits words ("m ore", "w ilderness", "o f"); repair() joins the pieces back up when the joined word is one the
  book uses and a piece isn't. It loses some characters for good (dashes and apostrophes all come out as one unknown
  character), which clean() guesses back from context.
- The PDF's pages aren't the book's (blank and art pages were dropped from the scan), so printed page numbers come
  from the book's own contents page: each chapter and section it lists is found among the headings, and the pages
  between are counted on from there.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lawyer.tools import statblocks

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BOOKS_FILE = BASE_DIR / "lawyer" / "lib" / "books.json"
ALIASES_FILE = BASE_DIR / "lawyer" / "lib" / "aliases.json"
PDF_DIR = BASE_DIR / "books"
RULES_DIR = BASE_DIR / "rules"

SMALL_CAPS = 0.9  # The rest of a small-caps word is at most this size against its capital (they're about 0.8).
LONGEST_HEADING = 60  # Characters; a longer "heading" is a sentence in small caps, not a heading.
SMALLEST_HEADING = 7  # A heading's capital is at least this size; smaller small caps are a quote's opening words.
LONGEST_WORD = 16  # Letters; a "word" longer than this is table text the OCR ran together ("1ifleecedthewrong").
CARRY_ON = {"and", "of", "or", "the", "a", "to", "with", "for", "in"}  # A heading ending in one goes on a second line
LONGEST_RUN_IN = 8  # Words in a run-in rule's name ("Push, Drag, or Lift.").
LEVELS = [(15, 1), (12, 2), (10, 3), (8.5, 4), (0, 5)]  # A heading's capital size -> its level (1 = a chapter)
RUN_IN = 6  # The level of a run-in rule: under every heading.
COMMON_RUN_IN = 4  # A run-in name used more often than this is a label ("At Higher Levels."), not a rule.
UNKNOWN = "�"  # What the OCR's dashes, apostrophes and bullets all come out as.


@dataclass
class Run:
    """A piece of text as the PDF draws it, in one font and size."""
    text: str
    font: str
    size: float
    x: float
    y: float

    @property
    def italic(self) -> bool:
        return "Italic" in self.font

    @property
    def letter_spaced(self) -> bool:
        """Small caps' lower half: "o i s o n e d", "a r r y i n g" (mostly one-letter pieces)."""
        pieces = self.text.split()
        return len(pieces) >= 2 and sum(len(p) == 1 for p in pieces) >= 0.6 * len(pieces)


@dataclass
class Block:
    """A heading, run-in rule or line of text, in reading order."""
    kind: str  # "heading", "run_in" or "text"
    text: str
    level: int = 0
    page: int = 0  # The PDF's page (0 = the first)
    x: float = 0.0
    starts: bool = False  # Starts a paragraph of its own (a spell's "Range:", its school)


@dataclass
class Node:
    title: str
    level: int
    page: int
    parent: "Node | None"
    lines: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    run_in: bool = False

    def path(self) -> list[str]:
        node, titles = self.parent, []
        while node and node.parent:
            titles.append(node.title)
            node = node.parent
        return titles[::-1]


def read_runs(pdf: Path) -> list[list[Run]]:
    """Every page's runs, in the order the PDF draws them (which, for these scans, is reading order)."""
    import pypdf  # Only the build needs it; the bot just reads the JSON this writes.
    reader = pypdf.PdfReader(pdf)
    pages = []
    for page in reader.pages:
        runs: list[Run] = []

        def visit(text, cm, tm, font, size, runs=runs):
            if text.strip():
                name = str(font.get("/BaseFont", "")).lstrip("/") if font else ""
                runs.append(Run(text, name, round(size * tm[3] * cm[3], 1), tm[4] * cm[0] + cm[4],
                                tm[5] * cm[3] + cm[5]))
        page.extract_text(visitor_text=visit)
        pages.append(runs)
    return pages


def lines_of(runs: list[Run]) -> list[list[Run]]:
    """Runs grouped into the lines they're drawn on. A run can end a line ("...through \\n")."""
    lines, line = [], []
    for run in runs:
        last = line[-1] if line else None
        # Where the last run ends, roughly: two columns' headings can be drawn at the same height ("Grappler" and
        # "Inspiring Leader"), one after the other.
        gap = run.x - (last.x + len(last.text) * last.size * 0.6) if last else 0
        if last and (abs(run.y - last.y) > 2 or last.text.endswith("\n") or gap > 40 or run.x < last.x - 1):
            lines.append(line)
            line = []
        line.append(run)
    if line:
        lines.append(line)
    return lines


def despace(text: str) -> str:
    """Letter-spaced small caps back into words: "o u n t s  a n d" -> "ounts and"."""
    return " ".join(word.replace(" ", "") for word in re.split(r"\s{2,}", text.strip()))


def capital_before(line: list[Run], i: int) -> bool:
    """Whether run i is the rest of a small-caps word whose capital ends the run before ("M" "o u n t s", "3: C"
    "lasses")."""
    return bool(i) and line[i].size <= line[i - 1].size * SMALL_CAPS and not line[i].text.startswith("  ") \
        and re.search(r"(^|[^A-Za-z])[A-Z]$", line[i - 1].text.strip()) is not None


def heading_of(line: list[Run]) -> tuple[str, float] | None:
    """(title, capital size) if the line is a small-caps heading. Each capital starts a word, and the smaller run
    after it is the rest of that word; a smaller, letter-spaced run with no capital before it is a word of its own
    ("a n d"), or one whose capital the OCR lost ("V" "a r i a n t" "n c u m b r a n c e")."""
    if any(run.italic for run in line) or len(line) < 2:
        return None
    big = max(run.size for run in line)
    if big < SMALLEST_HEADING:
        return None
    small_caps = [capital_before(line, i) or (run.size <= big * SMALL_CAPS and run.letter_spaced)
                  for i, run in enumerate(line)]
    if not any(small_caps):
        return None
    # Every run is part of the heading: small caps, a capital (or "3:", "-"), or bold. Not "game is to imagine".
    if not all(s or len(r.text.strip()) <= 4 or "Bold" in r.font or re.search(r"[A-Z]$", r.text.strip())
               for s, r in zip(small_caps, line)):
        return None
    words: list[str] = []
    for i, run in enumerate(line):
        text = run.text.strip()
        if not text:
            continue
        pieces = despace(text).split(" ")
        if capital_before(line, i) and words:
            words[-1] += pieces[0].lower()
            pieces = pieces[1:]
        words += pieces
    title = tidy_title(" ".join(w for w in words if w))
    if "," in title:
        return None  # A paragraph's opening words in small caps ("In the Dungeons & Dragons game, each player")
    if not re.match(r"(Chapter|Appendix)\b", title) and (re.match(r"\d[a-z]", title) or re.search(r"\s\d", title)):
        return None  # A table's row: "1i’m trying to pay off", "1forester 6 Bountyhunter"
    if any(len(re.sub(r"[^A-Za-z]", "", w)) > LONGEST_WORD for w in title.split()):
        return None
    letters = sum(c.isalpha() for c in title)
    if not letters or len(title) > LONGEST_HEADING or letters < 0.6 * len(title.replace(" ", "")):
        return None
    return title, big


def tidy_title(title: str) -> str:
    """Spacing around punctuation as the book prints it: "3:C lasses" -> "3: C lasses", "Half -Elf" -> "Half-Elf",
    "Hawk (falcon )" -> "Hawk (falcon)", "What Is a Spell ?" -> "What Is a Spell?"."""
    title = re.sub(r"\s*([-/])\s*", r"\1", title)
    title = re.sub(r"(\w)\s+([’'])(\s|$)", r"\1\2\3", title)  # "Thieves ' Tools"
    title = re.sub(r"\s*:\s*", ": ", title)
    title = re.sub(r"\(\s+", "(", re.sub(r"\s+([)?!.])", r"\1", title))
    return re.sub(r"\s+", " ", title).strip()


def level_of(size: float) -> int:
    return next(level for least, level in LEVELS if size >= least)


def run_in_of(line: list[Run]) -> tuple[str, str] | None:
    """(name, the rest of the line) if the line starts a run-in rule: "Barding." in italic, then the text."""
    first = line[0]
    name = first.text.strip()
    if not (first.italic and first.size >= 8 and name.endswith(".") and name[0].isupper()):
        return None
    if len(name.split()) > LONGEST_RUN_IN + 3:  # Allowing for OCR splits ("V ehicle P roficien cy.")
        return None
    return name[:-1].strip(), "".join(run.text for run in line[1:])


def blocks_of(pages: list[list[Run]]) -> list[Block]:
    blocks = []
    for number, runs in enumerate(pages):
        for line in lines_of(runs):
            if heading := heading_of(line):
                title, size = heading
                last = blocks[-1] if blocks else None
                if last and last.kind == "heading" and last.page == number and last.level == level_of(size) \
                        and last.text.split()[-1].lower() in CARRY_ON:  # "Ability Scores and" / "Modifiers"
                    last.text += " " + title
                    continue
                blocks.append(Block("heading", title, level_of(size), number, line[0].x))
            elif run_in := run_in_of(line):
                name, rest = run_in
                blocks.append(Block("run_in", name, RUN_IN, number, line[0].x))
                if rest.strip():
                    blocks.append(Block("text", rest, page=number, x=line[1].x))
            else:
                text = "".join(despace(r.text) + (" " if r.text.endswith(" ") else "") if r.letter_spaced else r.text
                               for r in line)
                first = line[0]
                label = first.text.strip()
                starts = False
                if "Bold" in first.font and not first.italic and re.fullmatch(r"[A-Z][\w ]+:( \d+)?", label):
                    # A spell's "Casting Time: 1 action", a background's "Skill Proficiencies: ..."
                    name, _, rest = label.partition(":")
                    text = f"**{name.strip()}:**{rest} " + "".join(r.text for r in line[1:])
                    starts = True
                elif first.italic and blocks and blocks[-1].kind == "heading":
                    text = f"*{text.strip()}*\n"  # A spell's school, a feat's prerequisite: just under the heading
                    starts = True
                blocks.append(Block("text", text, page=number, x=first.x, starts=starts))
    return blocks


# Repairing the OCR's words

# Short words that sit side by side in plain English, so two of them aren't one word split ("a way", "in to").
COMMON = set("""a an the and or but nor of in on at to by for from with as is are was were be been it its this that
these those he she they we you i me my your our their his her him them us no not so if do does did can may might must
shall will would should could has have had one two any some all each every way out up off over how what when where
who why which there here then than too very own same other into onto upon set per via ever more most less few""".split())


class Words:
    """How often the book uses each word, and each pair of words side by side, as the OCR read them."""

    def __init__(self, texts):
        self.count, self.pairs = Counter(), Counter()
        for text in texts:
            words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
            self.count.update(words)
            self.pairs.update(zip(words, words[1:]))
        # How often each word is half of a split one: "m" in "m ore", "determ" in "determ ines".
        self.halves = Counter()
        for (a, b), times in self.pairs.items():
            if self.count[a + b]:
                self.halves[a] += times
                self.halves[b] += times

    def fragment(self, piece: str) -> bool:
        """Half a word, not a word: a letter on its own (but "a" and "I"), or mostly seen as half of a split word."""
        low = piece.lower()
        if low in COMMON:
            return False
        return len(low) == 1 or self.halves[low] * 2 >= self.count[low]

    def __getitem__(self, word: str) -> int:
        return self.count[word]

    def __iter__(self):
        return iter(self.count)


def vocabulary(blocks: list[Block]) -> Words:
    return Words(b.text for b in blocks if b.kind == "text")


def rare(piece: str, words: Words) -> bool:
    """Not a word the book uses on its own: half of a split word, or seen less than three times."""
    low = piece.lower()
    return low not in COMMON and (words.fragment(low) or words[low] < 3)


def known(word: str, words: Words) -> bool:
    """A word the book prints whole ("damage"), not just a piece of a bigger one ("overw" of "overw helm")."""
    return words[word.lower()] > 0 and not words.fragment(word)


def joins(pieces: list[str], words: Words) -> bool:
    """Whether these pieces are one word the OCR split: "dam age", "su ccessfu l", "m ines". Either the book prints
    the word whole and a piece isn't a word (or the book prints the word whole about as often as it has the pieces
    side by side, and they aren't everyday words: "a way" stays), or it's a letter and a piece of a word."""
    low = [p.lower() for p in pieces]
    joined = "".join(low)
    if low[0] in COMMON and len(low[0]) > 1 and len(low[1]) == 1:
        return False  # "the s ta rt": the letter starts the next word ("start"), it doesn't end "the"
    if len(low) == 2 and len(low[0]) == 1 and low[0] not in ("a", "i") and low[1] not in COMMON \
            and (words.fragment(low[1]) or words[low[1]] < 10):
        return True  # "m ines", "w eeks": a first letter on its own, and the rest
    if len(low) == 2 and len(low[1]) == 1 and low[1] not in ("a", "i") and low[0] not in COMMON \
            and words[low[0]] < 20 and low[0].isalpha():
        return True  # "spectra l", "storin g": a word's last letter on its own
    if not known(joined, words) or (len(low) == 3 and words[joined] < 2):
        return False
    if any(words.fragment(p) for p in low):
        return True
    if all(p in COMMON for p in low):
        return False
    together = min(words.pairs[(a, b)] for a, b in zip(low, low[1:]))
    return words[joined] * 4 >= together


def resplit(a: str, b: str, words: Words) -> tuple[str, str] | None:
    """Two words split in the wrong place ("tow orry" -> "to worry", "nom ore" -> "no more", "Aw rong" -> "A wrong",
    "as pell" -> "a spell", "thesta rt" -> "the start"): the second piece isn't a word (nor, unless it's an everyday
    one, the first), and moving the split makes an everyday word and one the book uses."""
    joined = a + b
    first_ok = rare(a, words) or a.lower() in COMMON or len(a) <= 2  # "ac reature": "AC" is a word, but not here
    if not (first_ok and rare(b, words)) or known(joined, words) or (len(b) < 2 and a.lower() in COMMON):
        return None

    def used(word: str) -> bool:  # Not known(): "start" is often half of a split word, but it's a word
        return words[word.lower()] >= 3

    best = None
    for cut in range(1, len(joined)):
        x, y = joined[:cut], joined[cut:]
        if cut == len(a):
            continue
        if (x.lower() in COMMON and used(y)) or (y.lower() in COMMON and used(x)):
            score = min(words[x.lower()], words[y.lower()])
            if best is None or score > best[0]:
                best = (score, x, y)
    return (best[1], best[2]) if best else None


def unseen(a: str, b: str, words: Words) -> bool:
    """A word the book never prints whole, split in two pieces that aren't words: "Venom ous"."""
    return rare(a, words) and words.fragment(b) and not known(a + b, words)


GAP = re.compile(r" {1,2}\n?|\n")  # Between a split word's pieces: a space or two, or the line's end


def repair(text: str, vocab: Words) -> str:
    """Join words the OCR split: "the w ilderness" -> "the wilderness", "dam age" -> "damage", "su ccessfu l" ->
    "successful", and move a split to where it belongs ("tow orry" -> "to worry")."""
    text = re.sub(r"(\w) ?([’']) s\b", r"\1\2s", text)  # "Land ’ s Stride", "city’ s"
    # "team s": a plural's s, when the book has the plural (not "the s ta rt", which is "the start")
    text = re.sub(r"\b([A-Za-z]+) s\b", lambda m: m.group(1) + "s" if vocab[m.group(1).lower() + "s"]
                  and m.group(1).lower() not in COMMON else m.group(0), text)
    tokens = re.split(r"(\s+)", text)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        word = re.fullmatch(r"([A-Za-z]+)(\W*)", tokens[i])
        if word and not word.group(2):
            done = False
            for count in (3, 2):  # Pieces: up to three
                end = i + 2 * (count - 1)
                if end >= len(tokens) or any(not GAP.fullmatch(tokens[k]) for k in range(i + 1, end, 2)):
                    continue
                last = re.fullmatch(r"([A-Za-z]+)(.*)", tokens[end], re.S)
                if not last or any(not tokens[k].isalpha() for k in range(i, end, 2)):
                    continue
                pieces = [tokens[k] for k in range(i, end, 2)] + [last.group(1)]
                if joins(pieces, vocab):
                    out.append("".join(pieces) + last.group(2))
                    i = end + 1
                    done = True
                    break
                if count == 2 and (split := resplit(pieces[0], pieces[1], vocab)):
                    out.append(f"{split[0]} {split[1]}{last.group(2)}")
                    i = end + 1
                    done = True
                    break
                if count == 2 and unseen(pieces[0], pieces[1], vocab):
                    out.append("".join(pieces) + last.group(2))
                    i = end + 1
                    done = True
                    break
            if done:
                continue
        out.append(tokens[i])
        i += 1
    return "".join(out)


def unjoin(word: str, vocab: Words) -> str:
    """Words the OCR ran together, split where the book's own words fit best: "Abilityscoreimprovement" -> "Ability
    score improvement", "Creatinga" -> "Creating a". A word the book uses as it is stays as it is."""
    letters = word.lower()
    # Long run-togethers ("abilityscoreimprovement"), and a word with "a" stuck on ("creatinga"); a shorter word the
    # book seldom uses ("signature", "menacing") is a word, not two.
    if not letters.isalpha() or not (len(letters) >= 12 or (letters.endswith("a") and vocab[letters[:-1]] >= 5)):
        return word
    best: list[list[str] | None] = [[]] + [None] * len(letters)  # Fewest pieces that spell letters[:i]
    for end in range(1, len(letters) + 1):
        for start in range(max(0, end - 20), end):
            piece = letters[start:end]
            ok = vocab[piece] >= 5 and (len(piece) > 2 or piece in COMMON) and not vocab.fragment(piece)
            if ok and best[start] is not None and (best[end] is None or len(best[start]) + 1 < len(best[end])):
                best[end] = best[start] + [piece]
    pieces = best[-1]
    if not pieces or len(pieces) < 2 or vocab[letters] * 2 >= min(vocab[p] for p in pieces):
        return word
    return " ".join(pieces).capitalize() if word[0].isupper() else " ".join(pieces)


def fix_title(title: str, vocab: Words) -> str:
    """A heading's words as the book means them: lost capitals put back where the book uses the word ("ncumbrance"
    -> "Encumbrance"), and each word capitalised the way the book's title case does ("of", "and" stay small)."""
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}
    words = []
    # "Devil ’ S Sight", "Dark One ’ Sblessing": a possessive the OCR spaced out
    title = re.sub(r"\s*[’']\s*[Ss]([a-z])", lambda m: "’s " + m.group(1).upper(), title)
    title = re.sub(r"\s*[’']\s*[Ss](?=\s|$)", "’s", title)
    title = " ".join(unjoin(word, vocab) for word in title.split())
    for n, word in enumerate(title.split()):
        low = word.lower()
        letters = re.sub(r"[^a-z]", "", low)
        if letters and vocab[letters] == 0 and len(letters) > 3:  # Its capital went missing: "ncumbrance"
            guesses = [w for w in vocab if len(w) == len(letters) + 1 and w[1:] == letters]
            if guesses:
                low = low.replace(letters, max(guesses, key=vocab.__getitem__), 1)
        after_colon = n and words[-1].endswith(":")
        if sum(c.isupper() for c in word) >= 2 and not word.isalpha():
            words.append(word)  # "D&D"
        else:
            words.append(low if n and low in small and not after_colon else low[:1].upper() + low[1:])
    return tidy_title(" ".join(words))


def clean(text: str) -> str:
    """Tidy a paragraph: lines joined, hyphenated words joined, the OCR's unknown character guessed back (an
    apostrophe in "it's", a dash anywhere else, a bullet at the start), and spacing evened out."""
    text = re.sub(rf"(\w){UNKNOWN}(s|t|d|ll|re|ve|m)\b", r"\1’\2", text)
    text = re.sub(rf"(^|\n)\s*{UNKNOWN}\s*", r"\1• ", text)
    text = text.replace(UNKNOWN, "—").replace("\n", " ")
    text = re.sub(r" +([,.;:!?)])", r"\1", text)
    text = re.sub(r"(\w) ([’'])(t|s|re|ve|ll|d|m)\b", r"\1\2\3", text)  # "isn 't"
    text = re.sub(r"(?<![A-Za-z])[lI]d(\d)", r"1d\1", text)  # "ld6": the OCR's l for 1
    text = re.sub(r"(\d) ?d ?(\d+)\b", r"\1d\2", text)  # "1 d6"
    return re.sub(r"\s+", " ", text).strip()


def paragraphs(blocks: list[Block], vocab: Words) -> list[str]:
    """A heading's lines as paragraphs. A new one starts with a bullet, a label (a spell's "Range:") or a run-in
    rule, or with a line indented past the one before when that one finished a sentence (a bullet's second line is
    indented too, and a column's first line is anywhere)."""
    paras: list[list[str]] = []
    last: Block | None = None
    for block in blocks:
        text = block.text
        ended = last is not None and re.search(r"[.:!?)”\"*]\s*$", last.text) is not None
        # After a label ("Components: V, S, M (a tiny ball of bat"), a new paragraph, unless its brackets are open.
        after_label = last is not None and last.starts and last.text.count("(") <= last.text.count(")")
        starts = block.starts or after_label or text.lstrip().startswith(UNKNOWN) \
            or text.startswith("**") or (ended and last is not None and 5 <= block.x - last.x <= 30)
        if not paras or starts:
            paras.append([])
        paras[-1].append(text if text.endswith("\n") else text + "\n")
        last = block
    return [p for p in (clean(repair(unbreak("".join(lines)), vocab)) for lines in paras) if p]


def unbreak(text: str) -> str:
    """Words hyphenated across lines joined back up: "imagina-\\ntion", "mini\\xad\\nm ize"."""
    text = re.sub(rf"(\w)[{UNKNOWN}\xad-]\n(\w)", r"\1\2", text)
    return text.replace("\xad\n", "").replace("\xad", "")


# Printed page numbers

def plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text.lower()))


@dataclass
class Contents:
    """A line of the book's contents page: "Worlds of Adventure ....... 5". Chapters (and the introduction,
    appendices...) are letter-spaced there; the sections under them aren't."""
    title: str
    page: int
    chapter: bool


def contents(pages: list[list[Run]], contents_pages: list[int]) -> list[Contents]:
    found = []
    for number in contents_pages:
        for line in lines_of(pages[number - 1]):
            text = "".join(r.text for r in line).strip()
            if match := re.fullmatch(r"(.*?\D)[\s.]*?(\d{1,3})", text):
                title = match.group(1).strip(" .")
                if re.fullmatch(r"P ?a ?r ?t\s+\d", title):
                    continue  # "Part 1": the book's parts aren't sections
                chapter = any(r.letter_spaced for r in line) or bool(re.match(r"C ?h ?a ?p|A ?p ?p ?e", title))
                found.append(Contents(title, int(match.group(2)), chapter))
    return found


def contents_title(title: str, vocab: Words) -> str:
    """A contents line's title in words: "H alf-O rc" -> "Half-Orc", "B a rd" -> "Bard"."""
    title = re.sub(r"(^|\s|-)([A-Z]) ([a-z])", r"\1\2\3", title)
    return fix_title(repair(title, vocab), vocab)


def restructure(blocks: list[Block], toc: list[Contents], numbers: list[int], vocab: Words) -> list[Block]:
    """The book's own outline, from its contents page: what it lists as a section is a section (level 2), under its
    chapter, and every other heading goes under one of them (level 3 or lower). A section whose heading the scan
    lost (Barbarian's title page) is put back at the start of its printed page, so what follows is still under it."""
    sections = {plain(c.title): c for c in toc if not c.chapter}
    found = set()
    for block in blocks:
        if block.kind != "heading":
            continue
        key = plain(block.text)
        if block.level == 1:
            found.add(key)  # "How to Play" is a chapter in its size, a section in the contents: either way, found
        elif key in sections and key not in found:
            block.level = 2
            found.add(key)
        else:
            block.level = max(block.level, 3)  # Including a section's name again (a table: "Weapons")
    out = list(blocks)
    for key, section in sections.items():
        if key in found or section.page not in numbers:
            continue
        pdf_page = numbers.index(section.page)
        at = next((i for i, b in enumerate(out) if b.page >= pdf_page), len(out))
        out.insert(at, Block("heading", contents_title(section.title, vocab), 2, pdf_page))
    return out


def page_numbers(blocks: list[Block], toc: list[Contents], page_count: int) -> list[int]:
    """Each PDF page's printed page number: anchored where a contents entry's heading is found, counted on from
    there, and never past the next anchor (the scan dropped pages, so the count drifts behind; the anchors catch it
    up)."""
    headings = [(b.page, plain(b.text)) for b in blocks if b.kind == "heading"]
    anchors: dict[int, int] = {}
    start = 0
    for line in toc:
        title, printed = line.title, line.page
        key = plain(title)
        if len(key) < 3:
            continue
        for pdf_page, heading in headings:
            if pdf_page >= start and (heading == key or (len(key) > 8 and heading.startswith(key))):
                if pdf_page not in anchors:
                    anchors[pdf_page] = printed
                start = pdf_page
                break
    numbers, current = [], 0
    upcoming = sorted(anchors.items())
    for pdf_page in range(page_count):
        if pdf_page in anchors:
            current = anchors[pdf_page]
        elif current:
            current += 1
            later = [printed for page, printed in upcoming if page > pdf_page]
            if later:
                current = min(current, later[0])
        numbers.append(current or pdf_page + 1)
    return numbers


# Entries

def tree(blocks: list[Block]) -> Node:
    root = Node("", 0, 0, None)
    node = root
    for block in blocks:
        if block.kind == "text":
            node.lines.append(block)  # type: ignore[arg-type]  # Blocks until paragraphs() makes them text
            continue
        parent = node
        while parent.parent and parent.level >= block.level:
            parent = parent.parent
        child = Node(block.text, block.level, block.page, parent, run_in=block.kind == "run_in")
        parent.children.append(child)
        node = child
    return root


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", text.lower())).strip("-")


def category_of(node: Node, book: dict) -> str:
    rules = {plain(k): v for k, v in book["categories"].items()}
    while node and node.parent:
        if (found := rules.get(plain(node.title))) is not None:
            return found
        node = node.parent
    return book["default_category"]


def entries(root: Node, book_id: str, book: dict, numbers: list[int], vocab: Words) -> list[dict]:
    """One entry per heading and run-in rule. A heading's text is its own paragraphs, run-in rules and all, up to the
    next heading; its "sections" are the headings under it, for /rule to offer."""
    found, ids = [], Counter()
    names = Counter(n.title.lower() for n in walk(root) if n.run_in)
    titles = Counter((category_of(n, book), n.title.lower()) for n in walk(root))

    def own_text(node: Node) -> list[Block]:
        blocks = list(node.lines)
        for child in node.children:
            if child.run_in:
                blocks.append(Block("text", f"**{child.title}.** ", page=child.page, x=10_000))
                blocks.extend(child.lines)
        return blocks

    for node in walk(root):
        category = category_of(node, book)
        if category == "skip" or not node.title:
            continue
        if node.run_in and (names[node.title.lower()] > COMMON_RUN_IN or category == "creature"):
            continue  # A label ("At Higher Levels."), or a creature's trait or action: part of its stat block
        stats = stat_block(node, vocab) if category == "creature" else None
        if stats:
            text = [statblocks.render(node.title, stats)]
        else:
            text = paragraphs(node.lines if node.run_in else own_text(node), vocab)
        sections = [c.title for c in node.children if not c.run_in]
        if not text and not sections:
            continue
        key = f"{book_id}.{category}.{slug(node.title)}"
        if titles[(category, node.title.lower())] > 1 and (qualifier := section_of(node)):
            key = f"{book_id}.{category}.{slug(qualifier)}.{slug(node.title)}"  # phb.class.fighter.extra-attack
        ids[key] += 1
        if ids[key] > 1:
            key = f"{key}-{ids[key]}"
        found.append({
            "id": key,
            "edition": book["edition"],
            "source": book["source"],
            "book": book["title"],
            "page": numbers[node.page],
            "title": node.title,
            "category": category,
            "aliases": [],
            "path": node.path(),
            "sections": sections,
            "text": "\n\n".join(text),
            **({"stats": stats} if stats else {}),
        })
    return found


def stat_block(node: Node, vocab: Words) -> dict | None:
    """A creature's stats, if its heading is a stat block: its lines, with its traits and actions (run-in rules,
    to the rest of the parser) put back as "Name. text" lines for statblocks.parse."""
    lines = [b.text for b in node.lines]
    for child in node.children:
        if child.run_in:
            rest = [b.text for b in child.lines]
            lines.append(f"{child.title}. {rest[0] if rest else ''}")
            lines += rest[1:]
    if not any(statblocks.label_of(line) for line in lines):
        return None
    return statblocks.parse([unbreak(line) for line in lines], lambda t: repair(t, vocab))


def section_of(node: Node) -> str | None:
    """The section an entry is in (Fighter, Combat's Actions in Combat), or its chapter if it's not in one; to tell
    apart entries with the same name."""
    ancestor = node.parent
    while ancestor and ancestor.parent and ancestor.level > 2:
        ancestor = ancestor.parent
    return ancestor.title if ancestor and ancestor.title and ancestor is not node else None


def walk(node: Node):
    for child in node.children:
        yield child
        yield from walk(child)


def build(book_id: str, pdf: Path | None = None) -> dict:
    book = json.loads(BOOKS_FILE.read_text(encoding="utf-8"))["books"][book_id]
    pdf = pdf or PDF_DIR / book["file"]
    if book.get("layout") == "monsters":
        from lawyer.tools import monsters_build
        return monsters_build.build(book_id, book, pdf)
    if book.get("layout") == "caps":
        from lawyer.tools import caps_build
        return caps_build.build(book_id, book, pdf)
    pages = read_runs(pdf)
    blocks = blocks_of(pages)
    vocab = vocabulary(blocks)
    for block in blocks:
        if block.kind != "text":
            block.text = fix_title(repair(block.text, vocab), vocab)
    toc = contents(pages, book.get("contents_pages", []))
    numbers = page_numbers(blocks, toc, len(pages))
    blocks = restructure(blocks, toc, numbers, vocab)
    return {"book": book_id, "source": book["source"], "title": book["title"], "edition": book["edition"],
            "entries": entries(tree(blocks), book_id, book, numbers, vocab)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a rulebook's /rule entries from its PDF.")
    parser.add_argument("book", help="the book's id in lawyer/lib/books.json, e.g. phb")
    parser.add_argument("--pdf", type=Path, help="the PDF, if it isn't books/<the file books.json names>")
    args = parser.parse_args(argv)
    built = build(args.book, args.pdf)
    RULES_DIR.mkdir(exist_ok=True)
    out = RULES_DIR / f"{args.book}.json"
    out.write_text(json.dumps(built, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = Counter(e["category"] for e in built["entries"])
    print(f"Wrote {len(built['entries'])} entries to {out.relative_to(BASE_DIR)}: "
          + ", ".join(f"{n} {c}" for c, n in counts.most_common()), file=sys.stderr)
    ids = {e["id"] for e in built["entries"]}
    aliases = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))["aliases"]
    for lost in sorted(k for k in aliases if k.startswith(f"{args.book}.") and k not in ids):
        print(f"  lawyer/lib/aliases.json names {lost}, which this book no longer has", file=sys.stderr)


if __name__ == "__main__":
    main()
