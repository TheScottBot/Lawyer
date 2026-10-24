"""/class and /race (lawyer.features.character), on the made-up Knight and Gnoll in conftest.py."""

import discord

from lawyer.features import character
from tests.fakes import Ctx, Interaction, User, run

SCOTT = User(1, "scott")


def ask(command, name, **options):
    ctx = Ctx(SCOTT)
    run(command.callback(ctx, name=name, **options))
    return ctx.last


def field_names(sent):
    return [f.name for f in sent.embed.fields]


def test_class_features_by_level():
    sent = ask(character.class_command, "knight")
    assert sent.embed.title == "⚔️ Knight"
    # The basics first, then features in level order; a sidebar ("The Knight") isn't a feature
    assert field_names(sent) == ["Hit Points", "Steady · 1st level", "Charge · 2nd level", "Lance Mastery · 5th level"]
    steady = next(f.value for f in sent.embed.fields if f.name.startswith("Steady"))
    assert steady.endswith("**Options:** Saddle, Stirrups")
    assert "**Subclasses:** Order of the Rose, Order of the Thorn" in sent.embed.description


def test_subclass_menu():
    sent = ask(character.class_command, "knight")
    menu = [c for c in sent.view.children if isinstance(c, discord.ui.Select)][0]
    assert [o.label for o in menu.options] == ["Knight (the class)", "Order of the Rose (TB)", "Order of the Thorn (TB)"]
    clicked = Interaction(SCOTT, values=["tb.class.order-of-the-thorn"])
    run(sent.view.picked(clicked))
    assert clicked.last.embed.title == "⚔️ Knight: Order of the Thorn"
    # The class and the subclass together, in level order, the subclass's marked
    assert [f.name for f in clicked.last.embed.fields] == [
        "Hit Points", "Steady · 1st level", "Charge · 2nd level", "Lance Mastery · 5th level",
        "🔸 Barbs · 7th level (Order of the Thorn)"]
    assert "🔸 marks Order of the Thorn's features (TB)" in clicked.last.embed.description


def test_subclass_feature_without_a_level_comes_with_the_subclass(test_book):
    test_book.by_id["tb.class.bloom"].text = "You bloom."  # Doesn't say when: at the subclass's first, 3rd
    test_book.by_id["tb.class.order-of-the-rose"].sections.append("Thorns")
    from tests.conftest import entry
    thorns = entry("tb.class.thorns", "Thorns", "class", 81, "At 3rd level, thorns.",
                   path=["Chapter 3: Classes", "Knight", "Knightly Orders", "Order of the Rose"])
    test_book.entries.append(thorns)
    test_book.children[("tb", *thorns.path)].append(thorns)
    sent = ask(character.class_command, "knight", subclass="rose")
    assert "🔸 Bloom · 3rd level (Order of the Rose)" in field_names(sent)


def test_class_and_subclass_typed_together():
    assert ask(character.class_command, "knight order of the rose").embed.title == "⚔️ Knight: Order of the Rose"
    assert ask(character.class_command, "knight", subclass="thorn").embed.title == "⚔️ Knight: Order of the Thorn"
    assert ask(character.class_command, "knigt").embed.title == "⚔️ Knight"  # Typo


def test_unknown_class_lists_them():
    sent = ask(character.class_command, "astronaut")
    assert sent.private and sent.content == "No class called “astronaut”. I know: Knight."
    assert "No Knight subclass called “banana”" in ask(character.class_command, "knight banana").content


def test_race_traits_and_subraces():
    sent = ask(character.race_command, "gnoll")
    assert sent.embed.title == "🧝 Gnoll"
    assert field_names(sent) == ["​", "Ability Score Increase", "Speed", "🔹 Plains Gnoll", "Fleet",
                                 "🔹 Hill Gnoll", "Sturdy"]  # Not the sidebar "The Pack"
    assert next(f.value for f in sent.embed.fields if f.name == "Speed") == "Your base walking speed is 30 feet."


def test_one_subrace():
    sent = ask(character.race_command, "gnoll hill")
    assert sent.embed.title == "🧝 Hill Gnoll"
    assert "Fleet" not in field_names(sent) and "Sturdy" in field_names(sent)
    assert ask(character.race_command, "gnoll", subrace="plains gnoll").embed.title == "🧝 Plains Gnoll"


def test_autocomplete():
    found = run(character.class_autocomplete(Interaction(SCOTT), "kn"))
    assert [(c.name, c.value) for c in found] == [("Knight (TB)", "tb.class.knight")]
    subs = run(character.subclass_autocomplete(Interaction(SCOTT, namespace={"name": "tb.class.knight"}), ""))
    assert [c.value for c in subs] == ["tb.class.order-of-the-rose", "tb.class.order-of-the-thorn"]
    assert [c.value for c in run(character.race_autocomplete(Interaction(SCOTT), "g"))] == ["tb.race.gnoll"]
