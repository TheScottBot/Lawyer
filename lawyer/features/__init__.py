"""One module per feature. Each is a discord.py extension: its setup(bot) registers the feature's commands.

Optional hooks a feature module can define, used by /help:
    HELP_CATEGORY = "📜 Rules"  (its /help section, one of help.CATEGORIES; a command can override with extras["category"])
"""

# Load order is also the order /help lists features in.
FEATURES = [
    "lawyer.features.rule",
    "lawyer.features.stats",
    "lawyer.features.character",
    "lawyer.features.settings",
    "lawyer.features.help",
]
