"""The bot itself: startup, loading features, syncing slash commands, command logging and errors."""

import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from lawyer import config, db
from lawyer.common import log
from lawyer.features import FEATURES


def setup_logging() -> None:
    """Log to the terminal (so journalctl still works) and to a rolling log file."""
    formatter = logging.Formatter("[{asctime}] [{levelname:<7}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
    # The log file is best-effort: if it can't be opened, keep running with terminal/journal logging only.
    try:
        config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES,
                                           backupCount=config.LOG_BACKUPS, encoding="utf-8")
    except OSError as error:
        log.warning("Couldn't open log file %s, logging to terminal only: %s", config.LOG_FILE, error)
        return
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def describe_options(options: list[dict]) -> str:
    """Slash command options as 'name=value', flattening subcommands."""
    parts = []
    for option in options:
        if "options" in option:
            parts.append(describe_options(option["options"]))
        elif "value" in option:
            parts.append(f"{option['name']}={option['value']}")
    return " ".join(p for p in parts if p)


class LawyerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Needed to read "<prefix>rule" from messages. Must also be enabled in the Developer Portal.
        intents.message_content = True
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

    async def load_features(self) -> None:
        for feature in FEATURES:
            await self.load_extension(feature)

    async def setup_hook(self):
        await self.load_features()
        if config.GUILD_IDS:
            # Server-only slash commands update instantly; global ones can take a while to reach clients.
            for guild_id in config.GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                try:
                    synced = await self.tree.sync(guild=guild)
                except discord.Forbidden:
                    # One wrong server shouldn't stop the bot: say which, and carry on with the rest.
                    log.warning("Couldn't add slash commands to server %s (Discord said Missing Access). Either the "
                                "bot isn't in that server (check GUILD_IDS), or it was invited without the "
                                "applications.commands scope (re-invite it with that ticked). Skipping it.", guild_id)
                    continue
                log.info("Synced %d slash commands to server %s", len(synced), guild_id)
            # Remove any old global copies so commands don't show up twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global slash commands", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (ID: %s), prefix: %r, logging to %s", self.user, self.user.id,
                 config.COMMAND_PREFIX, config.LOG_FILE)

    async def on_command(self, ctx: commands.Context):
        # Fires for both /commands and prefix commands.
        if ctx.interaction:
            invocation = f"/{ctx.command.qualified_name} {describe_options(ctx.interaction.data.get('options', []))}".strip()
        else:
            invocation = ctx.message.content
        where = f"{ctx.guild.name} #{ctx.channel}" if ctx.guild else "DM"
        log.info("[%s] %s ran %r", where, ctx.author, invocation)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Tell people when they typed a command wrong instead of failing silently.
        if isinstance(error, (commands.UserInputError, commands.NoPrivateMessage)):
            log.info("%s's %s command failed: %s", ctx.author, ctx.command, error)
            await ctx.send(str(error), ephemeral=True)
        elif isinstance(error, commands.CheckFailure):
            log.info("%s can't use %s here: %s", ctx.author, ctx.command, error)
            await ctx.send(str(error) or "You can't use that here.", ephemeral=True)
        elif not isinstance(error, commands.CommandNotFound):
            await super().on_command_error(ctx, error)


def create_bot() -> LawyerBot:
    db.init(config.DB_PATH)
    return LawyerBot()


def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit(f"DISCORD_TOKEN is not set. Copy .env.example to {config.ENV_FILE} and add your token.")
    setup_logging()
    # log_handler=None: use the logging set up above instead of discord.py's default.
    create_bot().run(config.DISCORD_TOKEN, log_handler=None)
