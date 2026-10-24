"""Finding a rule however it's typed (lawyer.lib.rulebook)."""

import json

from lawyer.lib.rulebook import CLOSE, EXACT, TEXT, Rulebook, name_score


def ids(hits):
    return [h.entry.id for h in hits]


def test_exact_name_wins_and_ties_go_to_conditions(test_book):
    hits = test_book.search("poison")
    assert ids(hits)[:2] == ["tb.condition.poisoned", "tb.rule.poison"]  # Both are called poison; conditions first
    assert hits[0].how == EXACT


def test_title_with_its_heading(test_book):
    # "poison damage" is Damage Types > Poison, not the condition that's only called "poison"
    assert ids(test_book.search("poison damage"))[0] == "tb.rule.poison"
    assert ids(test_book.search("fighter extra attack"))[0] == "tb.class.fighter.extra-attack"
    assert ids(test_book.search("extra attack monk"))[0] == "tb.class.monk.extra-attack"


def test_typos(test_book):
    assert ids(test_book.search("posion damage"))[0] == "tb.rule.poison"  # Letters swapped round
    assert ids(test_book.search("firebal"))[0] == "tb.spell.fireball"
    assert ids(test_book.search("grappeld"))[0] == "tb.condition.grappled"


def test_alias(test_book):
    assert ids(test_book.search("grapple"))[0] == "tb.rule.grappling"


def test_words_in_the_text_come_after_names(test_book):
    hits = test_book.search("noxious")
    assert ids(hits) == ["tb.spell.poison-spray"] and hits[0].how == TEXT
    close = test_book.search("poisoned creature")
    assert close[0].entry.id == "tb.condition.poisoned" and close[0].how == CLOSE


def test_id_finds_just_that_entry(test_book):
    assert ids(test_book.search("tb.rule.dash")) == ["tb.rule.dash"]


def test_filters(test_book):
    assert ids(test_book.search("poison", category="spell")) == ["tb.spell.poison-spray"]
    assert test_book.search("poison", book="mm") == []


def test_nothing(test_book):
    assert test_book.search("zzqx") == []
    assert test_book.search("the of") == []  # All filler
    assert test_book.search("po") == []  # Too short to look for in the text


def test_sections_of(test_book):
    combat = test_book.by_id["tb.rule.actions-in-combat"]
    assert [e.title for e in test_book.sections_of(combat)] == ["Dash", "Grappling"]


def test_autocomplete(test_book):
    assert [e.id for e in test_book.autocomplete("pois")][:3] == ["tb.rule.poison", "tb.condition.poisoned",
                                                                 "tb.spell.poison-spray"]
    assert {e.category for e in test_book.autocomplete("")} == {"condition"}  # Nothing typed: the conditions


def test_name_score():
    assert name_score(["poison", "damage"], ["poison", "damage", "types"]) > name_score(["poison", "damage"], ["poison"])
    assert name_score(["fire"], ["cold"]) == 0


def test_load_merges_aliases(tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "tb.json").write_text(json.dumps({"book": "tb", "source": "TB", "title": "Test Book",
                                               "edition": "5e-2014", "entries": [{
                                                   "id": "tb.rule.opportunity-attacks", "edition": "5e-2014",
                                                   "source": "TB", "book": "Test Book", "page": 195,
                                                   "title": "Opportunity Attacks", "category": "rule",
                                                   "aliases": ["oa"], "path": [], "sections": [], "text": "..."}]}))
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"aliases": {"tb.rule.opportunity-attacks": ["aoo", "oa"]}}))
    book = Rulebook.load(rules, aliases)
    assert book.by_id["tb.rule.opportunity-attacks"].aliases == ["oa", "aoo"]
    assert ids(book.search("aoo")) == ["tb.rule.opportunity-attacks"]
    assert book.books == {"tb": {"source": "TB", "title": "Test Book", "edition": "5e-2014", "published": ""}}


def test_newer_first(test_book):
    """With newer_first (a server's prefer_newer), the newest book's version of a rule wins a tie."""
    from tests.conftest import entry
    newer = entry("nb.rule.dash", "Dash", "rule", 5, "Run even faster.", path=["Chapter 2", "Tools", "Moving"])
    newer.book_id, newer.source = "nb", "NB"
    book = Rulebook([*test_book.entries, newer], {"tb": {"published": "2014-08-19"}, "nb": {"published": "2017-11-21"}})
    assert ids(book.search("dash", newer_first=True))[:2] == ["nb.rule.dash", "tb.rule.dash"]
    assert ids(book.search("dash", newer_first=False))[0] == "tb.rule.dash"  # Off: the shallower, earlier one
    assert ids(book.search("dash", book="tb", newer_first=True)) == ["tb.rule.dash"]


def test_load_with_no_books(tmp_path):
    assert len(Rulebook.load(tmp_path / "missing")) == 0


def test_real_aliases_file_is_names_only():
    """lawyer/lib/aliases.json is committed: ids and names, never the books' text."""
    from lawyer.lib.rulebook import ALIASES_FILE
    data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))["aliases"]
    for key, names in data.items():
        assert key.count(".") >= 2 and all(isinstance(n, str) and len(n) <= 40 for n in names), key
