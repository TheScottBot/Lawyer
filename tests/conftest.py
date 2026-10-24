"""Shared test setup: never read the real .env, and a small made-up rulebook in place of the real ones.

Run the tests with:  python -m pytest

The real books (books/ and rules/) are never committed, so no test may need them. BOOK below is a stand-in with the
same shape, written for the tests: its text isn't the rulebooks' own.
"""

import os

# Before importing lawyer: never read the real .env, and don't pick up settings from the environment.
os.environ["LAWYER_NO_DOTENV"] = "1"
for name in ("GUILD_IDS", "COMMAND_PREFIX", "RULES_DIR", "DB_PATH"):
    os.environ.pop(name, None)

import pytest  # noqa: E402

from lawyer import db  # noqa: E402
from lawyer.features import rule  # noqa: E402
from lawyer.lib.rulebook import Entry, Rulebook  # noqa: E402


def entry(id, title, category, page, text, path=(), sections=(), aliases=(), stats=None):
    return Entry(id=id, title=title, source="TB", book="Test Book", edition="5e-2014", page=page, category=category,
                 text=text, path=list(path), sections=list(sections), aliases=list(aliases), book_id="tb",
                 stats=stats)


GRUB = {"size": "Small", "type": "beast", "alignment": "unaligned", "ac": 12, "ac_note": "natural armor", "hp": 9,
        "hp_dice": "2d6 + 2", "speed": "20 ft., burrow 10 ft.",
        "abilities": {"str": 8, "dex": 14, "con": 12, "int": 2, "wis": 10, "cha": 3},
        "senses": "tremorsense 30 ft., passive Perception 10", "cr": "1/4", "xp": 50,
        "traits": [{"name": "Squishy", "text": "The grub is very squishy."}],
        "actions": [{"name": "Nibble", "text": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 4 (1d4 + 2) piercing damage."}]}
WYRM = {**GRUB, "size": "Gargantuan", "type": "dragon", "hp": 300, "cr": "20", "xp": 25000,
        "actions": [{"name": f"Bite {n}", "text": "A long attack. " * 60} for n in range(8)],
        "legendary_intro": "The wyrm can take 3 legendary actions.",
        "legendary_actions": [{"name": "Tail", "text": "It swishes."}], "lair": ["Wyrm Lair Actions"]}
CLASSES = ["Chapter 3: Classes"]
KNIGHT = CLASSES + ["Knight"]
RACES = ["Chapter 2: Races"]


COMBAT = ["Chapter 9: Combat"]
BOOK = [
    entry("tb.rule.chapter-9-combat", "Chapter 9: Combat", "rule", 189, "Fights, in rounds.",
          sections=["Actions in Combat", "Damage Types"]),
    entry("tb.rule.actions-in-combat", "Actions in Combat", "rule", 192, "What you can do on your turn.",
          path=COMBAT, sections=["Dash", "Grappling"]),
    entry("tb.rule.dash", "Dash", "rule", 192, "You move twice as far this turn.",
          path=COMBAT + ["Actions in Combat"]),
    entry("tb.rule.grappling", "Grappling", "rule", 195, "Grab hold with a Strength (Athletics) check.",
          path=COMBAT + ["Actions in Combat"], aliases=["grapple"]),
    entry("tb.rule.damage-types", "Damage Types", "rule", 196, "Fire burns. Poison sickens. Cold chills.",
          path=COMBAT, sections=["Poison"]),
    entry("tb.rule.poison", "Poison", "rule", 196, "Stings and toxic gas deal poison damage.",
          path=COMBAT + ["Damage Types"]),
    entry("tb.condition.poisoned", "Poisoned", "condition", 292, "• A poisoned creature has disadvantage.",
          path=["Appendix A: Conditions"], aliases=["poison"]),
    entry("tb.condition.grappled", "Grappled", "condition", 290, "• A grappled creature's speed is 0.",
          path=["Appendix A: Conditions"]),
    entry("tb.spell.poison-spray", "Poison Spray", "spell", 266, "*Conjuration cantrip*\n\nA puff of noxious gas.",
          path=["Chapter 11: Spells"]),
    entry("tb.spell.fireball", "Fireball", "spell", 241, "*3rd-level evocation*\n\nA bright streak, then a boom.",
          path=["Chapter 11: Spells"]),
    entry("tb.class.fighter.extra-attack", "Extra Attack", "class", 72, "Attack twice when you take the Attack action.",
          path=["Chapter 3: Classes", "Fighter", "Class Features"]),
    entry("tb.class.monk.extra-attack", "Extra Attack", "class", 79, "Attack twice, monk style.",
          path=["Chapter 3: Classes", "Monk", "Class Features"]),
    entry("tb.monster.grub", "Grub", "monster", 150, "*Small beast*", path=["Grubs"], stats=GRUB),
    entry("tb.monster.ancient-wyrm", "Ancient Wyrm", "monster", 151, "*Gargantuan dragon*", path=["Wyrms"],
          stats={**WYRM, "checks": ["no actions read"]}),
    # A class: Knight, with its features and two subclasses
    entry("tb.class.knight", "Knight", "class", 80, "Knights ride in.",
          path=CLASSES, sections=["Class Features", "Knightly Orders"]),
    entry("tb.class.knight.class-features", "Class Features", "class", 80, "As a knight, you gain:",
          path=KNIGHT, sections=["Hit Points", "Charge", "Steady", "The Knight", "Lance Mastery"]),
    entry("tb.class.knight.hit-points", "Hit Points", "class", 80, "1d10 per knight level.",
          path=KNIGHT + ["Class Features"]),
    entry("tb.class.charge", "Charge", "class", 80, "Starting at 2nd level, you can charge.",
          path=KNIGHT + ["Class Features"]),
    entry("tb.class.steady", "Steady", "class", 80, "You don't fall off your horse.",
          path=KNIGHT + ["Class Features"], sections=["Saddle", "Stirrups"]),
    entry("tb.class.saddle", "Saddle", "class", 80, "A good one.", path=KNIGHT + ["Class Features", "Steady"]),
    entry("tb.class.stirrups", "Stirrups", "class", 80, "Two of them.", path=KNIGHT + ["Class Features", "Steady"]),
    entry("tb.class.the-knight", "The Knight", "class", 80, "A sidebar.", path=KNIGHT + ["Class Features"]),
    entry("tb.class.lance-mastery", "Lance Mastery", "class", 81, "Beginning at 5th level, lances are easy.",
          path=KNIGHT + ["Class Features"]),
    entry("tb.class.knightly-orders", "Knightly Orders", "class", 81, "Pick an order.", path=KNIGHT,
          sections=["Order of the Rose", "Order of the Thorn"]),
    entry("tb.class.order-of-the-rose", "Order of the Rose", "class", 81, "Gardeners.",
          path=KNIGHT + ["Knightly Orders"], sections=["Bloom", "Petals"]),
    entry("tb.class.bloom", "Bloom", "class", 81, "At 3rd level, you bloom.",
          path=KNIGHT + ["Knightly Orders", "Order of the Rose"]),
    entry("tb.class.petals", "Petals", "class", 81, "At 11th level, petals.",
          path=KNIGHT + ["Knightly Orders", "Order of the Rose"]),
    entry("tb.class.order-of-the-thorn", "Order of the Thorn", "class", 81, "Prickly.",
          path=KNIGHT + ["Knightly Orders"], sections=["Barbs", "Spikes"]),
    entry("tb.class.barbs", "Barbs", "class", 81, "At 7th level, you're barbed.",
          path=KNIGHT + ["Knightly Orders", "Order of the Thorn"]),
    entry("tb.class.spikes", "Spikes", "class", 81, "At 15th level, spikes.",
          path=KNIGHT + ["Knightly Orders", "Order of the Thorn"]),
    # A race: Gnoll, with traits and two subraces
    entry("tb.race.gnoll", "Gnoll", "race", 30, "Gnolls laugh a lot.", path=RACES, sections=["Gnoll Traits"]),
    entry("tb.race.gnoll-traits", "Gnoll Traits", "race", 31,
          "Your gnoll has these traits.\n\n**Ability Score Increase.** Your Strength score increases by 2.\n\n"
          "**Speed.** Your base walking speed is 30 feet.", path=RACES + ["Gnoll"],
          sections=["Plains Gnoll", "Hill Gnoll", "The Pack"]),
    entry("tb.race.plains-gnoll", "Plains Gnoll", "race", 31, "**Fleet.** You run fast.",
          path=RACES + ["Gnoll", "Gnoll Traits"]),
    entry("tb.race.hill-gnoll", "Hill Gnoll", "race", 31, "**Sturdy.** You don't fall over.",
          path=RACES + ["Gnoll", "Gnoll Traits"]),
    entry("tb.race.the-pack", "The Pack", "race", 31, "A sidebar.", path=RACES + ["Gnoll", "Gnoll Traits"]),
]


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts with no server settings, in memory."""
    db.init(":memory:")
    yield
    db.conn.close()


@pytest.fixture(autouse=True)
def test_book(monkeypatch):
    """/rule looks in BOOK, not whatever's in rules/."""
    book = Rulebook([*BOOK], {"tb": {"source": "TB", "title": "Test Book", "edition": "5e-2014"}})
    monkeypatch.setattr(rule, "rulebook", book)
    return book
