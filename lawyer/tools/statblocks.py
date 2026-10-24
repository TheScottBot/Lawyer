"""Reading a monster's stat block from its lines of OCR text, into the structured stats /stats shows.

    parse(lines) -> {"size": "Large", "type": "aberration", "alignment": "lawful evil", "ac": 17,
                     "ac_note": "natural armor", "hp": 135, "hp_dice": "18d10 + 36", "speed": "10 ft., swim 40 ft.",
                     "abilities": {"str": 21, "dex": 9, ...}, "saves": "Con +6, Int +8, Wis +6", "skills": ...,
                     "vulnerabilities", "resistances", "immunities", "condition_immunities", "senses", "languages",
                     "cr": "10", "xp": 5900, "traits": [{"name", "text"}], "actions": [...], "reactions": [...],
                     "legendary_intro": "...", "legendary_actions": [...], "checks": [...]}

The scans read digits as letters ("Sd6" is 5d6, "1S" is 15, "SO XP" is 50 XP, "ld4" is 1d4), so numbers are put
right where only a number can be (fix_numbers), and then checked against the rules: an ability's modifier against
its score, hit points against the average of their dice, XP against the challenge rating's. Anything that still
doesn't add up is listed in "checks", so a bad read can be found and isn't silently trusted.

A stat block's lines come out of the PDF in reading order more or less: the ability scores' column is often
interleaved with the lines beside it ("CHA" and "18 (+4)" among the traits), so they're picked out wherever they are.
"""

import re

SIZES = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]
TYPES = ["aberration", "beast", "celestial", "construct", "dragon", "elemental", "fey", "fiend", "giant", "humanoid",
         "monstrosity", "ooze", "plant", "undead", "swarm"]
ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]
# Challenge rating -> XP, as every 5e stat block has it
XP = {"0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800, "6": 2300,
      "7": 2900, "8": 3900, "9": 5000, "10": 5900, "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
      "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000, "21": 33000, "22": 41000, "23": 50000,
      "24": 62000, "25": 75000, "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000}
# The lines before the traits, in the order books print them: (field, label)
PROPERTIES = [("ac", "Armor Class"), ("hp", "Hit Points"), ("speed", "Speed"), ("saves", "Saving Throws"),
              ("skills", "Skills"), ("vulnerabilities", "Damage Vulnerabilities"),
              ("resistances", "Damage Resistances"), ("immunities", "Damage Immunities"),
              ("condition_immunities", "Condition Immunities"), ("senses", "Senses"), ("languages", "Languages"),
              ("cr", "Challenge")]
SECTIONS = {"actions": "actions", "reactions": "reactions", "legendaryactions": "legendary_actions"}
LOOKS_LIKE_DIGITS = str.maketrans({"S": "5", "s": "5", "O": "0", "o": "0", "I": "1", "l": "1", "i": "1", "B": "8"})
DIGITISH = "0-9SsOoIliB"
ABILITY_SCORE = re.compile(rf"([{DIGITISH}]{{1,2}})\s*[({{]\s*([+\-−–])\s*([{DIGITISH}]{{1,2}})\s*\)")
# A trait or action's name: "Multiattack.", "Breath Weapon (Recharge 5-6).", "Enslave (3/Day).", "Dive Attack ."
ITEM = re.compile(r"^([A-Za-z][A-Za-z'’\-/]*(?: [A-Za-z0-9'’\-/()]+){0,6}?) ?\. (.*)$")


def digits(token: str) -> str:
    return token.translate(LOOKS_LIKE_DIGITS)


def fix_numbers(text: str) -> str:
    """Letters the OCR read for digits, put right where only a number can be: dice ("Sd6", "ld4"), numbers with a
    digit in them ("1S", "6o", "2IO"), and numbers before units and in brackets ("SO ft.", "(SO XP)", "S (1d8")."""
    text = re.sub(rf"(?<![A-Za-z])([{DIGITISH}]{{1,2}})d([{DIGITISH}]{{1,3}})\b",
                  lambda m: f"{digits(m.group(1))}d{digits(m.group(2))}", text)
    text = re.sub(rf"(?<![A-Za-z])(?=[{DIGITISH}]*\d)[{DIGITISH}]{{2,4}}(?![A-Za-z])", lambda m: digits(m.group(0)), text)
    text = re.sub(rf"(?<![A-Za-z])([{DIGITISH}]{{1,3}})(?= ?(?:ft\b|XP\b|\(\d+d))", lambda m: digits(m.group(1)), text)
    text = re.sub(rf"\(([{DIGITISH}]{{1,3}}(?:,[{DIGITISH}]{{3}})?) XP\)", lambda m: f"({digits(m.group(1))} XP)", text)
    text = re.sub(r"(\d) (?=\d\b)", r"\1", text)  # "1 1" is 11 ("DC 1 1"), split by the OCR
    return text


def tidy(text: str) -> str:
    """Spacing evened out: the OCR leaves spaces before punctuation ("attack ." "range 30/120 ft ."), and reads
    "3/Day" as "3JDay"."""
    text = re.sub(r"(\d)\s?[Jj]\s?(Day|day)", r"\1/\2", text)
    text = re.sub(r"(?<=[a-z])/1", "ll", text)  # "c/oudki/1": the OCR reads l as / and 1
    text = re.sub(r"(?<=[A-Za-z])/(?=[a-z])", "l", text)  # "Spel/casting", "Me/f's"
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"(\d)ft\b", r"\1 ft", text)
    text = re.sub(r"([+\-]) (\d)", r"\1\2", text)  # "Con + 13", "Attack:+ 14"
    text = re.sub(r":([+\-]\d)", r": \1", text)
    text = re.sub(r"\b(Hit|Miss):(?=\S)", r"\1: ", text)
    text = re.sub(r"(\d) d(\d)", r"\1d\2", text)  # "1 d6"
    text = re.sub(r"(\d+d\d+) ?([+\-]) ?(\d+)", r"\1 \2 \3", text)  # Dice as the books print them: "2d6 + 3"
    return re.sub(r"\s+", " ", text).strip()


def squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def label_of(line: str) -> tuple[str, str] | None:
    """(field, the rest) if the line is one of the properties: "Senses passive Perception 15", "Percept ion"..."""
    squashed = squash(line)
    for name, label in PROPERTIES:
        key = squash(label)
        if squashed.startswith(key):
            # Find where the label ends in the line itself, spaces and all
            seen, cut = 0, 0
            for cut, char in enumerate(line):
                if char.isalpha():
                    seen += 1
                if seen == len(key):
                    break
            return name, line[cut + 1:].strip()
    return None


def is_type_line(line: str) -> bool:
    """"Large aberration, lawful evil", "Medium humanoid (any race), any alignment"; and the OCR's "11uge"."""
    line = line.strip().strip("*").strip()
    first = squash(line.split(" ")[0]) if line else ""
    if not any(close(first, size.lower()) for size in SIZES):
        return False
    if "," in line:
        return True
    # A summon's has no alignment: "Small elemental", "Large or smaller construct"
    words = squash(line.split("(")[0]).replace(first, "", 1)
    return len(line.split()) <= 5 and any(t in words for t in TYPES)


def close(a: str, b: str) -> bool:
    """The same word, or a letter out ("11uge" is "uge" to squash(): "huge" without its first letter)."""
    if a == b:
        return True
    if not a or abs(len(a) - len(b)) > 1 or len(b) < 4:
        return False
    same = sum(1 for x, y in zip(a[::-1], b[::-1]) if x == y)
    return same >= len(b) - 1


def parse_type(line: str) -> dict:
    """"Huge fiend (demon), chaotic evil" -> size, type (with its tag) and alignment."""
    line = tidy(line)
    what, _, alignment = line.partition(",")
    words = what.split()
    size = next((s for s in SIZES if words and close(squash(words[0]), s.lower())), words[0] if words else "")
    kind = " ".join(words[1:])
    base = squash(kind.split("(")[0])
    for known in TYPES:
        if close(base, known) or (base.startswith("swarm") and known == "swarm"):
            kind = (kind.replace(kind.split("(")[0].strip(), known, 1) if known != "swarm" else kind)
            break
    return {"size": size, "type": kind.strip(), "alignment": alignment.strip()}


def parse_ac(value: str) -> tuple[int | None, str]:
    value = fix_numbers(value)
    match = re.match(r"(\d+)\s*(?:\((.*)\))?", value)
    if not match:
        return None, value
    return int(match.group(1)), tidy(match.group(2) or "")


def average(dice: str) -> int | None:
    """The average of "18d10 + 36": what a stat block's hit points are."""
    match = re.fullmatch(r"(\d+)d(\d+)\s*(?:([+\-−–])\s*(\d+))?", dice.strip())
    if not match:
        return None
    count, sides = int(match.group(1)), int(match.group(2))
    bonus = int(match.group(4) or 0) * (-1 if match.group(3) in ("-", "−", "–") else 1)
    return count * (sides + 1) // 2 + bonus


def parse_hp(value: str, checks: list[str]) -> tuple[int | None, str]:
    value = fix_numbers(value)
    match = re.match(r"(\d+)\s*\(([^)]*)\)", value)
    if not match:
        number = re.fullmatch(r"\s*(\d+)\s*", value)
        if number:
            return int(number.group(1)), ""
        # A formula: Tasha's summons have "10 + five times your bard level", which is the hit points as written
        return (tidy(value) or None), ""
    # "1 8d8 + 54", "7d10 + i 1": digits split and misread
    dice = re.sub(rf"(?<=[+\-] )([{DIGITISH} ]+)$", lambda m: digits(m.group(1)).replace(" ", ""), match.group(2))
    dice = re.sub(r"(\d) (?=\d)", r"\1", fix_numbers(dice))
    hp, dice = int(match.group(1)), tidy(dice).replace("+", " + ").replace("  ", " ")
    dice = re.sub(r"\s*([+\-])\s*", r" \1 ", dice).strip()
    expected = average(dice)
    if expected is not None and expected != hp:
        checks.append(f"hit points {hp} aren't the average of {dice} ({expected}): using {expected}")
        hp = expected
    return hp, dice


def parse_cr(value: str, checks: list[str]) -> tuple[str | None, int | None]:
    value = fix_numbers(value).replace(" ", "")
    if not value or value.lower().lstrip("-—–").startswith("proficiency"):
        return None, None  # A summon's: no Challenge, or "Challenge — Proficiency Bonus equals your bonus"
    value = re.sub(r"^[Oo](?=\(|$)", "0", value)  # "O (10 XP)": CR 0
    match = re.match(r"(\d+/\d+|\d+)", value)
    if not match or match.group(1) not in XP:
        checks.append(f"challenge rating not read: {value!r}")
        return None, None
    return match.group(1), XP[match.group(1)]


def ability_scores(lines: list[str], checks: list[str]) -> dict[str, int]:
    """The six scores, from lines that are only "21 (+5)"s, wherever they are among the block's lines. Each is checked
    against its modifier, which is sturdier (one digit)."""
    found = []
    for line in lines:
        stripped = line.strip()
        if stripped and ABILITY_SCORE.sub("", stripped).strip() == "" and ABILITY_SCORE.search(stripped):
            found += ABILITY_SCORE.findall(stripped)
    scores = {}
    for name, (score, sign, mod) in zip(ABILITIES, found):
        score_n, mod_n = int(digits(score)), int(digits(mod)) * (-1 if sign != "+" else 1)
        if (score_n - 10) // 2 != mod_n:
            if score.isdigit() and not mod.isdigit():
                checks.append(f"{name.upper()} {score_n}'s modifier misread as {mod!r}: using {score_n}")
            else:
                # The score misread: of the two scores with this modifier, the one closest to what was read
                options = [10 + 2 * mod_n, 11 + 2 * mod_n]
                fixed = min(options, key=lambda o: abs(o - score_n))
                checks.append(f"{name.upper()} {score_n} doesn't have a {mod_n:+d} modifier: using {fixed}")
                score_n = fixed
        scores[name] = score_n
    if len(scores) < 6:
        checks.append(f"only {len(scores)} ability scores read")
    return scores


def is_ability_line(line: str) -> bool:
    stripped = line.strip()
    if re.fullmatch(r"(str|dex|con|int|lnt|wis|cha)+", squash(stripped)) and stripped.upper() == stripped:
        return True  # The headings: "STR", "STR DEX C O N  INT W IS C H A"
    return bool(stripped) and ABILITY_SCORE.sub("", stripped).strip() == "" and bool(ABILITY_SCORE.search(stripped))


SMALL_WORDS = {"a", "an", "and", "of", "the", "to", "in", "on", "or", "with", "from", "for", "at", "by"}


def is_name(name: str) -> bool:
    """A trait's or action's name is in title case ("Breath Weapon (Recharge 5-6)", "Wing Attack (Costs 2
    Actions)"); "Force damage" and "Bludgeoning damage and be knocked prone" are a sentence carrying on. One word
    can be any case: the OCR reads "Javelin" as "javelin"."""
    words = re.sub(r"\([^)]*\)?", "", name).split()
    if len(words) <= 1:
        return True
    return all(w[0].isupper() or w in SMALL_WORDS or not w[0].isalpha() for w in words)


def is_action(item: dict) -> bool:
    return item["name"].lower().startswith("multiattack") or bool(
        re.match(r"(Melee|Ranged|Melee or Ranged) (Weapon|Spell) Attack", item["text"]))


def section_of(line: str) -> str | None:
    """"ACTIONS", "LEGENDARY ACTIONS", and the PHB's "A c t io n s_ _ _ _"."""
    return SECTIONS.get(squash(line))


def items(lines: list[str], words=lambda text: text) -> tuple[list[str], list[dict]]:
    """(lines before the first item, [{"name", "text"}]): traits, actions, reactions or legendary actions. A name
    starts a line and ends in a full stop, and only after a line that finished a sentence (so "...a DC 14
    Constitution saving throw. On a failure" carrying on isn't an item called "Constitution saving throw")."""
    before, found = [], []
    ended = True
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = ITEM.match(line)
        if match and ended and not line.startswith(("Hit:", "Miss:")) and len(match.group(1)) <= 45 \
                and is_name(match.group(1)):
            name = tidy(words(tidy(match.group(1))))
            found.append({"name": name[0].upper() + name[1:], "text": match.group(2)})
        elif found:
            found[-1]["text"] += " " + line
        else:
            before.append(line)
        ended = bool(re.search(r"[.:!?)]\s*$", line))
    for item in found:
        item["text"] = tidy(words(fix_numbers(item["text"])))
    return before, found


def parse(lines: list[str], words=lambda text: text) -> dict:
    """A stat block's lines (from its size-and-type line on) -> its stats. See the module's docstring. `words` repairs
    the OCR's split words ("Percept ion"): the build passes the book's own (rules_build.repair with its vocabulary)."""
    checks: list[str] = []
    stats: dict = {}
    lines = [l.strip().strip("*").strip() for l in lines if l.strip().strip("*").strip()]  # *Large beast, ...*
    start = next((i for i, l in enumerate(lines[:3]) if is_type_line(l)), None)  # It's just above Armor Class
    if start is not None:
        stats.update(parse_type(lines[start]))
        lines = lines[start + 1:]
    properties: dict[str, str] = {}
    rest: list[str] = []  # Lines after the properties: traits and the sections
    current = None
    for line in lines:
        if rest or (current == "cr" and not label_of(line) and not is_ability_line(line)):
            rest.append(line)
            continue
        if is_ability_line(line):
            continue
        if found := label_of(line):
            current, value = found
            properties[current] = value
        elif current and current not in ("ac", "hp", "cr"):
            properties[current] += " " + line.strip()  # A long list wrapped onto the next line
        elif current:
            rest.append(line)
        # Before Armor Class, anything else is a stray line (the name again, a caption): skipped
    stats["ac"], stats["ac_note"] = parse_ac(properties.get("ac", ""))
    stats["ac_note"] = words(stats["ac_note"])
    stats["hp"], stats["hp_dice"] = parse_hp(properties.get("hp", ""), checks)
    stats["speed"] = tidy(fix_numbers(properties.get("speed", "")))
    stats["abilities"] = ability_scores(lines, checks)
    for name in ("saves", "skills", "vulnerabilities", "resistances", "immunities", "condition_immunities",
                 "senses", "languages"):
        value = tidy(words(fix_numbers(properties.get(name, ""))))
        if name in ("saves", "skills"):
            value = re.sub(r"\blnt\b", "Int", value)
        if value in ("-", "—", "–"):
            value = ""
        if value:
            stats[name] = value
    stats["cr"], stats["xp"] = parse_cr(properties.get("cr", ""), checks)

    # Traits, then each section's items. Ability scores mixed in among them are skipped.
    parts: dict[str, list[str]] = {"traits": []}
    part = "traits"
    for line in rest:
        if section := section_of(line):
            part = section
            parts.setdefault(part, [])
        elif not is_ability_line(line):
            parts[part].append(line)
    for part, part_lines in parts.items():
        before, found = items(part_lines, words)
        if part == "legendary_actions" and before:
            stats["legendary_intro"] = tidy(words(fix_numbers(" ".join(before))))
        stats[part] = found
    for part in ("traits", "actions"):
        stats.setdefault(part, [])
    if not stats["actions"] and "actions" not in parts:
        # The OCR lost the ACTIONS heading: traits come first, so the actions start at the first one that's an
        # attack or a Multiattack.
        first = next((i for i, item in enumerate(stats["traits"]) if is_action(item)), None)
        if first is not None:
            stats["traits"], stats["actions"] = stats["traits"][:first], stats["traits"][first:]
    if not stats["actions"]:
        checks.append("no actions read")
    if checks:
        stats["checks"] = checks
    return stats


def modifier(score: int) -> str:
    return f"{(score - 10) // 2:+d}"


def render(name: str, stats: dict) -> str:
    """The stat block as Markdown text: the entry's text, so /rule shows it and a search can find words in it."""
    kind = f"{stats.get('size', '')} {stats.get('type', '')}".strip()
    lines = [f"*{kind}, {stats['alignment']}*" if stats.get("alignment") else f"*{kind}*"]
    ac = f"**Armor Class** {stats.get('ac')}" + (f" ({stats['ac_note']})" if stats.get("ac_note") else "")
    hp = f"**Hit Points** {stats.get('hp')}" + (f" ({stats['hp_dice']})" if stats.get("hp_dice") else "")
    lines += [ac, hp, f"**Speed** {stats.get('speed', '')}"]
    scores = stats.get("abilities", {})
    if scores:
        lines.append(" · ".join(f"**{a.upper()}** {scores[a]} ({modifier(scores[a])})" for a in ABILITIES if a in scores))
    for field, label in [("saves", "Saving Throws"), ("skills", "Skills"),
                         ("vulnerabilities", "Damage Vulnerabilities"), ("resistances", "Damage Resistances"),
                         ("immunities", "Damage Immunities"), ("condition_immunities", "Condition Immunities"),
                         ("senses", "Senses"), ("languages", "Languages")]:
        if stats.get(field):
            lines.append(f"**{label}** {stats[field]}")
    if stats.get("cr"):
        lines.append(f"**Challenge** {stats['cr']} ({stats['xp']:,} XP)")
    text = "\n".join(lines)
    for part, heading in [("traits", None), ("actions", "Actions"), ("reactions", "Reactions"),
                          ("legendary_actions", "Legendary Actions")]:
        found = stats.get(part) or []
        if not found:
            continue
        block = [f"__**{heading}**__"] if heading else []
        if part == "legendary_actions" and stats.get("legendary_intro"):
            block.append(stats["legendary_intro"])
        block += [f"***{item['name']}.*** {item['text']}" for item in found]
        text += "\n\n" + "\n\n".join(block)
    return text
