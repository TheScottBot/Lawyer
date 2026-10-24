"""Building a rulebook's entries from its PDF (lawyer.tools.rules_build), on pages made up for the tests: runs of
text in the fonts and sizes the scans use, not the books themselves."""

import json

from lawyer.tools import rules_build as build
from lawyer.tools.rules_build import Block, Contents, Run, Words

BODY, SMALL, CAP = "CenturySchoolbook", 6.0, 7.5


def body(text, y, x=42.0):
    return Run(text + " \n", BODY, 7.5, x, y)


def heading(word_parts, y, x=42.0, cap=CAP):
    """Small caps: [("P", "o i s o n e d")] is "Poisoned", each capital a size up from the rest of its word."""
    runs = []
    for capital, rest in word_parts:
        runs.append(Run(capital, BODY, cap, x, y))
        runs.append(Run(" " + rest, BODY, cap * 0.8, x + 8, y))
        x += 60
    return runs


def test_small_caps_heading():
    line = heading([("L", "i f t i n g"), ("C", "a r r y i n g")], 500)
    line.insert(2, Run("a n d", BODY, SMALL, 151, 500))  # A small word: no capital
    assert build.heading_of(line) == ("Lifting and Carrying", CAP)


def test_chapter_heading_with_number():
    line = [Run("C", "CenturySchoolbook-Bold", 15.5, 38, 737), Run(" h apter", "CenturySchoolbook-Bold", 12.4, 54, 737),
            Run("  3: C", "CenturySchoolbook-Bold", 15.5, 128, 737), Run(" lasses", "CenturySchoolbook-Bold", 12.4, 175, 737)]
    title, size = build.heading_of(line)
    assert title == "Chapter 3: Classes" and build.level_of(size) == 1


def test_not_headings():
    # A paragraph's first words in small caps, then the paragraph itself
    opener = [Run("D", BODY, 6.5, 40, 300), Run(" u n g e o n s", BODY, 5.2, 48, 300), Run("game is to imagine", BODY, 7.5, 120, 300)]
    assert build.heading_of(opener) is None
    assert build.heading_of([body("Just a line of text.", 300)]) is None
    with_comma = heading([("I", "n"), ("T", "h e"), ("G", "a m e ,"), ("E", "a c h")], 300)
    assert build.heading_of(with_comma) is None


def test_run_in_rule():
    line = [Run("Carrying Capacity.", "CenturySchoolbook-Italic", 8.5, 116, 206), Run(" Your carrying capacity is \n", BODY, 7.5, 190, 206)]
    assert build.run_in_of(line) == ("Carrying Capacity", " Your carrying capacity is \n")
    assert build.run_in_of([Run("Player's Handbook", "CenturySchoolbook-Italic", 8.5, 40, 100)]) is None  # No stop


def test_two_columns_at_the_same_height_are_two_lines():
    runs = heading([("G", "r a p p l e r")], 500) + heading([("M", "o b i l e")], 500, x=360)
    assert [build.heading_of(line)[0] for line in build.lines_of(runs)] == ["Grappler", "Mobile"]


WORDS = Words(["the damage and more damage, damage again; more of the same, wrong or right, a long way, determines",
               "the m ore the dam age, dam age, determ ines, determ ines, to worry, no more, a wrong thing"] * 5)


def test_repair_joins_split_words():
    assert build.repair("the dam age", WORDS) == "the damage"
    assert build.repair("determ ines the m ore", WORDS) == "determines the more"
    assert build.repair("team s and city’ s", WORDS) == "teams and city’s"


def test_repair_moves_a_split():
    assert build.repair("have tow orry", WORDS) == "have to worry"
    assert build.repair("nom ore", WORDS) == "no more"


def test_repair_leaves_real_words():
    assert build.repair("a long way", WORDS) == "a long way"
    assert build.repair("the same", WORDS) == "the same"


def test_clean():
    assert build.clean("it�s a � test\nof lines") == "it’s a — test of lines"
    assert build.clean("� A poisoned creature") == "• A poisoned creature"
    assert build.unbreak("imagina�\ntion and mini\xad\nmize") == "imagination and minimize"


def test_fix_title():
    words = Words(["encumbrance encumbrance of the"])
    assert build.fix_title("variant: ncumbrance of the", words) == "Variant: Encumbrance of the"
    assert build.fix_title("Using D&D", words) == "Using D&D"
    assert build.fix_title("Devil ’ S Sight", words) == "Devil’s Sight"
    assert build.fix_title("Dark One ’ Sblessing", words) == "Dark One’s Blessing"


def page(*lines):
    return [run for line in lines for run in (line if isinstance(line, list) else [line])]


PAGES = [
    page(body("Contents", 740), Run("A p p e n d i x A :  C o n d i t i o n s 290", BODY, 7.5, 40, 700),
         body("Poisoned ................ 292", 690)),
    page(heading([("A", "p p e n d i x"), ("A", ":"), ("C", "o n d i t i o n s")], 740, cap=15.5),
         heading([("B", "l i n d e d")], 700), body("• A blinded creature can’t see.", 690)),
    page(heading([("P", "o i s o n e d")], 700), body("• A poisoned creature has disadvantage on attack rolls", 690),
         Run("and ability checks.\n", BODY, 7.5, 50, 680)),
]
BOOK = {"source": "TB", "title": "Test Book", "edition": "5e-2014", "default_category": "rule",
        "contents_pages": [1], "categories": {"Appendix A: Conditions": "condition", "Contents": "skip"}}


def test_entries_from_pages():
    blocks = build.blocks_of(PAGES)
    words = build.vocabulary(blocks)
    toc = build.contents(PAGES, [1])
    assert [(c.title.replace(" ", ""), c.page) for c in toc] == [("AppendixA:Conditions", 290), ("Poisoned", 292)]
    numbers = build.page_numbers(blocks, toc, len(PAGES))
    assert numbers[1:] == [290, 292]  # Anchored by the contents page: the scan dropped page 291
    found = build.entries(build.tree(build.restructure(blocks, toc, numbers, words)), "tb", BOOK, numbers, words)
    poisoned = next(e for e in found if e["title"] == "Poisoned")
    assert poisoned == {"id": "tb.condition.poisoned", "edition": "5e-2014", "source": "TB", "book": "Test Book",
                        "page": 292, "title": "Poisoned", "category": "condition", "aliases": [],
                        "path": ["Appendix A: Conditions"], "sections": [],
                        "text": "• A poisoned creature has disadvantage on attack rolls and ability checks."}
    assert next(e for e in found if e["title"] == "Blinded")["id"] == "tb.condition.blinded"


def test_missing_section_is_put_back():
    """A section the contents lists whose heading the scan lost (Barbarian's title page) goes back on its page."""
    blocks = [Block("heading", "Chapter 3: Classes", 1, 0), Block("text", "Classes intro.", page=0),
              Block("text", "Rage stuff.", page=1), Block("heading", "Rage", 5, 1)]
    toc = [Contents("Chapter 3: Classes", 45, True), Contents("Barbarian", 46, False)]
    out = build.restructure(blocks, toc, [45, 46], Words(["barbarian"]))
    assert [(b.kind, b.text, b.level) for b in out if b.kind == "heading"] == [
        ("heading", "Chapter 3: Classes", 1), ("heading", "Barbarian", 2), ("heading", "Rage", 5)]


def test_same_name_in_two_sections_gets_qualified_ids():
    root = build.Node("", 0, 0, None)
    classes = build.Node("Chapter 3: Classes", 1, 0, root)
    root.children.append(classes)
    for name in ("Fighter", "Monk"):
        cls = build.Node(name, 2, 0, classes)
        classes.children.append(cls)
        feature = build.Node("Extra Attack", 5, 0, cls)
        feature.lines.append(Block("text", f"{name} attacks twice.", page=0))
        cls.children.append(feature)
    book = {**BOOK, "categories": {"Chapter 3: Classes": "class"}}
    found = build.entries(root, "tb", book, [45], Words([""]))
    assert [e["id"] for e in found if e["title"] == "Extra Attack"] == ["tb.class.fighter.extra-attack",
                                                                       "tb.class.monk.extra-attack"]


def test_books_file():
    books = json.loads(build.BOOKS_FILE.read_text(encoding="utf-8"))["books"]
    for book_id, book in books.items():
        assert {"source", "title", "edition", "file", "default_category", "categories"} <= set(book), book_id
        assert book_id.isalnum() and book_id.islower()
