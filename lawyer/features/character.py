"""/class <class> [subclass] and /race <race> [subrace]: a whole class's or race's features in one place.

/rule finds any one of them (`/rule action surge`); these are the shortcut to all of them at once, the way you'd
read the book when making or levelling a character:

- /class fighter: hit points, proficiencies and equipment, then every class feature in level order, each with the
  level it comes at ("Extra Attack · 5th level"). With a subclass (`/class fighter battle master`, or from the
  **Subclass** menu, which has every book's), the class's features and the subclass's together in one collapsed list,
  in level order, the subclass's marked 🔸.
- /race dwarf: every racial trait, then each subrace's (`/race dwarf hill` for one).

Both come from the same entries /rule uses (a class is a heading in a book with "Class Features" under it; a race is
one with "<Race> Traits"), so a new book's classes and races turn up here by themselves. Long ones are split into
pages with ◀ ▶ buttons; only whoever asked can use the buttons and menus.
"""

import re

import discord
from discord import app_commands
from discord.ext import commands

from lawyer.common import EMBED_FIELD_LIMIT, EMBED_TOTAL_LIMIT, NO_PINGS, choices, clip
from lawyer.features import rule
from lawyer.lib import fuzzy
from lawyer.lib.rulebook import Entry

HELP_CATEGORY = "📜 Rules"
CLASS_COLOUR = discord.Color.dark_green()
RACE_COLOUR = discord.Color.teal()
BASICS = ["Hit Points", "Proficiencies", "Equipment"]  # A class's first features, shown first
FEATURE_TEXT = 700  # Characters of each feature: enough to use it; /rule has the rest
COMPACT_TEXT = 300  # ...and in the class-and-subclass view, where there are twice as many
PAGE_LIMIT = EMBED_TOTAL_LIMIT - 400
LEVEL = re.compile(r"\b(\d{1,2})\s?(?:st|nd|rd|th)\s?[ -]level\b|\blevel (\d{1,2})\b", re.IGNORECASE)  # "4 th-level"


def under(entry: Entry) -> list[Entry]:
    return rule.rulebook.sections_of(entry)


def classes(book: str | None = None) -> list[Entry]:
    """Every class: a heading with "Class Features" under it."""
    return [e for e in rule.rulebook.entries if e.category == "class" and "Class Features" in e.sections
            and (not book or e.book_id == book)]


def races(book: str | None = None) -> list[Entry]:
    """Every race: a heading with "<Race> Traits" under it."""
    return [e for e in rule.rulebook.entries if e.category == "race" and f"{e.title} Traits" in e.sections
            and (not book or e.book_id == book)]


def subclasses(cls: Entry) -> list[Entry]:
    """The class's subclasses from every book: its own book's, then any other book's with a heading for the same
    class (Xanathar's "Barbarian" has more Primal Paths)."""
    found = book_subclasses(cls)
    for other in rule.rulebook.entries:
        if other.category == "class" and other.title == cls.title and other.book_id != cls.book_id \
                and len(other.path) == len(cls.path):
            found += book_subclasses(other, least=1)  # Xanathar's has just the one Arcane Tradition
    return found


NOT_SUBCLASSES = re.compile(r"\b(optional|options?|builds?|companions?|infusions?|features?|invocations?)\b",
                            re.IGNORECASE)  # Tasha's "Optional Class Features", "Maneuver Options"...


def is_subclass_like(entry: Entry) -> bool:
    """A heading with features of its own (two or more), that isn't a list of options ("Maneuver Options")."""
    return len(under(entry)) >= 2 and not NOT_SUBCLASSES.search(entry.title)


def book_subclasses(cls: Entry, least: int = 2) -> list[Entry]:
    """The subclasses in one book: under a heading of them (the PHB's Martial Archetypes: Champion, Battle Master,
    Eldritch Knight), or straight under the class (Tasha's Barbarian: Path of the Beast, Path of Wild Magic). A
    supplement can add as few as one (`least`)."""
    for section in under(cls):
        if section.title == "Class Features" or NOT_SUBCLASSES.search(section.title):
            continue
        options = [o for o in under(section) if is_subclass_like(o)]
        if len(options) >= least:
            return options
    direct = [o for o in under(cls) if o.title != "Class Features" and is_subclass_like(o)]
    if len(direct) >= least:
        return direct
    # The scan lost the heading (Otherworldly Patrons): they're under Class Features, as "The Fiend" and the rest
    features = next((e for e in under(cls) if e.title == "Class Features"), None)
    found = [f for f in under(features) if is_subclass(f)] if features else []
    return found if len(found) >= 2 else []


def is_subclass(feature: Entry) -> bool:
    """A heading under Class Features that's a subclass the scan put there: its sections are features ("The Fiend"
    has Dark One's Blessing...), not options with no more under them (Fighting Style's)."""
    return feature.title.startswith("The ") and len(under(feature)) >= 2


def subraces(race: Entry) -> list[Entry]:
    traits = traits_of(race)
    return [s for s in under(traits) if not s.title.startswith("The ")] if traits else []  # "The Darkness of the
    # Drow" is a sidebar


def traits_of(race: Entry) -> Entry | None:
    return next((e for e in under(race) if e.title == f"{race.title} Traits"), None)


def level_of(feature: Entry, default: int = 1) -> int:
    """The level a feature comes at, from its text ("Beginning at 5th level"); `default` if it doesn't say."""
    match = LEVEL.search(feature.text[:300])
    return int(match.group(1) or match.group(2)) if match else default


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def feature_field(feature: Entry, with_level: bool = True, limit: int = FEATURE_TEXT,
                  level: int | None = None) -> tuple[str, str]:
    """A feature as a field: its name and level, its text (cut, with where to read on), and its options if it has
    them (Fighting Style's styles)."""
    name = f"{feature.title} · {ordinal(level or level_of(feature))} level" if with_level else feature.title
    text = clip(feature.text or "", limit, more=f"… *(/rule {feature.title.lower()})*")
    options = under(feature)
    if options:
        text += "\n**Options:** " + ", ".join(o.title for o in options)
    return name[:256], clip(text or "—", EMBED_FIELD_LIMIT)


def run_in_fields(text: str) -> list[tuple[str, str]]:
    """A heading's run-in rules as fields: "**Darkvision.** Accustomed to life underground..." -> ("Darkvision",
    "Accustomed to..."). Text before the first is its own field, unnamed."""
    fields = []
    for paragraph in text.split("\n\n"):
        match = re.match(r"\*\*(.+?)\.\*\* ?(.*)", paragraph, re.S)
        if match:
            fields.append((match.group(1), match.group(2)))
        elif fields:
            fields[-1] = (fields[-1][0], f"{fields[-1][1]}\n\n{paragraph}")
        else:
            fields.append(("​", paragraph))
    return [(name[:256], clip(value or "—", EMBED_FIELD_LIMIT)) for name, value in fields]


def paged(title: str, colour: discord.Color, entry: Entry, description: str,
          fields: list[tuple[str, str]], author: str | None = None) -> list[discord.Embed]:
    """Fields spread over as many embeds as they need."""
    pages: list[discord.Embed] = []

    def new_page() -> discord.Embed:
        embed = discord.Embed(title=title[:256], color=colour,
                              description=clip(description, 4000) if not pages else f"*{title}, continued*")
        if author:
            embed.set_author(name=author[:256])
        pages.append(embed)
        return embed

    embed = new_page()
    for name, value in fields:
        if len(embed) + len(name) + len(value) > PAGE_LIMIT or len(embed.fields) >= 25:
            embed = new_page()
        embed.add_field(name=name, value=value, inline=False)
    for n, page in enumerate(pages):
        where = f"{entry.book}, {entry.where} · {entry.edition} · {entry.id}"
        page.set_footer(text=(f"Page {n + 1} of {len(pages)} · " if len(pages) > 1 else "") + where)
    return pages


def class_pages(cls: Entry) -> list[discord.Embed]:
    basics, rest = class_features(cls)
    fields = [feature_field(f, with_level=False) for f in basics] + [feature_field(f) for f in rest]
    subs = subclasses(cls)
    about = clip(cls.text, 900)
    if subs:
        about += f"\n\n**Subclasses:** {', '.join(s.title for s in subs)}. Pick one from the menu."
    return paged(f"⚔️ {cls.title}", CLASS_COLOUR, cls, about, fields, author="Class")


def class_features(cls: Entry) -> tuple[list[Entry], list[Entry]]:
    """(the basics: hit points, proficiencies, equipment; the features, in level order)."""
    heading = next(e for e in under(cls) if e.title == "Class Features")
    # Not "The Fighter" (a sidebar) or "The Fiend" (a subclass the scan put here: it's in the menu)
    features = [f for f in under(heading) if not f.title.startswith("The ")]
    # Tasha's Artificer has its Hit Points and Proficiencies beside Class Features, not under it
    features = [f for f in under(cls) if f.title in BASICS and f.title not in {g.title for g in features}] + features
    basics = sorted((f for f in features if f.title in BASICS), key=lambda f: BASICS.index(f.title))
    return basics, sorted((f for f in features if f.title not in BASICS), key=level_of)  # Keeps the book's order


def subclass_pages(cls: Entry, sub: Entry) -> list[discord.Embed]:
    """The class and a subclass together, collapsed: every feature either gives, in level order, the subclass's
    marked 🔸 and each cut shorter, so a whole character's features fit in a page or two."""
    basics, features = class_features(cls)
    # A subclass's feature that doesn't say its level (Maneuvers: a list) comes with the subclass, at its first level
    stated = [level_of(f, 0) for f in under(sub) if level_of(f, 0)]
    first = min(stated, default=1)
    merged = sorted([(level_of(f), 0, f) for f in features] + [(level_of(f, first), 1, f) for f in under(sub)],
                    key=lambda item: (item[0], item[1]))
    fields = [feature_field(f, with_level=False, limit=COMPACT_TEXT) for f in basics]
    for level, from_sub, feature in merged:
        name, value = feature_field(feature, limit=COMPACT_TEXT, level=level)
        fields.append((f"🔸 {name} ({sub.title})"[:256] if from_sub else name, value))
    about = clip(sub.text, 500) + f"\n\n🔸 marks {sub.title}'s features ({sub.source}); the rest are every {cls.title}'s."
    return paged(f"⚔️ {cls.title}: {sub.title}", CLASS_COLOUR, sub, about, fields,
                 author=f"{cls.title} with the {sub.title} subclass")


def race_pages(race: Entry, only: Entry | None = None) -> list[discord.Embed]:
    traits = traits_of(race)
    fields = run_in_fields(traits.text) if traits else []
    for sub in subraces(race):
        if only and sub.id != only.id:
            continue
        sub_fields = run_in_fields(sub.text)
        if sub_fields and sub_fields[0][0] == "​":
            sub_fields[0] = (f"🔹 {sub.title}", sub_fields[0][1])
        else:
            sub_fields.insert(0, (f"🔹 {sub.title}", "Its traits, as well as the ones above:"))
        fields += sub_fields
    title = f"🧝 {only.title}" if only else f"🧝 {race.title}"
    about = clip(race.text, 700)
    if subraces(race) and not only:
        about += f"\n\n**Subraces:** {', '.join(s.title for s in subraces(race))}."
    return paged(title, RACE_COLOUR, traits or race, about, fields, author="Race")


class BookPages(discord.ui.View):
    """◀ ▶ through pages, and a menu (subclasses, subraces) that swaps in another set. Only whoever asked."""

    def __init__(self, pages: list[discord.Embed], author_id: int, command: str,
                 menu: tuple[str, list[tuple[str, str]], object] | None = None):
        super().__init__(timeout=rule.MENU_TIMEOUT)
        self.author_id, self.command = author_id, command
        self.message: discord.Message | None = None
        self.menu = menu  # (placeholder, [(label, value)], pick(value) -> pages)
        self.show(pages)

    def show(self, pages: list[discord.Embed], picked: str | None = None) -> None:
        self.pages, self.page = pages, 0
        self.clear_items()
        if len(pages) > 1:
            for label, step in (("◀", -1), ("▶", 1)):
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=0)

                async def turn(interaction: discord.Interaction, step=step):
                    self.page = max(0, min(len(self.pages) - 1, self.page + step))
                    await interaction.response.edit_message(embed=self.pages[self.page], view=self)
                button.callback = turn
                self.add_item(button)
        if self.menu:
            placeholder, options, _ = self.menu
            select = discord.ui.Select(placeholder=placeholder, row=1, options=[
                discord.SelectOption(label=label[:100], value=value[:100], default=value == picked)
                for label, value in options[:25]])
            select.callback = self.picked
            self.add_item(select)

    @property
    def has_controls(self) -> bool:
        return bool(self.children)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"That's someone else's. Run your own `/{self.command}`.",
                                                    ephemeral=True)
            return False
        return True

    async def picked(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        self.show(self.menu[2](value), picked=value)
        await interaction.response.edit_message(embed=self.pages[0], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


def best(typed: str, pool: list[Entry]) -> Entry | None:
    """The entry whose title best matches what was typed (an id from autocomplete is that entry)."""
    if not typed:
        return None
    by_id = {e.id: e for e in pool}
    if typed in by_id:
        return by_id[typed]
    found = fuzzy.best_match(typed, fuzzy.index((e, e.title) for e in pool))
    if found:
        return found.thing
    # Part of its name: "zealot" is Path of the Zealot, "fiend" The Fiend
    typed_words = fuzzy.words(typed)
    return next((e for e in pool if typed_words and all(
        any(fuzzy.same_word(t, w) for w in fuzzy.words(e.title)) for t in typed_words)), None)


def split_name(typed: str, pool: list[Entry]) -> tuple[Entry | None, str]:
    """"fighter battle master" -> (Fighter, "battle master"): the shortest start of what's typed that's one of them
    by name ("half orc" is Half-Orc, not Half-Elf's "half" and then "orc"); failing that, the closest to all of it."""
    words = typed.split()
    for cut in range(1, len(words) + 1):
        start = fuzzy.words(" ".join(words[:cut]))
        found = next((e for e in pool if fuzzy.words(e.title) == start), None)
        if found:
            return found, " ".join(words[cut:])
    return best(typed, pool), ""


async def send_pages(ctx: commands.Context, pages: list[discord.Embed], view: BookPages, private: bool) -> None:
    message = await ctx.send(embed=pages[0], view=view if view.has_controls else None, ephemeral=private,
                             allowed_mentions=NO_PINGS)
    view.message = message


def nothing(kind: str, typed: str, pool: list[Entry]) -> str:
    names = ", ".join(sorted({e.title for e in pool})) or "none yet"
    return f"No {kind} called “{discord.utils.escape_markdown(typed[:60])}”. I know: {names}."


async def class_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    found = fuzzy.starting_first(current, classes(), key=lambda e: e.title)
    return choices([(f"{e.title} ({e.source})", e.id) for e in found])


async def subclass_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cls = best(getattr(interaction.namespace, "name", "") or "", classes())
    pool = subclasses(cls) if cls else [s for c in classes() for s in subclasses(c)]
    return choices([(f"{s.title} ({s.source})", s.id)
                    for s in fuzzy.starting_first(current, pool, key=lambda e: e.title)])


async def race_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    found = fuzzy.starting_first(current, races(), key=lambda e: e.title)
    return choices([(f"{e.title} ({e.source})", e.id) for e in found])


async def subrace_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    race = best(getattr(interaction.namespace, "name", "") or "", races())
    pool = subraces(race) if race else [s for r in races() for s in subraces(r)]
    return choices([(f"{s.title} ({s.source})", s.id)
                    for s in fuzzy.starting_first(current, pool, key=lambda e: e.title)])


@commands.hybrid_command(name="class", aliases=["classes"],
                         description="A class's features, all together, by level, with its subclasses.")
@app_commands.describe(name="The class: fighter, wizard, warlock...",
                       subclass="Optional: the class and this subclass together, in one list (battle master...)",
                       private="Only show it to you (default: everyone in the channel sees it)")
@app_commands.autocomplete(name=class_autocomplete, subclass=subclass_autocomplete)
async def class_command(ctx: commands.Context, *, name: str, subclass: str | None = None, private: bool = False):
    """Everything a class gets, in one place: hit points, proficiencies and equipment, then every class feature in
    level order, each marked with the level it comes at (`Extra Attack · 5th level`) and cut short with the `/rule`
    to read the rest. Features with options list them (Fighting Style: Archery, Defense...).

    Give a subclass (optional) for the class and subclass together, collapsed into one list: every feature a
    character of that subclass gets, in level order, the subclass's marked 🔸. `/class fighter battle master`, or
    `/class name:fighter subclass:champion`. The **Subclass** menu does the same, with every book's subclasses
    (Xanathar's too). Long classes have ◀ ▶ pages.

    `/rule` finds any single feature; this is the whole class at a glance."""
    pool = classes()
    if subclass is None:
        cls, rest = split_name(name, pool)
    else:
        cls, rest = best(name, pool), subclass
    if not cls:
        await ctx.send(nothing("class", name, pool), ephemeral=True)
        return
    subs = subclasses(cls)
    by_id = {s.id: s for s in subs}
    pick = (lambda value: subclass_pages(cls, by_id[value]) if value in by_id else class_pages(cls))
    options = [(f"{cls.title} (the class)", cls.id)] + [(f"{s.title} ({s.source})", s.id) for s in subs]
    sub = best(rest, subs) if rest else None
    if rest and not sub:
        await ctx.send(nothing(f"{cls.title} subclass", rest, subs), ephemeral=True)
        return
    pages = subclass_pages(cls, sub) if sub else class_pages(cls)
    view = BookPages(pages, ctx.author.id, "class", (f"Subclasses of {cls.title}", options, pick) if subs else None)
    if sub:
        view.show(pages, picked=sub.id)
    await send_pages(ctx, pages, view, private)


@commands.hybrid_command(name="race", aliases=["races", "species"],
                         description="A race's traits, all together, with its subraces.")
@app_commands.describe(name="The race: dwarf, elf, tiefling...",
                       subrace="Only this subrace: hill dwarf, wood elf...",
                       private="Only show it to you (default: everyone in the channel sees it)")
@app_commands.autocomplete(name=race_autocomplete, subrace=subrace_autocomplete)
async def race_command(ctx: commands.Context, *, name: str, subrace: str | None = None, private: bool = False):
    """Every racial trait in one place (ability score increases, size, speed, darkvision, languages...), then each
    subrace's. Give a subrace to see only its traits with the race's: `/race dwarf hill`, or
    `/race name:elf subrace:wood elf`. The **Subrace** menu switches between them.

    `/rule` finds any single trait; this is the whole race at a glance."""
    pool = races()
    if subrace is None:
        race, rest = split_name(name, pool)
    else:
        race, rest = best(name, pool), subrace
    if not race:
        await ctx.send(nothing("race", name, pool), ephemeral=True)
        return
    subs = subraces(race)
    by_id = {s.id: s for s in subs}
    sub = None
    if rest:
        sub = best(rest, subs) or best(f"{rest} {race.title}", subs)
        if not sub:
            await ctx.send(nothing(f"{race.title} subrace", rest, subs), ephemeral=True)
            return
    pick = (lambda value: race_pages(race, by_id.get(value)))
    options = [(f"{race.title} (every subrace)", race.id)] + [(s.title, s.id) for s in subs]
    pages = race_pages(race, sub)
    view = BookPages(pages, ctx.author.id, "race", (f"Subraces of {race.title}", options, pick) if subs else None)
    if sub:
        view.show(pages, picked=sub.id)
    await send_pages(ctx, pages, view, private)


async def setup(bot: commands.Bot):
    bot.add_command(class_command)
    bot.add_command(race_command)
