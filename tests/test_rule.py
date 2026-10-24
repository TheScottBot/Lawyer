"""/rule (lawyer.features.rule)."""

import discord

from lawyer.features import rule
from tests.fakes import Ctx, Interaction, User, run

SCOTT = User(1, "scott")
DAVE = User(2, "dave")


def look(what, *, user=SCOTT, **options):
    ctx = Ctx(user)
    run(rule.rule.callback(ctx, what=what, **options))
    return ctx.last


def test_answer_says_where_it_is():
    sent = look("poisoned")
    assert sent.embed.title == "🩸 Poisoned"
    assert "disadvantage" in sent.embed.description
    assert sent.embed.author.name == "Appendix A: Conditions"
    assert sent.embed.footer.text == "Test Book, TB p. 292 · 5e-2014 · condition · tb.condition.poisoned"
    assert not sent.private  # The table sees the ruling


def test_private():
    assert look("fireball", private=True).private


def test_other_matches_menu():
    sent = look("poison")
    assert sent.embed.title == "🩸 Poisoned"
    assert sent.content == "-# 1 more with that name: see Other matches."
    menu = sent.view.children[0]
    assert isinstance(menu, discord.ui.Select)
    assert [o.value for o in menu.options][:2] == ["tb.condition.poisoned", "tb.rule.poison"]
    assert menu.options[0].default


def test_picking_another_match_shows_it():
    sent = look("poison")
    clicked = Interaction(SCOTT, values=["tb.rule.poison"])
    run(sent.view.picked(clicked))
    assert clicked.last.embed.title == "📜 Poison"
    assert clicked.last.embed.author.name == "Chapter 9: Combat › Damage Types"


def test_sections_menu_and_up_button():
    sent = look("actions in combat")
    assert "In this section: Dash, Grappling" in sent.text
    sections = [c for c in sent.view.children if isinstance(c, discord.ui.Select)][-1]
    assert [o.label for o in sections.options] == ["Dash", "Grappling"]
    clicked = Interaction(SCOTT, values=["tb.rule.dash"])
    run(sent.view.picked(clicked))
    assert clicked.last.embed.title == "📜 Dash"
    up = [c for c in sent.view.children if isinstance(c, discord.ui.Button)][0]
    assert up.label == "Up to Actions in Combat"
    back = Interaction(SCOTT)
    run(up.callback(back))
    assert back.last.embed.title == "📜 Actions in Combat"


def test_only_whoever_asked_can_use_the_menus():
    sent = look("poison")
    nosy = Interaction(DAVE, values=["tb.rule.poison"])
    assert run(sent.view.interaction_check(nosy)) is False
    assert nosy.last.private and "someone else's" in nosy.last.content


def test_one_answer_has_no_menus():
    assert look("fireball").view is None  # Nothing else matches, nothing under it, and its chapter isn't an entry
    dash = look("dash").view.children  # Only the way back up
    assert len(dash) == 1 and isinstance(dash[0], discord.ui.Button)


def test_not_found():
    sent = look("zzqx")
    assert sent.private and "Nothing for “zzqx”" in sent.embed.title and "TB" in sent.embed.description


def test_no_books(monkeypatch):
    from lawyer.lib.rulebook import Rulebook
    monkeypatch.setattr(rule, "rulebook", Rulebook([]))
    sent = look("poison")
    assert sent.private and "haven't got any rulebooks" in sent.content


def test_long_text_is_cut_with_the_page(test_book):
    test_book.by_id["tb.rule.dash"].text = "You run. " * 1000
    sent = look("dash")
    assert len(sent.embed.description) <= 4096
    assert sent.embed.description.endswith("*(It goes on: TB p. 192.)*")


def test_autocomplete_sends_ids():
    found = run(rule.what_autocomplete(Interaction(SCOTT), "fire"))
    assert found[0].value == "tb.spell.fireball" and found[0].name == "Fireball — TB p. 241 · spell"
    assert look(found[0].value).embed.title == "✨ Fireball"


def test_book_and_category_autocomplete():
    books = run(rule.book_autocomplete(Interaction(SCOTT), "test"))
    assert [(c.name, c.value) for c in books] == [("Test Book (TB, 5e-2014)", "tb")]
    assert [c.value for c in run(rule.category_autocomplete(Interaction(SCOTT), "con"))] == ["condition"]
