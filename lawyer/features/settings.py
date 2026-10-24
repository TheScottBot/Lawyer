"""/settings: this server's settings. Changing one needs Manage Server; anyone can see them.

    /settings show                  what they are
    /settings prefer_newer on|off   whether /rule and /stats answer from the newest book first

Stored per server in lawyer.db (lawyer/db.py), so each server chooses for itself.
"""

import discord
from discord import app_commands
from discord.ext import commands

from lawyer import db

HELP_CATEGORY = "🔧 Utilities"


def settings_embed(guild_id: int) -> discord.Embed:
    newer = db.prefer_newer(guild_id)
    embed = discord.Embed(title="⚙️ Settings", color=discord.Color.blurple())
    embed.add_field(name=f"Prefer newer rules: {'on' if newer else 'off'}", inline=False,
                    value="A rule in more than one book comes from the newest book first (Xanathar's before the "
                          "Player's Handbook); `book:phb` gets the original." if newer else
                          "A rule in more than one book: the best match, whichever book. Turn on with "
                          "`/settings prefer_newer on`.")
    return embed


@commands.hybrid_group(name="settings", fallback="show", description="This server's settings for the bot.")
@commands.guild_only()
async def settings(ctx: commands.Context):
    """This server's settings: what they are (`/settings show`), and changing them, which needs Manage Server.

    `/settings prefer_newer on`: when a rule is in more than one book (Falling is in the Player's Handbook and in
    Xanathar's), `/rule` and `/stats` answer from the newest book first, and say which older books have it too.
    Add `book:phb` to a `/rule` for the original. Off (the default): the best match, whichever book it's in."""
    await ctx.send(embed=settings_embed(ctx.guild.id), ephemeral=True)


@settings.command(name="prefer_newer", description="Answer from the newest book first when a rule is in several.")
@app_commands.describe(on="On: newest book first (book:phb for the original). Off: best match, any book.")
@commands.has_permissions(manage_guild=True)
async def prefer_newer(ctx: commands.Context, on: bool):
    """On: when a rule is in more than one book, /rule and /stats answer from the newest book first, and say which
    older books have it (`book:phb` for the original). Off: the best match, whichever book. Needs Manage Server."""
    db.set_prefer_newer(ctx.guild.id, on)
    await ctx.send(f"Prefer newer rules is now **{'on' if on else 'off'}** for this server.")


async def setup(bot: commands.Bot):
    bot.add_command(settings)
