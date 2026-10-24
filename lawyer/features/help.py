"""/help [command]: every command by section, or one command in detail.

Each feature chooses its section with HELP_CATEGORY (see lawyer.features), and each command's page is its docstring,
so adding a feature never means editing this file; adding a section does (CATEGORIES).
"""

import importlib
import inspect

import discord
from discord import app_commands
from discord.ext import commands

from lawyer import config
from lawyer.common import EMBED_FIELD_LIMIT, EMBED_TOTAL_LIMIT, choices, clip
from lawyer.features import FEATURES

HELP_CATEGORY = "🔧 Utilities"
# The sections, in this order, each with what's in it for the front page.
CATEGORIES = {
    "📜 Rules": "Looking things up in our rulebooks",
    "🔧 Utilities": "Help",
}
UNCATEGORISED = "🧩 Other"


def category_of(command: commands.Command) -> str:
    if category := command.extras.get("category"):
        return category
    module = importlib.import_module(command.module) if command.module else None
    return getattr(module, "HELP_CATEGORY", UNCATEGORISED)


def visible_commands(bot: commands.Bot) -> list[commands.Command]:
    return sorted((c for c in bot.commands if not c.hidden), key=lambda c: c.name)


def front_page(bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(title="⚖️ Lawyer", color=discord.Color.blurple(),
                          description="A rules lawyer that reads from our own rulebooks. Every command works as a "
                                      f"slash command (`/rule`) and typed (`{config.COMMAND_PREFIX}rule`). "
                                      "`/help <command>` for more on one.")
    by_category: dict[str, list[commands.Command]] = {}
    for command in visible_commands(bot):
        by_category.setdefault(category_of(command), []).append(command)
    order = list(CATEGORIES) + sorted(c for c in by_category if c not in CATEGORIES)
    for category in order:
        if category not in by_category:
            continue
        lines = [f"`/{c.name}`: {c.description}" for c in by_category[category]]
        about = CATEGORIES.get(category)
        embed.add_field(name=f"{category}" + (f" — {about}" if about else ""),
                        value=clip("\n".join(lines), EMBED_FIELD_LIMIT), inline=False)
    return embed


def command_page(command: commands.Command) -> discord.Embed:
    p = config.COMMAND_PREFIX
    typed = ", ".join(f"`{p}{name}`" for name in [command.name, *command.aliases])
    embed = discord.Embed(title=f"/{command.qualified_name}", color=discord.Color.blurple(),
                          description=clip(inspect.cleandoc(command.help or command.description or ""), 4000))
    embed.add_field(name="Typed", value=typed, inline=False)
    if command.app_command and getattr(command.app_command, "parameters", None):
        options = "\n".join(f"`{o.name}`{'' if o.required else ' (optional)'}: {o.description}"
                            for o in command.app_command.parameters)
        embed.add_field(name="Options", value=clip(options, EMBED_FIELD_LIMIT), inline=False)
    return embed


def find_command(bot: commands.Bot, name: str) -> commands.Command | None:
    return bot.get_command(name.strip().lstrip("/!").lower())


async def command_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    names = [c.name for c in visible_commands(interaction.client) if current.lower() in c.name]
    return choices([(n, n) for n in names])


@commands.hybrid_command(name="help", description="What I can do: every command, or one in detail.")
@app_commands.describe(command="A command to see in detail, e.g. rule")
@app_commands.autocomplete(command=command_autocomplete)
async def help_command(ctx: commands.Context, command: str | None = None):
    """Every command, by section, with what it does. Give a command's name (`/help rule`) for its page: what it does
    in detail, how to word things, and its options."""
    if command:
        found = find_command(ctx.bot, command)
        if not found:
            await ctx.send(f"There's no `{command[:50]}` command. `/help` lists them all.", ephemeral=True)
            return
        embed = command_page(found)
    else:
        embed = front_page(ctx.bot)
    if len(embed) > EMBED_TOTAL_LIMIT:
        embed.description = clip(embed.description or "", 1000)
    await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    bot.add_command(help_command)
