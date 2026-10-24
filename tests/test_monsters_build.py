"""Finding and naming stat blocks on a bestiary's pages (lawyer.tools.monsters_build), on made-up pages."""

from lawyer.tools import monsters_build as mb
from lawyer.tools.rules_build import Words

PAGE = """I2
GRUB
Small beast, unaligned
Armor Class 12
Hit Points 9 (2d6 + 2)
Speed 20 ft.
Challenge 1/4 (50 XP)
Nibble. Melee Weapon Attack: +4 to hit, reach 5 ft., one target.
GRUBS
Grubs live underground. They are squishy.
Squishy Lives. Grubs pop.
~0
Small beast, unaligned
Armor Class 13
Hit Points 9 (2d6 + 2)
Speed 20 ft.
Challenge 1/2 (100 XP)
Chomp. Melee Weapon Attack: +4 to hit, reach 5 ft., one target."""


def test_find_blocks():
    blocks, lore = mb.find_blocks(12, PAGE)
    assert [(b.above, b.lines[1]) for b in blocks] == [("GRUB", "Armor Class 12"), ("", "Armor Class 13")]
    assert "GRUBS" in lore and "Grubs live underground. They are squishy." in lore
    assert not any("Armor Class" in line for line in lore)


def test_index_names_the_blocks():
    index_page = "INDEX OF STAT BLOCKS\nGiant Gru b, l2\nGrub , 12\nCourtier. See Noble.\nWorm, 99"
    words = Words(["grub giant worm"] * 5)
    index = mb.stat_block_index([index_page], [0], words)
    assert index == {12: ["Giant Grub", "Grub"], 99: ["Worm"]}
    blocks, _ = mb.find_blocks(12, PAGE)
    unused = mb.name_blocks(blocks, index, 0)
    # The one whose name the OCR read takes it; the other takes what's left on its page
    assert [b.name for b in blocks] == ["Grub", "Giant Grub"]
    assert unused == ["Worm"]


def test_lore_paragraphs():
    lines = ["GRUBS", "Grubs live underground. They", "are squishy.", "Squishy Lives. Grubs pop.",
             "LAIR ACTIONS", "The grub's lair wobbles.", "T4"]
    out = mb.paragraphs(lines, Words(["grubs live underground they are squishy lives lair actions pop"] * 5))
    assert out == [("heading", "Grubs"), ("text", "Grubs live underground. They are squishy."),
                   ("text", "**Squishy Lives.** Grubs pop."), ("heading", "Lair Actions"),
                   ("text", "The grub's lair wobbles.")]


def test_footer_is_not_a_heading():
    assert mb.is_footer("44 Chapter 2 I Bestiary") and mb.is_footer("Io Chapter 1 I Fantastical Races")
    assert not mb.is_heading("44 CHAPTER 2 I BESTIARY")
    assert not mb.is_footer("GRUB TRAITS")


def test_names_from_bookmarks():
    """No index (Monsters of the Multiverse): a run-together name takes its bookmark's, in the stat block's order,
    and a lost one takes the page's bookmark no stat block has."""
    marks = [mb.Bookmark("Abishai, Red", 40, 1), mb.Bookmark("Grub", 41, 1)]
    blocks = [mb.Block(40, [], "REDABISHAI", "REDABISHAI"), mb.Block(41, [], "SWARM OF GRUBS", "SWARM OF GRUBS"),
              mb.Block(41, [], ""), mb.Block(90, [], "")]
    mb.name_from_bookmarks(blocks, marks, Words(["swarm of grubs"] * 5), 0)
    assert [b.name for b in blocks] == ["Red Abishai", "Swarm of Grubs", "Grub", "Unnamed creature (p. 90)"]


def test_quote_in_capitals_is_not_headings():
    lines = ["THE GRUB IS", "MIGHTY AND WISE", "Grubs live underground."]
    assert [kind for kind, _ in mb.paragraphs(lines, Words([""]))] == ["text"]
