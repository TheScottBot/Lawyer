"""/rule <what> [book] [category] [private] (typed: !rule <what>): look a rule up in our rulebooks.

The books are built from our own PDFs by lawyer/tools/rules_build.py into rules/ (see docs/SETUP.md); this reads
them once, at startup. The answer is the entry the book has for it (its text, where it is in the book, and the page),
with two menus under it: other matches for what was typed ("poison" is the condition, the damage type and three
spells), and the sections under this one (Combat's Actions in Combat lists Attack, Dash, Disengage...). Only whoever
asked can use the menus, so a lookup in the middle of a game can't be changed out from under the table.
"""

import discord
from discord import app_commands
from discord.ext import commands

from lawyer import config, db
from lawyer.common import EMBED_DESCRIPTION_LIMIT, EMBED_FIELD_LIMIT, NO_PINGS, choices, clip, log
from lawyer.lib.rulebook import EXACT, Entry, Hit, Rulebook

HELP_CATEGORY = "📜 Rules"
MENU_TIMEOUT = 600  # Seconds the menus keep working
TEXT_SHOWN = 3500  # Characters of an entry's text: room left for its sections and the footer
CATEGORY_COLOURS = {
    "condition": discord.Color.dark_red(),
    "rule": discord.Color.blurple(),
    "spell": discord.Color.purple(),
    "feat": discord.Color.gold(),
    "class": discord.Color.dark_green(),
    "race": discord.Color.teal(),
    "equipment": discord.Color.dark_gold(),
    "background": discord.Color.orange(),
    "creature": discord.Color.dark_grey(),
    "lore": discord.Color.dark_blue(),
}
CATEGORY_EMOJI = {"condition": "🩸", "rule": "📜", "spell": "✨", "feat": "🏅", "class": "⚔️", "race": "🧝",
                  "equipment": "🎒", "background": "📖", "creature": "🐾", "lore": "🌌"}

rulebook = Rulebook.load(config.RULES_DIR)
if rulebook.books:
    log.info("Loaded %d rules from %s", len(rulebook), ", ".join(b["source"] for b in rulebook.books.values()))
else:
    log.warning("No rulebooks in %s: /rule has nothing to look in. Build one with python -m lawyer.tools.rules_build",
                config.RULES_DIR)


def entry_embed(entry: Entry, sections: list[Entry] | None = None) -> discord.Embed:
    """An entry as the book has it: its text, where it is (chapter > section), and the page."""
    emoji = CATEGORY_EMOJI.get(entry.category, "📜")
    text = clip(entry.text or "*(Just a heading: see the sections under it.)*", TEXT_SHOWN,
                more=f"…\n\n*(It goes on: {entry.where}.)*")
    embed = discord.Embed(title=f"{emoji} {entry.title}"[:256], description=text[:EMBED_DESCRIPTION_LIMIT],
                          color=CATEGORY_COLOURS.get(entry.category, discord.Color.blurple()))
    if entry.path:
        embed.set_author(name=" › ".join(entry.path)[:256])
    if sections:
        listed = ", ".join(s.title for s in sections)
        embed.add_field(name="In this section", value=clip(listed, EMBED_FIELD_LIMIT), inline=False)
    embed.set_footer(text=f"{entry.book}, {entry.where} · {entry.edition} · {entry.category} · {entry.id}"[:2048])
    return embed


def not_found_embed(query: str) -> discord.Embed:
    books = ", ".join(b["source"] for b in rulebook.books.values()) or "none yet"
    return discord.Embed(title=f"📜 Nothing for “{discord.utils.escape_markdown(query[:200])}”",
                         color=discord.Color.light_grey(),
                         description=f"I couldn't find that in the rulebooks I have ({books}). Try the rule's own "
                                     f"name (grappled, cover, opportunity attack) or fewer words.")


def option_for(entry: Entry, default: bool = False) -> discord.SelectOption:
    where = f"{entry.where} · {entry.category}" + (f" · {entry.path[-1]}" if entry.path else "")
    return discord.SelectOption(label=entry.title[:100], value=entry.id[:100], description=where[:100],
                                emoji=CATEGORY_EMOJI.get(entry.category), default=default)


class RuleView(discord.ui.View):
    """The menus under an entry: the other matches, and the sections under it. Only whoever asked can use them."""

    def __init__(self, entry: Entry, hits: list[Hit], author_id: int):
        super().__init__(timeout=MENU_TIMEOUT)
        self.hits, self.author_id = hits, author_id
        self.message: discord.Message | None = None
        self.show(entry)

    def show(self, entry: Entry) -> None:
        """Put the menus for this entry under it."""
        self.entry = entry
        self.sections = rulebook.sections_of(entry)
        self.clear_items()
        if len(self.hits) > 1:
            matches = discord.ui.Select(placeholder=f"Other matches ({len(self.hits) - 1})", row=0,
                                        options=[option_for(h.entry, h.entry.id == entry.id) for h in self.hits[:25]])
            matches.callback = self.picked
            self.add_item(matches)
        if self.sections:
            under = discord.ui.Select(placeholder=f"Sections under {entry.title}"[:150], row=1,
                                      options=[option_for(s) for s in self.sections[:25]])
            under.callback = self.picked
            self.add_item(under)
        if entry.path and (parent := self.parent_of(entry)):
            up = discord.ui.Button(label=f"Up to {parent.title}"[:80], emoji="⬆️", row=2)

            async def go_up(interaction: discord.Interaction, parent=parent):
                await self.go(interaction, parent)
            up.callback = go_up
            self.add_item(up)

    @staticmethod
    def parent_of(entry: Entry) -> Entry | None:
        siblings = rulebook.children.get((entry.book_id, *entry.path[:-1]), [])
        return next((e for e in siblings if e.title == entry.path[-1]), None)

    @property
    def has_menus(self) -> bool:
        return bool(self.children)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("That's someone else's lookup. Run your own `/rule`.",
                                                    ephemeral=True)
            return False
        return True

    async def picked(self, interaction: discord.Interaction) -> None:
        entry = rulebook.by_id.get(interaction.data["values"][0])
        if entry:
            await self.go(interaction, entry)

    async def go(self, interaction: discord.Interaction, entry: Entry) -> None:
        self.show(entry)
        await interaction.response.edit_message(embed=entry_embed(entry, self.sections), view=self)

    async def on_timeout(self) -> None:
        # The menus stop working after MENU_TIMEOUT, so grey them out.
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass  # Private replies can only be edited for 15 minutes; not worth failing over.


def look_up(query: str, book: str | None = None, category: str | None = None, newer_first: bool = False) -> list[Hit]:
    return rulebook.search(query, book=book, category=category, newer_first=newer_first)


def older_note(hits: list[Hit]) -> str | None:
    """With prefer_newer on, when an older book has its own version of the answer ("Falling" in the PHB and in
    Xanathar's): which, and how to get it."""
    first = hits[0].entry
    older = [h.entry for h in hits[1:] if h.how == EXACT and h.entry.title.lower() == first.title.lower()
             and h.entry.book_id != first.book_id]
    if not older:
        return None
    sources = ", ".join(dict.fromkeys(e.source for e in older))
    books = " or ".join(f"`book:{b}`" for b in dict.fromkeys(e.book_id for e in older))
    return f"-# Newest rules first ({first.source}). Also in {sources}: add {books} for that."


async def what_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    book = getattr(interaction.namespace, "book", None)
    return choices([(f"{e.title} — {e.where} · {e.category}", e.id) for e in rulebook.autocomplete(current, book)])


async def book_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    typed = current.lower()
    return choices([(f"{b['title']} ({b['source']}, {b['edition']})", book_id)
                    for book_id, b in rulebook.books.items()
                    if typed in book_id or typed in b["title"].lower() or typed in b["source"].lower()])


async def category_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    present = sorted({e.category for e in rulebook.entries})
    return choices([(c, c) for c in present if current.lower() in c])


@commands.hybrid_command(name="rule", aliases=["rules", "r"],
                         description="Look up a rule in our rulebooks: a condition, action, spell, feat or anything.")
@app_commands.describe(what="The rule: poison, grappled, opportunity attack, fireball, fighter extra attack",
                       book="Only this book (leave out for every book)",
                       category="Only this kind of entry: condition, spell, feat, class, rule...",
                       private="Only show it to you (default: everyone in the channel sees it)")
@app_commands.autocomplete(what=what_autocomplete, book=book_autocomplete, category=category_autocomplete)
async def rule(ctx: commands.Context, *, what: str, book: str | None = None, category: str | None = None,
               private: bool = False):
    """Look up a rule and get what the book says, with the book and page it's on. Type it however you'd say it at
    the table: `poison`, `poison damage`, `grappled`, `aoo`, `fighter extra attack`, `carrying capacity`. Small typos
    are fine (`posion`).

    If the server has `/settings prefer_newer` on, a rule in more than one book comes from the newest one first
    (Xanathar's before the Player's Handbook), with a note saying which older books have it: add `book:phb` for
    the original.

    When more than one thing matches ("poison" is a condition, a damage type and some spells), you get the best one
    and an **Other matches** menu for the rest. A heading with sections under it (Actions in Combat) has a
    **Sections** menu, and every entry has an **Up** button to the heading it's under. Only you can use the menus.

    Pick from the autocomplete list to go straight to an entry. `book` and `category` narrow the search."""
    if not rulebook.entries:
        await ctx.send("I haven't got any rulebooks yet. Whoever runs me needs to build one (see docs/SETUP.md).",
                       ephemeral=True)
        return
    newer_first = db.prefer_newer(ctx.guild.id if ctx.guild else None)
    hits = look_up(what, book, category, newer_first=newer_first)
    if not hits:
        await ctx.send(embed=not_found_embed(what), ephemeral=True)
        return
    entry = hits[0].entry
    # An exact name that several entries share ("extra attack") isn't one answer: say there are others.
    view = RuleView(entry, hits, ctx.author.id)
    embed = entry_embed(entry, view.sections)
    others = sum(1 for h in hits if h.how == EXACT) - 1
    content = f"-# {others} more with that name: see Other matches." if others > 0 else None
    if newer_first and not book:
        content = older_note(hits) or content
    message = await ctx.send(content, embed=embed, view=view if view.has_menus else None,
                             ephemeral=private, allowed_mentions=NO_PINGS)
    view.message = message


async def setup(bot: commands.Bot):
    bot.add_command(rule)
