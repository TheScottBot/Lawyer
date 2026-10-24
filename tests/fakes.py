"""Stand-ins for Discord objects, so commands can be run without connecting to Discord."""

import asyncio
import types


def run(coro):
    return asyncio.run(coro)


class User:
    def __init__(self, uid: int, name: str):
        self.id, self.name, self.display_name = uid, name, name
        self.mention = f"<@{uid}>"
        self.bot = False

    def __str__(self):
        return self.name


class Guild:
    def __init__(self, gid: int = 111, name: str = "Test Server"):
        self.id, self.name = gid, name


class Sent:
    """A message the bot sent."""

    def __init__(self, content=None, embed=None, view=None, private=False, allowed_mentions=None):
        self.content, self.embed, self.view = content, embed, view
        self.private, self.allowed_mentions = private, allowed_mentions
        self.edits: list[dict] = []

    @property
    def text(self) -> str:
        """Content plus embed title/description/fields/footer, for easy asserts."""
        parts = [self.content or ""]
        if self.embed:
            parts += [self.embed.author.name or "", self.embed.title or "", self.embed.description or ""]
            parts += [f"{f.name}: {f.value}" for f in self.embed.fields]
            parts += [self.embed.footer.text or ""]
        return "\n".join(p for p in parts if p)

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class Channel:
    def __init__(self, cid: int = 500, guild: Guild | None = None):
        self.id, self.guild = cid, guild

    def __str__(self):
        return f"channel-{self.id}"


class Ctx:
    """A command context: slash=True for /commands, False for !commands."""

    def __init__(self, author: User, guild: Guild | None = None, *, slash: bool = True, bot=None):
        self.author = author
        self.guild = guild if guild is not None else Guild()
        self.channel = Channel(guild=self.guild)
        self.bot = bot
        self.interaction = types.SimpleNamespace(data={}) if slash else None
        self.message = types.SimpleNamespace(content="")
        self.sent: list[Sent] = []

    async def send(self, content=None, embed=None, view=None, ephemeral=False, allowed_mentions=None, **kwargs):
        message = Sent(content, embed, view, ephemeral, allowed_mentions)
        self.sent.append(message)
        return message

    async def defer(self, ephemeral=False):
        pass

    @property
    def last(self) -> Sent:
        return self.sent[-1]


class Interaction:
    """Someone using a menu or button, or typing into autocomplete."""

    def __init__(self, user: User, values: list[str] | None = None, namespace: dict | None = None, client=None):
        self.user = user
        self.data = {"values": values or []}
        self.namespace = types.SimpleNamespace(**(namespace or {}))
        self.client = client
        self.sent: list[Sent] = []
        self.response = self

    async def send_message(self, content=None, embed=None, ephemeral=False, **kwargs):
        self.sent.append(Sent(content, embed, private=ephemeral))

    async def edit_message(self, embed=None, view=None, **kwargs):
        self.sent.append(Sent(embed=embed, view=view))

    @property
    def last(self) -> Sent:
        return self.sent[-1]
