"""/settings and prefer_newer (lawyer.features.settings, lawyer.db), and what it does to /rule."""

from lawyer import db
from lawyer.features import rule, settings
from lawyer.lib.rulebook import Rulebook
from tests.conftest import BOOK, entry
from tests.fakes import Ctx, Guild, User, run

SCOTT = User(1, "scott")


def test_setting_is_per_server():
    assert not db.prefer_newer(111)
    db.set_prefer_newer(111, True)
    assert db.prefer_newer(111) and not db.prefer_newer(222)
    db.set_prefer_newer(111, False)
    assert not db.prefer_newer(111)
    assert not db.prefer_newer(None)  # DMs: off


def test_show_and_change():
    ctx = Ctx(SCOTT, Guild(111))
    run(settings.settings.callback(ctx))
    assert ctx.last.private and ctx.last.embed.fields[0].name == "Prefer newer rules: off"
    run(settings.prefer_newer.callback(ctx, True))
    assert ctx.last.content == "Prefer newer rules is now **on** for this server."
    run(settings.settings.callback(ctx))
    assert ctx.last.embed.fields[0].name == "Prefer newer rules: on"


def test_changing_needs_manage_server():
    assert any("has_permissions" in check.__qualname__ for check in settings.prefer_newer.checks)


def with_newer_book(monkeypatch):
    newer = entry("nb.rule.dash", "Dash", "rule", 5, "Run even faster.", path=["Chapter 2", "Tools", "Moving"])
    newer.book_id, newer.source, newer.book = "nb", "NB", "Newer Book"
    book = Rulebook([*BOOK, newer], {"tb": {"source": "TB", "title": "Test Book", "published": "2014-08-19"},
                                     "nb": {"source": "NB", "title": "Newer Book", "published": "2017-11-21"}})
    monkeypatch.setattr(rule, "rulebook", book)


def look(what, **options):
    ctx = Ctx(SCOTT, Guild(111))
    run(rule.rule.callback(ctx, what=what, **options))
    return ctx.last


def test_prefer_newer_on_rule(monkeypatch):
    with_newer_book(monkeypatch)
    assert look("dash").embed.footer.text.endswith("tb.rule.dash")  # Off: the best match
    db.set_prefer_newer(111, True)
    sent = look("dash")
    assert sent.embed.footer.text.endswith("nb.rule.dash")
    assert sent.content == "-# Newest rules first (NB). Also in TB: add `book:tb` for that."
    original = look("dash", book="tb")
    assert original.embed.footer.text.endswith("tb.rule.dash") and original.content is None
