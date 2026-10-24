"""Books with headings in capitals (lawyer.tools.caps_build): Xanathar's and Tasha's, on made-up blocks and runs."""

from lawyer.tools import caps_build as cb
from lawyer.tools.rules_build import Block, Run, Words

BODY = "Times-Roman"


def heading(text, page, level=5):
    return Block("heading", text, level, page)


def text(words, page):
    return Block("text", words + "\n", page=page)


def test_headings_are_capitals_in_times():
    assert cb.heading_of([Run("PATH OF THE STORM", BODY, 10.3, 50, 300)], 9.5) == ("PATH OF THE STORM", 10.3)
    assert cb.heading_of([Run("TABLE TITLE", "Helvetica-Bold", 10, 50, 300)], 9.5) is None  # A table's
    assert cb.heading_of([Run("INFECTIOUS", BODY, 9, 50, 300), Run("FURY", "ArialMT", 8, 90, 300)], 9.5) \
        == ("INFECTIOUS FURY", 9)  # One word in Arial: still a heading
    assert cb.heading_of([Run("CHAPTER 1", BODY, 7, 50, 20)], 9.5) is None  # The footer
    assert cb.heading_of([Run("CHA", "Times-Bold", 9, 50, 300)], 9.5) is None  # A stat block's
    assert cb.heading_of([Run("TAA", "Times-Bold", 13, 50, 300)], 9.5, ignore=frozenset({"taa"})) is None


def test_run_in_over_several_runs():
    line = [Run("At", "Times-Italic", 10, 50, 300), Run("Higher", "Times-Italic", 10, 60, 300),
            Run("Levels.", "Times-Italic", 10, 90, 300), Run("When you cast", BODY, 9.5, 120, 300)]
    name, rest = cb.run_in_of(line)
    assert name == "At Higher Levels" and rest[0].text == "When you cast"


def test_respace():
    words = Words(["path of the zealot rakish audacity oath redemption storm herald"] * 5)
    assert cb.respace("r a kish audacity", words) == "rakish audacity"
    assert cb.respace("oath of re demp ti on", words) == "oath of redemption"
    assert cb.respace("path ofthe zealot", words) == "path of the zealot"  # Not "ofthe"
    assert cb.respace("storm herald", words) == "storm herald"  # Already words


def test_deeper_bookmarks_and_reown():
    """Tasha's: subclasses are bookmarked; a column read out of order puts the Fathomless's features under the Genie
    (whose title is only in the art, so it's put back at the top of its page), and each feature's own line moves it
    back."""
    blocks = [heading("Warlock", 1, 2),
              heading("The Fathomless", 1), text("Your patron is a sea thing.", 1),
              heading("Tentacle of the Deeps", 1), text("*1st-level Fathomless feature*", 1),
              heading("Oceanic Soul", 2), text("*6th-level Fathomless feature*", 2),
              heading("Genie’s Vessel", 2), text("*1st-level Genie feature*", 2),
              heading("Fathomless Plunge", 2), text("*4 th-level Fathomless feature*", 2)]
    marks = [(2, "The Fathomless", 1), (2, "The Genie", 2)]
    out = cb.deeper_bookmarks(blocks, marks, Words([""]))
    order = [(b.text, b.level) for b in out if b.kind == "heading"]
    assert order == [("Warlock", 2), ("The Fathomless", 3), ("Tentacle of the Deeps", 4), ("Oceanic Soul", 4),
                     ("Fathomless Plunge", 4), ("The Genie", 3), ("Genie’s Vessel", 4)]


def test_owner_key():
    assert cb.owner_key("The Fathomless") == cb.owner_key("Fathomless") == "fathomless"
