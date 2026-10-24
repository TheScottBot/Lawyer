# Commands

Every command works as a slash command (`/rule`) and typed (`!rule`, with the prefix set by `COMMAND_PREFIX`).

## 📜 Rules

| Command | What it does |
|---|---|
| `/rule <what> [book] [category] [private]` (typed: `!rule <what>`, `!r`) | Look a rule up in our rulebooks. You get the book's text, the chapter and section it's in, and the book, page, edition and id it came from (`Player's Handbook, PHB p. 292 · 5e-2014 · condition · phb.condition.poisoned`). |

How to word it: however you'd say it at the table. The rule's name (`grappled`, `cover`, `fireball`), what people call
it (`aoo`, `dual wield`, `crit`, `long rest`), or its name with what it's under (`poison damage` is the damage type,
`fighter extra attack` the fighter's). Any word order, and small typos are fine (`posion`, `firebal`). If no name
matches, you get the entries that use every word you typed.

| Option | |
|---|---|
| `what` | The rule. Picking from the autocomplete list goes straight to that entry. |
| `book` | Only this book (`phb`). Leave out for every book. |
| `category` | Only this kind of entry: `condition`, `rule`, `spell`, `feat`, `class`, `race`, `equipment`, `background`, `creature`, `lore`. |
| `private` | Only you see the answer. By default the channel does, so the table can see the ruling. |

Under the answer:

- **Other matches**: everything else that matched, best first. `/rule poison` is the Poisoned condition, with the
  poison damage type, Poison Spray and the rest in the menu.
- **Sections under it**: for a heading with sections (Actions in Combat: Attack, Dash, Disengage…).
- **⬆️ Up to …**: the heading it's under.

Only whoever asked can use them, for 10 minutes.

Examples: `/rule poison`, `/rule poison damage`, `/rule grappled`, `/rule aoo`, `/rule what:extra attack category:class`.

| Command | What it does |
|---|---|
| `/stats <monster> [book] [private]` (typed: `!stats`, `!monster`) | A monster's whole stat block, laid out to run: AC, hit points and challenge, speed, the six ability scores, saves, skills, senses, resistances and languages, then traits, actions, reactions and legendary actions. A monster with a lair names the `/rule` for its lair actions. |
| `/class <name> [subclass] [private]` (typed: `!class`) | A class's features all together: hit points, proficiencies and equipment, then every feature in level order (`Extra Attack · 5th level`), with its options (Fighting Style's styles). With a subclass (optional), the class and subclass collapsed into one list in level order, the subclass's features marked 🔸. The **Subclass** menu has every book's subclasses (Xanathar's too). |
| `/race <name> [subrace] [private]` (typed: `!race`) | A race's traits all together (ability scores, size, speed, darkvision, languages...), then each subrace's. |

`/stats` covers every stat block in the books: the Monster Manual's, and the Player's Handbook's creatures (familiars,
mounts, wild shapes). Small typos are fine (`owlbaer`). A big stat block (a lich, an ancient dragon) has ◀ ▶ pages,
and more than one match (`dragon`) has an **Other matches** menu. If the scan of a stat block wasn't read cleanly, it
says what's missing and the page to check rather than guessing.

`/class` and `/race` are shortcuts: `/rule` finds any one feature or trait, these show the whole class or race at
once. Each feature is cut short with the `/rule` to read the rest. Type the subclass or subrace after the name to go
straight to it: `/class fighter battle master`, `/race dwarf hill`, or use the `subclass`/`subrace` options. Long
classes have ◀ ▶ pages.

Examples: `/stats goblin`, `/stats adult red dragon`, `/class wizard`, `/class fighter battle master`,
`/race tiefling`, `/race elf wood`.

## 🔧 Utilities

| Command | What it does |
|---|---|
| `/settings` (or `/settings show`) | This server's settings. Only you see them. |
| `/settings prefer_newer <on/off>` | Needs Manage Server. On: when a rule is in more than one book (Falling is in the PHB and Xanathar's), `/rule` and `/stats` answer from the newest book first and say which older books have it; add `book:phb` for the original. Off (the default): the best match, whichever book. |
| `/help [command]` | Every command by section, or one command's page (`/help rule`): what it does, how to word things, its options. Only you see it. |
