"""/stats <monster> [book] [private] (typed: !stats <monster>): a monster's stat block, laid out to run it.

Every stat block in the books (the Monster Manual's, and the Player's Handbook's creatures in Appendix D) was parsed
when the book was built (lawyer/tools/statblocks.py) into its numbers, traits, actions, reactions and legendary
actions; this lays them out as Discord embeds. A big one (a lich's spell list, an ancient dragon) is more than one
embed can hold, so it's split into pages with ◀ ▶ buttons. A stat block the scan didn't read cleanly says so, with
the page to check. /rule finds the same stat blocks, as text, among everything else.
"""

import discord
from discord import app_commands
from discord.ext import commands

from lawyer import db
from lawyer.common import EMBED_FIELD_LIMIT, EMBED_TOTAL_LIMIT, NO_PINGS, choices, clip
from lawyer.features import rule
from lawyer.lib.rulebook import EXACT, Entry, Hit

HELP_CATEGORY = "📜 Rules"
COLOUR = discord.Color.dark_red()
ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]
PROPERTIES = [("saves", "Saving Throws"), ("skills", "Skills"), ("vulnerabilities", "Vulnerabilities"),
              ("resistances", "Resistances"), ("immunities", "Damage Immunities"),
              ("condition_immunities", "Condition Immunities"), ("senses", "Senses"), ("languages", "Languages")]
PARTS = [("traits", "Traits"), ("actions", "Actions"), ("reactions", "Reactions"),
         ("legendary_actions", "Legendary Actions")]
PAGE_LIMIT = EMBED_TOTAL_LIMIT - 300  # Room for the title and footer


def has_stats(entry: Entry) -> bool:
    return bool(entry.stats)


def modifier(score: int) -> str:
    return f"{(score - 10) // 2:+d}"


def ability_table(scores: dict) -> str:
    """The six scores as the book lays them out, in a code block so they line up."""
    names = "  ".join(f"{a.upper():^7}" for a in ABILITIES)
    values = "  ".join(f"{f'{scores[a]} ({modifier(scores[a])})':^7}" if a in scores else f"{'?':^7}"
                       for a in ABILITIES)
    return f"```\n{names}\n{values}\n```"


def item_fields(title: str, items: list[dict], intro: str = "") -> list[tuple[str, str]]:
    """A part of the stat block (Actions) as fields: as many items to a field as fit, carrying on in the next."""
    fields, current = [], intro
    for item in items:
        line = f"***{item['name']}.*** {item['text']}"
        if current and len(current) + len(line) + 2 > EMBED_FIELD_LIMIT:
            fields.append(current)
            current = ""
        while len(line) > EMBED_FIELD_LIMIT:  # One item longer than a field: a lich's spell list
            cut = clip(line, EMBED_FIELD_LIMIT, more="")
            fields.append(cut)
            line = line[len(cut):].strip()
        current = f"{current}\n\n{line}".strip()
    if current:
        fields.append(current)
    return [(title if n == 0 else f"{title} (continued)", text) for n, text in enumerate(fields)]


def warning(entry: Entry) -> str | None:
    """A note when the scan didn't read this stat block cleanly: what's off, and the page to check."""
    checks = entry.stats.get("checks") or []
    serious = [c for c in checks if not c.startswith(("hit points", "STR", "DEX", "CON", "INT", "WIS", "CHA"))]
    if not serious:
        return None
    return f"⚠️ The scan of this stat block isn't clean ({'; '.join(serious)}). Check {entry.where}."


def stat_embeds(entry: Entry) -> list[discord.Embed]:
    """The stat block as one embed, or pages of them if it's too big for one."""
    s = entry.stats
    head = f"*{s.get('size', '')} {s.get('type', '')}, {s.get('alignment', '')}*" if s.get("type") else ""
    ac = f"{s.get('ac', '?')}" + (f" ({s['ac_note']})" if s.get("ac_note") else "")
    hp = f"{s.get('hp', '?')}" + (f" ({s['hp_dice']})" if s.get("hp_dice") else "")
    cr = f"{s['cr']} ({s['xp']:,} XP)" if s.get("cr") else "?"
    details = "\n".join(f"**{label}** {s[key]}" for key, label in PROPERTIES if s.get(key))
    first = [("Armor Class", ac, True), ("Hit Points", hp, True), ("Challenge", cr, True),
             ("Speed", s.get("speed") or "?", False)]
    if s.get("abilities"):
        first.append(("Abilities", ability_table(s["abilities"]), False))
    if details:
        first.append(("Details", clip(details, EMBED_FIELD_LIMIT), False))
    fields = [(n, v, i) for n, v, i in first]
    for key, title in PARTS:
        intro = s.get("legendary_intro", "") if key == "legendary_actions" else ""
        fields += [(n, v, False) for n, v in item_fields(title, s.get(key) or [], intro)]
    if s.get("lair"):
        fields.append(("Lair", "\n".join(f"`/rule {name}`" for name in s["lair"]), False))

    note = warning(entry)
    description = "\n\n".join(part for part in (head, note) if part) or None
    pages: list[discord.Embed] = []

    def new_page() -> discord.Embed:
        embed = discord.Embed(title=f"🐉 {entry.title}"[:256], color=COLOUR, description=description if not pages
                              else f"*{entry.title}, continued*")
        if entry.path:
            embed.set_author(name=" › ".join(entry.path)[:256])
        pages.append(embed)
        return embed

    embed = new_page()
    for name, value, inline in fields:
        if len(embed) + len(name) + len(value) > PAGE_LIMIT or len(embed.fields) >= 25:
            embed = new_page()
        embed.add_field(name=name[:256], value=value[:EMBED_FIELD_LIMIT], inline=inline)
    for n, page in enumerate(pages):
        where = f"{entry.book}, {entry.where} · {entry.edition} · {entry.id}"
        page.set_footer(text=(f"Page {n + 1} of {len(pages)} · " if len(pages) > 1 else "") + where)
    return pages


class StatsView(discord.ui.View):
    """◀ ▶ for a stat block's pages, and a menu of the other monsters that matched. Only whoever asked can use them."""

    def __init__(self, entry: Entry, hits: list[Hit], author_id: int):
        super().__init__(timeout=rule.MENU_TIMEOUT)
        self.hits, self.author_id = hits, author_id
        self.message: discord.Message | None = None
        self.show(entry)

    def show(self, entry: Entry) -> None:
        self.entry, self.pages, self.page = entry, stat_embeds(entry), 0
        self.clear_items()
        if len(self.pages) > 1:
            for label, step in (("◀", -1), ("▶", 1)):
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=0)

                async def turn(interaction: discord.Interaction, step=step):
                    self.page = max(0, min(len(self.pages) - 1, self.page + step))
                    await interaction.response.edit_message(embed=self.pages[self.page], view=self)
                button.callback = turn
                self.add_item(button)
        if len(self.hits) > 1:
            menu = discord.ui.Select(placeholder=f"Other matches ({len(self.hits) - 1})", row=1,
                                     options=[rule.option_for(h.entry, h.entry.id == entry.id) for h in self.hits[:25]])
            menu.callback = self.picked
            self.add_item(menu)

    @property
    def has_controls(self) -> bool:
        return bool(self.children)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("That's someone else's lookup. Run your own `/stats`.",
                                                    ephemeral=True)
            return False
        return True

    async def picked(self, interaction: discord.Interaction) -> None:
        entry = rule.rulebook.by_id.get(interaction.data["values"][0])
        if entry:
            self.show(entry)
            await interaction.response.edit_message(embed=self.pages[0], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def monster_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    book = getattr(interaction.namespace, "book", None)
    found = rule.rulebook.autocomplete(current, book, only=has_stats)
    return choices([(f"{e.title} — CR {(e.stats or {}).get('cr') or '?'} · {e.where}", e.id) for e in found])


@commands.hybrid_command(name="stats", aliases=["statblock", "monster"],
                         description="A monster's stat block: AC, HP, abilities, actions, legendary actions.")
@app_commands.describe(monster="The monster: goblin, owlbear, adult red dragon, lich",
                       book="Only this book (leave out for every book)",
                       private="Only show it to you (default: everyone in the channel sees it)")
@app_commands.autocomplete(monster=monster_autocomplete, book=rule.book_autocomplete)
async def stats(ctx: commands.Context, *, monster: str, book: str | None = None, private: bool = False):
    """A monster's whole stat block, ready to run: Armor Class, hit points and challenge, speed, the six ability
    scores, saves, skills, senses and resistances, then its traits, actions, reactions and legendary actions. A
    monster with a lair says which `/rule` has its lair actions.

    Any monster or creature with a stat block in the books: the Monster Manual, and the Player's Handbook's
    creatures (familiars, mounts, wild shapes). Small typos are fine (`owlbaer`). A big stat block has ◀ ▶ pages;
    when more than one monster matches (`dragon`), an **Other matches** menu has the rest. Only you can use them.

    If the scan of a stat block wasn't read cleanly, it says what's missing and the page to check."""
    if not any(e.stats for e in rule.rulebook.entries):
        await ctx.send("I haven't got any stat blocks yet. Whoever runs me needs to build the Monster Manual "
                       "(see docs/SETUP.md).", ephemeral=True)
        return
    hits = rule.rulebook.search(monster, book=book, only=has_stats,
                                newer_first=db.prefer_newer(ctx.guild.id if ctx.guild else None))
    if not hits:
        await ctx.send(f"No stat block for “{discord.utils.escape_markdown(monster[:100])}”. Try its name as the "
                       "book has it (goblin, adult red dragon) or `/rule` for anything else.", ephemeral=True)
        return
    view = StatsView(hits[0].entry, hits, ctx.author.id)
    others = sum(1 for h in hits if h.how == EXACT) - 1
    content = f"-# {others} more with that name: see Other matches." if others > 0 else None
    message = await ctx.send(content, embed=view.pages[0], view=view if view.has_controls else None,
                             ephemeral=private, allowed_mentions=NO_PINGS)
    view.message = message


async def setup(bot: commands.Bot):
    bot.add_command(stats)
