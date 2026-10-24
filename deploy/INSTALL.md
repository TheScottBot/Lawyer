# Installing Lawyer in the homelab container

For the Debian 13 (trixie), x86_64 container with Python 3.13 that the deployment
lock was made for. The bot runs from a checkout at `/opt/Lawyer` as the `lawyer`
user, under the `lawyer` systemd service.

`deploy.sh` does the work in phases. Run it as root in the container.

## First install

Fetch the script and run every phase:

```bash
curl --fail --location --remote-name https://raw.githubusercontent.com/TheScottBot/Lawyer/main/deploy/deploy.sh
```

```bash
bash deploy.sh
```

It stops twice on purpose, each time saying what to do and which phases to run
next:

1. At `settings`, having created `/opt/Lawyer/.env` (and pointed `DB_PATH` at
   `data/lawyer.db`): set `DISCORD_TOKEN` there (and `GUILD_IDS` for your
   server), then carry on with the phases it names. The token is never printed.
2. At `rules`: copy the built rulebooks in. They're built from the PDFs on the PC
   that has them (`python -m lawyer.tools.rules_build <book>`, see
   [docs/SETUP.md](../docs/SETUP.md)); the PDFs never go to the container, only
   what's built from them. From the Lawyer folder on that PC:

```bash
scp rules/*.json root@lawyer:/opt/Lawyer/rules/
```

`bash deploy.sh help` lists the phases. Each can be run again safely.

## Updating

The code:

```bash
bash /opt/Lawyer/deploy/deploy.sh code dependencies service start
```

A rebuilt or new book: copy its `rules/<book>.json` over as above, then

```bash
bash /opt/Lawyer/deploy/deploy.sh rules start
```

The bot reads the rulebooks when it starts, so a new one needs the restart. Each
server's `/settings` are in `data/lawyer.db`, which updates never touch.

## Slash commands

With `GUILD_IDS` set in `.env`, the commands are registered to those servers on
every start and show up at once. Without it they're registered globally, which
can take a while to reach Discord clients.

## If it will not start

Follow the log with `journalctl -u lawyer -f`.

- `DISCORD_TOKEN is not set`: `.env` has no token.
- `No rulebooks in /opt/Lawyer/rules`: the `rules` phase's copy was missed; the
  bot runs, but `/rule` has nothing to look in.
- `Logged in as ...` but no slash commands: the bot was invited without the
  `applications.commands` scope, or `GUILD_IDS` names a server it isn't in (the
  log says which).
- `PrivilegedIntentsRequired`: switch on the Message Content Intent in the Discord
  Developer Portal (Bot > Privileged Gateway Intents).
- `status=226/NAMESPACE`: the container cannot give the service its own
  filesystem view. The sandboxing lines in the unit need the container's nesting
  feature switched on (on Proxmox: the container's Options, Features, Nesting),
  then a container restart.
