"""/stats (lawyer.features.stats)."""

import discord

from lawyer.features import stats
from lawyer.lib.rulebook import CLOSE, EXACT, Hit
from tests.fakes import Ctx, Interaction, User, run

SCOTT = User(1, "scott")
DAVE = User(2, "dave")


def look(monster, *, user=SCOTT, **options):
    ctx = Ctx(user)
    run(stats.stats.callback(ctx, monster=monster, **options))
    return ctx.last


def test_stat_block():
    sent = look("grub")
    embed = sent.embed
    assert embed.title == "🐉 Grub" and embed.description == "*Small beast, unaligned*"
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Armor Class"] == "12 (natural armor)" and fields["Hit Points"] == "9 (2d6 + 2)"
    assert fields["Challenge"] == "1/4 (50 XP)"
    assert "8 (-1)" in fields["Abilities"] and "15" not in fields["Abilities"] and "14 (+2)" in fields["Abilities"]
    assert fields["Details"] == "**Senses** tremorsense 30 ft., passive Perception 10"
    assert fields["Traits"] == "***Squishy.*** The grub is very squishy."
    assert fields["Actions"].startswith("***Nibble.*** Melee Weapon Attack")
    assert embed.footer.text == "Test Book, TB p. 150 · 5e-2014 · tb.monster.grub"
    assert sent.view is None and not sent.private


def test_only_stat_blocks():
    assert "No stat block for “fireball”" in look("fireball").content  # /rule has it; /stats doesn't


def test_typo():
    assert look("grbu").embed.title == "🐉 Grub"


def test_big_one_is_pages_with_warning_and_lair():
    sent = look("ancient wyrm")
    pages = sent.view.pages
    assert len(pages) > 1 and all(len(p) <= 6000 for p in pages)
    assert all(len(f.value) <= 1024 for p in pages for f in p.fields)
    assert "⚠️ The scan of this stat block isn't clean (no actions read). Check TB p. 151." in pages[0].description
    assert pages[0].footer.text.startswith("Page 1 of ")
    everything = [f for p in pages for f in p.fields]
    assert any(f.name == "Actions (continued)" for f in everything)
    assert any(f.name == "Legendary Actions" and f.value.startswith("The wyrm can take 3") for f in everything)
    assert any(f.name == "Lair" and "`/rule Wyrm Lair Actions`" in f.value for f in everything)
    forward = [c for c in sent.view.children if isinstance(c, discord.ui.Button) and c.label == "▶"][0]
    clicked = Interaction(SCOTT)
    run(forward.callback(clicked))
    assert clicked.last.embed is pages[1]


def test_other_matches_and_only_the_asker(test_book):
    assert look("tb.monster.grub").embed.title == "🐉 Grub"  # Autocomplete's id
    grub, wyrm = test_book.by_id["tb.monster.grub"], test_book.by_id["tb.monster.ancient-wyrm"]
    view = stats.StatsView(grub, [Hit(grub, 1.0, EXACT), Hit(wyrm, 0.6, CLOSE)], SCOTT.id)
    menu = [c for c in view.children if isinstance(c, discord.ui.Select)][0]
    assert [o.value for o in menu.options] == ["tb.monster.grub", "tb.monster.ancient-wyrm"]
    clicked = Interaction(SCOTT, values=["tb.monster.ancient-wyrm"])
    run(view.picked(clicked))
    assert clicked.last.embed.title == "🐉 Ancient Wyrm"
    nosy = Interaction(DAVE)
    assert run(view.interaction_check(nosy)) is False


def test_autocomplete():
    found = run(stats.monster_autocomplete(Interaction(SCOTT), "gr"))
    assert [(c.name, c.value) for c in found] == [("Grub — CR 1/4 · TB p. 150", "tb.monster.grub")]
