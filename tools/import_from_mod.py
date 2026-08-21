#!/usr/bin/env python3
"""One-shot importer: read private Mod C# sources into the normalized catalog."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from i18nlib import (
    SOURCE_LOCALE,
    dialogue_turn_hash,
    dumps,
    load_json,
    placeholder_tokens,
    source_hash,
    turn_id_for,
    unescape_cs,
    ui_file_stem,
    write_json,
)

SUMMARY_RE = re.compile(r"</?summary>")
ARG_DOC_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*|\d+)\}:\s*([^.;]+)")
FIELD_RE = re.compile(r'^\s*public static LocString (\w+) = "(.*)";\s*$')
CLASS_RE = re.compile(r"^\s*public class (\w+)\s*$")
STORYLET_IDS = [
    "Greeting",
    "Casual",
    "Vent",
    "Teach",
    "BestFriend",
    "Care",
    "Comfort",
    "SharedMeal",
    "Party",
    "Welcome",
    "Date",
    "AnniversaryMissed",
    "Anniversary",
    "ConfessionRekindle",
    "ConfessionFail",
    "Confession",
    "Jealousy",
    "Breakup",
    "Fallout",
    "Reconcile",
    "ApologyBond",
    "Apology",
    "Argument",
    "RivalDied",
    "Rival",
    "PartnerLoss",
    "CrushLoss",
    "BrawlBond",
    "Brawl",
    "BreakdownCry",
    "BreakdownWail",
    "BreakdownVomit",
    "BreakdownBinge",
    "BreakdownDestroy",
    "BreakdownShock",
    "BreakdownComfort",
    "HazardResent",
    "HazardEased",
    "HazardGratitude",
    "HazardComrade",
    "WrathBlame",
    "WrathIsolated",
    "WrathSpeakUp",
    "WrathRescue",
    "WrathPunch",
    "WrathWitness",
    "WrathSawCrying",
    "WrathFaded",
    "FamineWarning",
    "FamineCountdown",
    "FamineAverted",
    "FamineCull",
    "FamineOver",
    "FamineLastOne",
    "WrathMealSnub",
]
# Longer names first so AnniversaryMissed wins over Anniversary.
STORYLET_IDS_SORTED = sorted(STORYLET_IDS, key=len, reverse=True)
TAG_SUFFIXES = [
    ("Hothead", "hothead"),
    ("Crybaby", "crybaby"),
    ("Loud", "loud"),
    ("Eater", "eater"),
    ("Nervous", "nervous"),
    ("Jumpy", "jumpy"),
    ("Gentle", "gentle"),
    ("Curious", "curious"),
    ("Slow", "slow"),
    ("Early", "early"),
    ("Night", "night"),
    ("Sleepy", "sleepy"),
]


class CsScanner:
    def __init__(self, text: str, pos: int = 0):
        self.text = text
        self.pos = pos
        self.n = len(text)

    def skip(self) -> None:
        while self.pos < self.n:
            char = self.text[self.pos]
            if char in " \t\r\n":
                self.pos += 1
                continue
            if char == "/" and self.pos + 1 < self.n:
                nxt = self.text[self.pos + 1]
                if nxt == "/":
                    while self.pos < self.n and self.text[self.pos] not in "\r\n":
                        self.pos += 1
                    continue
                if nxt == "*":
                    end = self.text.find("*/", self.pos + 2)
                    if end < 0:
                        raise ValueError("unterminated block comment")
                    self.pos = end + 2
                    continue
            return

    def peek(self) -> str:
        self.skip()
        if self.pos >= self.n:
            return ""
        return self.text[self.pos]

    def startswith(self, token: str) -> bool:
        self.skip()
        return self.text.startswith(token, self.pos)

    def expect(self, token: str) -> None:
        self.skip()
        if not self.text.startswith(token, self.pos):
            snippet = self.text[self.pos : self.pos + 40].replace("\n", "\\n")
            raise ValueError(f"expected {token!r} at {self.pos}, found {snippet!r}")
        self.pos += len(token)

    def parse_string(self) -> str:
        self.skip()
        if self.pos >= self.n or self.text[self.pos] != '"':
            snippet = self.text[self.pos : self.pos + 40].replace("\n", "\\n")
            raise ValueError(f"expected string at {self.pos}, found {snippet!r}")
        self.pos += 1
        raw: list[str] = []
        while self.pos < self.n:
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                return unescape_cs("".join(raw))
            if char == "\\":
                if self.pos + 1 >= self.n:
                    raise ValueError("truncated escape")
                raw.append(char)
                raw.append(self.text[self.pos + 1])
                self.pos += 2
                continue
            raw.append(char)
            self.pos += 1
        raise ValueError("unterminated string")

    def parse_int(self) -> int:
        self.skip()
        start = self.pos
        if self.pos < self.n and self.text[self.pos] in "+-":
            self.pos += 1
        while self.pos < self.n and self.text[self.pos].isdigit():
            self.pos += 1
        if start == self.pos:
            raise ValueError(f"expected int at {self.pos}")
        return int(self.text[start : self.pos])


def parse_strings_cs(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    class_stack: list[list[Any]] = []
    depth = 0
    comments: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("///"):
            comments.append(stripped[3:].strip())
            continue
        while class_stack and class_stack[-1][2] and depth <= class_stack[-1][1]:
            class_stack.pop()
        match = CLASS_RE.match(line)
        if match:
            class_stack.append([match.group(1), depth, False])
        depth += line.count("{") - line.count("}")
        if class_stack and depth > class_stack[-1][1]:
            class_stack[-1][2] = True
        match = FIELD_RE.match(line)
        if match:
            key = ".".join([item[0] for item in class_stack] + [match.group(1)])
            source = unescape_cs(match.group(2))
            description = SUMMARY_RE.sub("", " ".join(comments)).strip()
            tokens = sorted(placeholder_tokens(source), key=lambda item: (item.isdigit(), item))
            arg_docs = {m.group(1): m.group(2).strip() for m in ARG_DOC_RE.finditer(description)}
            arguments = []
            for token in tokens:
                arguments.append(
                    {
                        "token": token,
                        "name": arg_docs.get(token, token),
                        "kind": "text",
                    }
                )
            hashed = source_hash(
                source=source,
                arguments=arguments,
                rich_text=False,
                description=description,
            )
            entries.append(
                {
                    "key": key,
                    "source": source,
                    "description": description,
                    "arguments": arguments,
                    "richText": False,
                    "sourceHash": hashed,
                }
            )
            comments = []
            continue
        if stripped and not stripped.startswith("//"):
            comments = []
    return entries


def load_en_table(mod_root: Path) -> dict[str, str]:
    generate = (mod_root / "tools" / "generate_translations.py").read_text(encoding="utf-8")
    # EN dict is assigned as EN = { ... } before FIELD_RE.
    start = generate.find("\nEN = {")
    if start < 0:
        start = generate.find("EN = {")
    if start < 0:
        raise RuntimeError("EN dictionary not found in generate_translations.py")
    brace = generate.find("{", start)
    scanner = CsScanner(generate, brace)
    # The EN table is Python, not C#, but string literals share the same scanner.
    return _parse_python_string_dict(generate[brace:])


def _parse_python_string_dict(text: str) -> dict[str, str]:
    # Use ast on a sliced dict literal. Find matching brace.
    depth = 0
    end = None
    for i, char in enumerate(text):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError("unterminated EN dictionary")
    import ast

    obj = ast.literal_eval(text[:end])
    if not isinstance(obj, dict):
        raise RuntimeError("EN is not a dict")
    return obj


def parse_line_spec_arrays(path: Path) -> dict[str, list[list[tuple[int, str]]]]:
    text = path.read_text(encoding="utf-8")
    arrays: dict[str, list[list[tuple[int, str]]]] = {}
    needle = "public static readonly LineSpec[][] "
    pos = 0
    while True:
        start = text.find(needle, pos)
        if start < 0:
            break
        scanner = CsScanner(text, start + len(needle))
        scanner.skip()
        name_start = scanner.pos
        while scanner.pos < scanner.n and (scanner.text[scanner.pos].isalnum() or scanner.text[scanner.pos] == "_"):
            scanner.pos += 1
        name = scanner.text[name_start:scanner.pos]
        scanner.expect("=")
        arrays[name] = _parse_line_spec_initializer(scanner)
        pos = scanner.pos
    return arrays


def _parse_line_spec_initializer(scanner: CsScanner) -> list[list[tuple[int, str]]]:
    scanner.expect("{")
    candidates: list[list[tuple[int, str]]] = []
    while True:
        peeked = scanner.peek()
        if peeked == "}":
            scanner.pos += 1
            scanner.skip()
            if scanner.peek() == ";":
                scanner.pos += 1
            return candidates
        if peeked == ",":
            scanner.pos += 1
            continue
        scanner.expect("new[]")
        scanner.expect("{")
        turns: list[tuple[int, str]] = []
        while True:
            inner = scanner.peek()
            if inner == "}":
                scanner.pos += 1
                break
            if inner == ",":
                scanner.pos += 1
                continue
            scanner.expect("new LineSpec")
            scanner.expect("(")
            slot = scanner.parse_int()
            scanner.expect(",")
            line = scanner.parse_string()
            scanner.expect(")")
            turns.append((slot, line))
        candidates.append(turns)


def parse_string_arrays(path: Path, names: list[str]) -> dict[str, list[list[str]]]:
    text = path.read_text(encoding="utf-8")
    found: dict[str, list[list[str]]] = {}
    for name in names:
        needle = f"{name} ="
        start = text.find(needle)
        if start < 0:
            raise RuntimeError(f"{name} not found in {path}")
        scanner = CsScanner(text, start + len(needle))
        scanner.expect("{")
        rows: list[list[str]] = []
        while True:
            peeked = scanner.peek()
            if peeked == "}":
                scanner.pos += 1
                found[name] = rows
                break
            if peeked == ",":
                scanner.pos += 1
                continue
            scanner.expect("new[]")
            scanner.expect("{")
            row: list[str] = []
            while True:
                inner = scanner.peek()
                if inner == "}":
                    scanner.pos += 1
                    break
                if inner == ",":
                    scanner.pos += 1
                    continue
                row.append(scanner.parse_string())
            rows.append(row)
    return found


def split_pool_name(name: str) -> tuple[str, dict[str, str]]:
    if name.endswith("Zh"):
        stem = name[:-2]
    elif name.endswith("En"):
        stem = name[:-2]
    else:
        raise ValueError(f"unexpected pool name {name}")
    for suffix, tag in TAG_SUFFIXES:
        if stem.endswith(suffix) and stem[: -len(suffix)] in STORYLET_IDS:
            return stem[: -len(suffix)], {"kind": "initiatorTag", "value": tag}
    if stem in STORYLET_IDS:
        return stem, {"kind": "base"}
    raise ValueError(f"cannot map pool name {name} to a storylet")


def pair_storylet_arrays(
    arrays: dict[str, list[list[tuple[int, str]]]]
) -> list[dict[str, Any]]:
    zh_names = sorted(name for name in arrays if name.endswith("Zh"))
    candidates: list[dict[str, Any]] = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for zh_name in zh_names:
        en_name = zh_name[:-2] + "En"
        if en_name not in arrays:
            raise RuntimeError(f"missing English pool for {zh_name}")
        storylet, variant = split_pool_name(zh_name)
        zh_pool = list(arrays[zh_name])
        en_pool = list(arrays[en_name])
        if len(en_pool) > len(zh_pool):
            extra = en_pool[len(zh_pool) :]
            print(
                f"note: {en_name} has {len(extra)} extra candidate(s); "
                "adding zh stubs so candidate ids align and English pool order is kept",
                file=sys.stderr,
            )
            for extra_turns in extra:
                zh_pool.append(list(extra_turns))
        elif len(zh_pool) > len(en_pool):
            raise RuntimeError(
                f"{zh_name} has {len(zh_pool)} candidates but {en_name} has {len(en_pool)}"
            )
        variant_key = variant.get("value") if variant.get("kind") == "initiatorTag" else "base"
        for zh_turns, en_turns in zip(zh_pool, en_pool):
            counts[(storylet, variant_key)] += 1
            seq = counts[(storylet, variant_key)]
            cid = f"storylet.{storylet.lower()}.{variant_key}.{seq:03d}"
            src_turns = _turns_from_pairs(zh_turns)
            loc_turns = []
            src_by_id = {turn["turnId"]: turn for turn in src_turns}
            for turn_index, (en_slot, en_text) in enumerate(en_turns):
                tid = turn_id_for(turn_index)
                src_turn = src_by_id.get(tid)
                hashed = dialogue_turn_hash(
                    source=src_turn["source"] if src_turn else "",
                    speaker_slot=en_slot,
                    turn_id=tid,
                )
                loc_turns.append(
                    {
                        "turnId": tid,
                        "speakerSlot": en_slot,
                        "text": en_text,
                        "sourceHash": hashed,
                    }
                )
            candidates.append(
                {
                    "candidateId": cid,
                    "storyletId": storylet,
                    "family": storylet.lower(),
                    "variant": variant,
                    "turns": src_turns,
                    "enTurns": loc_turns,
                }
            )
    return candidates


def _turns_from_pairs(turns: list[tuple[int, str]]) -> list[dict[str, Any]]:
    out = []
    for turn_index, (slot, text) in enumerate(turns):
        out.append(
            {
                "turnId": turn_id_for(turn_index),
                "speakerSlot": slot,
                "source": text,
            }
        )
    return out


def pair_fallback(arrays: dict[str, list[list[str]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    mapping = [
        ("ZhTemplates", "EnTemplates", "ordinary"),
        ("ZhBreakingTemplates", "EnBreakingTemplates", "breaking"),
    ]
    for zh_name, en_name, category in mapping:
        zh_pool = arrays[zh_name]
        en_pool = arrays[en_name]
        if len(zh_pool) != len(en_pool):
            raise RuntimeError(f"fallback {category} zh {len(zh_pool)} vs en {len(en_pool)}")
        for index, (zh_turns, en_turns) in enumerate(zip(zh_pool, en_pool), start=1):
            if len(zh_turns) != len(en_turns):
                raise RuntimeError(
                    f"fallback {category}[{index}] turn count {len(zh_turns)} vs {len(en_turns)}"
                )
            cid = f"storylet.fallback.{category}.{index:03d}"
            src_turns = []
            loc_turns = []
            for turn_index, (zh_text, en_text) in enumerate(zip(zh_turns, en_turns)):
                tid = turn_id_for(turn_index)
                slot = turn_index % 2
                hashed = dialogue_turn_hash(source=zh_text, speaker_slot=slot, turn_id=tid)
                src_turns.append({"turnId": tid, "speakerSlot": slot, "source": zh_text})
                loc_turns.append(
                    {
                        "turnId": tid,
                        "speakerSlot": slot,
                        "text": en_text,
                        "sourceHash": hashed,
                    }
                )
            out.append(
                {
                    "candidateId": cid,
                    "storyletId": "Fallback",
                    "family": "fallback",
                    "variant": {"kind": "category", "value": category},
                    "turns": src_turns,
                    "enTurns": loc_turns,
                }
            )
    return out


def write_ui_catalog(i18n_root: Path, entries: list[dict[str, Any]], en: dict[str, str]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[ui_file_stem(entry["key"])].append(entry)
    catalog_dir = i18n_root / "catalog" / "ui"
    locale_dir = i18n_root / "locales" / "en" / "ui"
    for path in catalog_dir.glob("*.json"):
        path.unlink()
    for path in locale_dir.glob("*.json"):
        path.unlink()
    for stem in sorted(grouped):
        src_entries = []
        loc_entries = []
        for entry in grouped[stem]:
            key = entry["key"]
            if key not in en:
                raise RuntimeError(f"missing EN translation for {key}")
            src_entries.append(
                {
                    "key": key,
                    "seq": entry["seq"],
                    "source": entry["source"],
                    "description": entry["description"],
                    "arguments": entry["arguments"],
                    "richText": entry["richText"],
                }
            )
            loc_entries.append(
                {
                    "key": key,
                    "text": en[key],
                    "sourceHash": entry["sourceHash"],
                    "status": "reviewed",
                }
            )
        write_json(
            catalog_dir / f"{stem}.json",
            {"namespace": stem, "entries": src_entries},
        )
        write_json(
            locale_dir / f"{stem}.json",
            {"locale": "en", "namespace": stem, "entries": loc_entries},
        )


def write_dialogue_catalog(i18n_root: Path, candidates: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["family"])].append(candidate)
    catalog_dir = i18n_root / "catalog" / "dialogue"
    locale_dir = i18n_root / "locales" / "en" / "dialogue"
    for path in catalog_dir.glob("*.json"):
        path.unlink()
    for path in locale_dir.glob("*.json"):
        path.unlink()
    for family in sorted(grouped):
        src_candidates = []
        loc_candidates = []
        for candidate in grouped[family]:
            src_candidates.append(
                {
                    "candidateId": candidate["candidateId"],
                    "storyletId": candidate["storyletId"],
                    "variant": candidate["variant"],
                    "turns": candidate["turns"],
                }
            )
            loc_candidates.append(
                {
                    "candidateId": candidate["candidateId"],
                    "status": "reviewed",
                    "turns": candidate["enTurns"],
                }
            )
        write_json(
            catalog_dir / f"{family}.json",
            {"family": family, "candidates": src_candidates},
        )
        write_json(
            locale_dir / f"{family}.json",
            {"locale": "en", "family": family, "candidates": loc_candidates},
        )


def write_manifest(i18n_root: Path, content_version: str) -> None:
    write_json(
        i18n_root / "manifest.json",
        {
            "schemaVersion": 1,
            "contentVersion": content_version,
            "sourceLocale": "zh",
            "fallbackLocale": "en",
            "publishedLocales": ["zh", "en"],
            "exports": {
                "ui": "po",
                "dialogue": "json",
                "prompts": "json",
            },
        },
    )


def import_mod(mod_root: Path, i18n_root: Path, content_version: str) -> None:
    strings_cs = mod_root / "src" / "STRINGS.cs"
    entries = parse_strings_cs(strings_cs)
    for index, entry in enumerate(entries):
        entry["seq"] = index
    en = load_en_table(mod_root)
    po_path = mod_root / "translations" / "en.po"
    from i18nlib import parse_po_catalog

    po, po_errors = parse_po_catalog(po_path)
    if po_errors:
        raise RuntimeError("en.po parse errors:\n" + "\n".join(po_errors))
    missing = [entry["key"] for entry in entries if entry["key"] not in en]
    extra = [key for key in en if key not in {e["key"] for e in entries}]
    if missing or extra:
        raise RuntimeError(f"EN/STRINGS mismatch missing={missing[:5]} extra={extra[:5]}")
    po_missing = [entry["key"] for entry in entries if entry["key"] not in po]
    if po_missing:
        raise RuntimeError(f"en.po missing {len(po_missing)} keys, e.g. {po_missing[:5]}")
    # Prefer live en.po as published English (same as EN when generate is in sync).
    for entry in entries:
        if po[entry["key"]] != en[entry["key"]]:
            raise RuntimeError(f"EN dict and en.po disagree on {entry['key']}")

    arrays = parse_line_spec_arrays(mod_root / "src" / "Presentation" / "StoryletLines.cs")
    storylet_candidates = pair_storylet_arrays(arrays)
    fallback_arrays = parse_string_arrays(
        mod_root / "src" / "Ai" / "FallbackLines.cs",
        ["ZhTemplates", "EnTemplates", "ZhBreakingTemplates", "EnBreakingTemplates"],
    )
    fallback_candidates = pair_fallback(fallback_arrays)

    write_ui_catalog(i18n_root, entries, en)
    write_dialogue_catalog(i18n_root, storylet_candidates + fallback_candidates)
    write_manifest(i18n_root, content_version)
    print(
        f"imported {len(entries)} UI keys and "
        f"{len(storylet_candidates) + len(fallback_candidates)} dialogue candidates"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Mod C# copy into the i18n catalog")
    parser.add_argument("--mod-root", type=Path, required=True)
    parser.add_argument("--i18n-root", type=Path, required=True)
    parser.add_argument("--content-version", required=True)
    args = parser.parse_args()
    import_mod(args.mod_root.resolve(), args.i18n_root.resolve(), args.content_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
