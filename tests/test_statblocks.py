"""Reading stat blocks from OCR text (lawyer.tools.statblocks), on made-up monsters written the way the scans read."""

from lawyer.tools import statblocks as sb

# A stat block as the Monster Manual's scan reads it: the ability column interleaved with other lines, digits read
# as letters ("1S", "Sd6", "SO XP", "ld4"), split words, and the OCR's spacing.
GRUB = """Small beast, unaligned
Armor Class 12 (natural armor)
Hit Points 9 (2d6 + 2)
Speed 20ft., burrow l0 ft.
STR
8 (-1)
DEX
1S (+2)
Skills Percept ion +2
CON
12 (+1)
Senses tremorsense 30 ft., passive Perception 1 2
Languages-
Challenge 1/4 (SO XP)
INT
2 (-4)
WIS
10 (+0)
Squishy . The grub is very squishy, and it takes a DC 10 Constitution
saving throw. On a failure it pops.
CHA
3 {-4)
ACTIONS
Nibble. Melee Weapon Attack:+ 4 to hit, reach 5 ft., one target.
Hit: 4 (ld4 + 2) piercing damage.
Spit (3JDay). The grub spits. Force damage. It's
gross.
LEGENDARY ACTIONS
The grub can take 3 legendary actions, choosing from the options below.
Wriggle. The grub moves.
Big Wriggle (Costs 2 Actions). The grub moves a lot.""".splitlines()


def test_parse():
    stats = sb.parse(GRUB)
    assert (stats["size"], stats["type"], stats["alignment"]) == ("Small", "beast", "unaligned")
    assert (stats["ac"], stats["ac_note"], stats["hp"], stats["hp_dice"]) == (12, "natural armor", 9, "2d6 + 2")
    assert stats["speed"] == "20 ft., burrow 10 ft."
    assert stats["abilities"] == {"str": 8, "dex": 15, "con": 12, "int": 2, "wis": 10, "cha": 3}
    assert stats["senses"] == "tremorsense 30 ft., passive Perception 12"
    assert "languages" not in stats  # "-": none
    assert (stats["cr"], stats["xp"]) == ("1/4", 50)
    assert [t["name"] for t in stats["traits"]] == ["Squishy"]
    assert stats["traits"][0]["text"].endswith("On a failure it pops.")  # "...Constitution saving throw." carries on
    assert [a["name"] for a in stats["actions"]] == ["Nibble", "Spit (3/Day)"]
    assert stats["actions"][0]["text"] == "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 4 (1d4 + 2) piercing damage."
    assert "Force damage. It's gross." in stats["actions"][1]["text"]  # Not an action called "Force damage"
    assert stats["legendary_intro"].startswith("The grub can take 3")
    assert [a["name"] for a in stats["legendary_actions"]] == ["Wriggle", "Big Wriggle (Costs 2 Actions)"]
    assert "checks" not in stats


def test_words_repairs_split_words():
    stats = sb.parse(GRUB, words=lambda text: text.replace("Percept ion", "Perception"))
    assert stats["skills"] == "Perception +2"


def test_checks_fix_what_adds_up():
    lines = ["Medium humanoid (any race), any alignment", "Armor Class 10", "Hit Points 9 (2d8 + 1)", "Speed 30 ft.",
             "STR DEX CON INT WIS CHA", "10 (+0) 12 (+1) 1O (+0) 18 (+2) 10 (+0) 10 (+0)", "Challenge 1/8 (2S XP)",
             "Club. Melee Weapon Attack: +2 to hit, reach 5 ft., one target. Hit: 2 (1d4) bludgeoning damage."]
    stats = sb.parse(lines)
    assert stats["hp"] == 10  # 2d8 + 1 averages 10: the 9 was misread
    assert stats["abilities"]["int"] == 15  # 18 doesn't have a +2 modifier; 14 and 15 do, and 15 is closer
    assert stats["xp"] == 25  # From the challenge rating, whatever the XP read as
    assert len(stats["checks"]) == 2
    assert [a["name"] for a in stats["actions"]] == ["Club"]  # No ACTIONS heading: the attack starts them


def test_problems_are_listed():
    stats = sb.parse(["Tiny beast, unaligned", "Armor Class 10", "Hit Points 1 (1d4 - 1)", "Speed 5 ft.",
                      "Challenge zzz"])
    assert "challenge rating not read: 'zzz'" in stats["checks"]
    assert "only 0 ability scores read" in stats["checks"]
    assert "no actions read" in stats["checks"]


def test_summon():
    """Tasha's summons: no alignment, hit points as a formula, and no challenge rating."""
    stats = sb.parse(["*Small elemental*", "Armor Class 13 (natural armor)",
                      "Hit Points 5 + five times your druid level", "Speed 30 ft., fly 30 ft. (hover)",
                      "STR", "10 (+0)", "DEX", "14 (+2)", "CON", "14 (+2)", "INT", "13 (+1)", "WIS", "15 (+2)",
                      "CHA", "11 (+0)", "Challenge — Proficiency Bonus equals your bonus", "ACTIONS",
                      "Flame Seed. Ranged Spell Attack: your spell attack modifier to hit, range 60 ft., one target."])
    assert (stats["size"], stats["type"], stats["alignment"]) == ("Small", "elemental", "")
    assert stats["hp"] == "5 + five times your druid level"
    assert stats["cr"] is None and "checks" not in stats
    assert sb.render("Wildfire Spirit", stats).startswith("*Small elemental*\n")


def test_fix_numbers():
    assert sb.fix_numbers("Hit: S (Sd6) and 1S ft. (SO XP) ld4 2IO") == "Hit: 5 (5d6) and 15 ft. (50 XP) 1d4 210"
    assert sb.fix_numbers("Some Ogres are Old") == "Some Ogres are Old"  # Words stay words


def test_type_lines():
    assert sb.is_type_line("11uge monstrosity, neutr.al evil")  # The OCR's "Huge"
    assert not sb.is_type_line("Damage Immunities poison, psychic")
    assert sb.parse_type("Medium fium'anoid (bullywug), neutral evil")["size"] == "Medium"


def test_average():
    assert sb.average("18d10 + 36") == 135
    assert sb.average("1d4 - 1") == 1
    assert sb.average("nonsense") is None


def test_render():
    text = sb.render("Grub", sb.parse(GRUB))
    assert text.startswith("*Small beast, unaligned*\n**Armor Class** 12 (natural armor)")
    assert "**DEX** 15 (+2)" in text and "**Challenge** 1/4 (50 XP)" in text
    assert "__**Legendary Actions**__\n\nThe grub can take 3" in text
