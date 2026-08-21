#!/usr/bin/env python3
"""Deterministic i18n catalog load, hash, validate, and export helpers.

Pure functions over sorted inputs: no process locale, timezone, or directory-order
dependence. Dist writers always emit UTF-8 LF with two-space JSON indent.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

FORMAT_ITEM_RE = re.compile(
    r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*|\d+)"
    r"(?:\s*,\s*[-+]?\d+)?(?:\s*:[^{}]*)?\}(?!\})"
)

SCHEMA_VERSION = 1
SOURCE_LOCALE = "zh"
FALLBACK_LOCALE = "en"
TURN_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def normalize_locale(value: str) -> str:
    return (value or "").strip().replace("_", "-").lower()


def placeholder_tokens(text: str) -> set[str]:
    return {match.group(1) for match in FORMAT_ITEM_RE.finditer(text or "")}


def placeholder_syntax_error(text: str) -> str | None:
    index = 0
    while index < len(text or ""):
        if text[index] == "{":
            if index + 1 < len(text) and text[index + 1] == "{":
                index += 2
                continue
            match = FORMAT_ITEM_RE.match(text, index)
            if match is None:
                return f"invalid '{{' at character {index + 1}"
            index = match.end()
            continue
        if text[index] == "}":
            if index + 1 < len(text) and text[index + 1] == "}":
                index += 2
                continue
            return f"unmatched '}}' at character {index + 1}"
        index += 1
    return None


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(obj).encode("utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def source_hash(*, source: str, arguments: list[dict[str, str]], rich_text: bool, description: str) -> str:
    payload = {
        "arguments": arguments,
        "description": description or "",
        "richText": bool(rich_text),
        "source": source,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def dialogue_turn_hash(*, source: str, speaker_slot: int, turn_id: str) -> str:
    payload = {
        "source": source,
        "speakerSlot": speaker_slot,
        "turnId": turn_id,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def turn_id_for(index: int) -> str:
    if index < 0:
        raise ValueError("turn index must be >= 0")
    if index < 26:
        return TURN_LETTERS[index]
    # 26 -> aa, 27 -> ab. Enough for dialogue turns.
    return turn_id_for(index // 26 - 1) + TURN_LETTERS[index % 26]


def escape_cs(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def escape_po(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def unescape_cs(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            mapping = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'}
            out.append(mapping.get(nxt, nxt))
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def sorted_paths(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern), key=lambda p: p.as_posix())


def load_manifest(root: Path) -> dict[str, Any]:
    return load_json(root / "manifest.json")


def iter_ui_source_files(root: Path) -> list[Path]:
    return sorted_paths(root / "catalog" / "ui", "*.json")


def iter_dialogue_source_files(root: Path) -> list[Path]:
    return sorted_paths(root / "catalog" / "dialogue", "*.json")


def load_ui_sources(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in iter_ui_source_files(root):
        payload = load_json(path)
        for entry in payload.get("entries", []):
            entries.append(entry)
    entries.sort(key=lambda item: (item.get("seq", 10**9), item.get("key", "")))
    return entries


def load_ui_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted_paths(root / "locales" / locale / "ui", "*.json"):
        payload = load_json(path)
        for entry in payload.get("entries", []):
            entries.append(entry)
    return entries


def load_dialogue_sources(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in iter_dialogue_source_files(root):
        payload = load_json(path)
        for candidate in payload.get("candidates", []):
            candidates.append(candidate)
    return candidates


def load_dialogue_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in sorted_paths(root / "locales" / locale / "dialogue", "*.json"):
        payload = load_json(path)
        for candidate in payload.get("candidates", []):
            candidates.append(candidate)
    return candidates


def ui_file_stem(key: str) -> str:
    parts = key.split(".")
    if len(parts) < 3:
        raise ValueError(f"UI key {key!r} is too short to split into a namespace file")
    return f"{parts[1].lower()}.{parts[2].lower()}"


def parse_locstring_cs(path: Path) -> list[tuple[str, str]]:
    """Yield (dotted_key, default_text) for every LocString field, in file order."""
    class_re = re.compile(r"^\s*public class (\w+)\s*$")
    field_re = re.compile(r'^\s*public static LocString (\w+) = "(.*)";\s*$')
    entries: list[tuple[str, str]] = []
    class_stack: list[list[Any]] = []
    depth = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        while class_stack and class_stack[-1][2] and depth <= class_stack[-1][1]:
            class_stack.pop()
        match = class_re.match(line)
        if match:
            class_stack.append([match.group(1), depth, False])
        depth += line.count("{") - line.count("}")
        if class_stack and depth > class_stack[-1][1]:
            class_stack[-1][2] = True
        match = field_re.match(line)
        if match:
            key = ".".join([item[0] for item in class_stack] + [match.group(1)])
            entries.append((key, unescape_cs(match.group(2))))
    return entries


def parse_po_catalog(path: Path) -> tuple[dict[str, str], list[str]]:
    import ast

    catalog: dict[str, str] = {}
    errors: list[str] = []
    context: str | None = None
    translated: str | None = None
    active: str | None = None

    def flush(line: int) -> None:
        nonlocal context, translated, active
        if context:
            key = context.removeprefix("ONIAiSocial.")
            if key in catalog:
                errors.append(f"{path}:{line}: duplicate msgctxt {context}")
            elif translated is None or translated == "":
                errors.append(f"{path}:{line}: empty msgstr for {context}")
            else:
                catalog[key] = translated
        context = translated = active = None

    def value(raw: str, line: int) -> str | None:
        try:
            parsed = ast.literal_eval(raw.strip())
        except (SyntaxError, ValueError):
            errors.append(f"{path}:{line}: invalid PO quoted string")
            return None
        if not isinstance(parsed, str):
            errors.append(f"{path}:{line}: PO value is not a string")
            return None
        return parsed

    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped:
            flush(line_number)
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("msgctxt "):
            if context:
                flush(line_number)
            context = value(stripped[len("msgctxt ") :], line_number)
            active = "context"
            continue
        if stripped.startswith("msgstr "):
            translated = value(stripped[len("msgstr ") :], line_number)
            active = "translated"
            continue
        if stripped.startswith("msgid "):
            active = "ignored"
            continue
        if stripped.startswith('"'):
            continuation = value(stripped, line_number)
            if continuation is None:
                continue
            if active == "context":
                context = (context or "") + continuation
            elif active == "translated":
                translated = (translated or "") + continuation
            continue
    flush(len(lines) + 1)
    return catalog, errors


def fallback_chain(locale: str, published: Iterable[str]) -> list[str]:
    published_set = {normalize_locale(item) for item in published}
    exact = normalize_locale(locale)
    chain: list[str] = []

    def add(item: str) -> None:
        item = normalize_locale(item)
        if item and item not in chain:
            chain.append(item)

    add(exact)
    if "-" in exact:
        add(exact.split("-", 1)[0])
    add(FALLBACK_LOCALE)
    add(SOURCE_LOCALE)
    return [item for item in chain if item in published_set or item == SOURCE_LOCALE]


def validate_catalog(root: Path) -> list[str]:
    errors: list[str] = []
    manifest = load_manifest(root)
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"manifest schemaVersion must be {SCHEMA_VERSION}")
    if manifest.get("sourceLocale") != SOURCE_LOCALE:
        errors.append("manifest sourceLocale must be zh")
    if manifest.get("fallbackLocale") != FALLBACK_LOCALE:
        errors.append("manifest fallbackLocale must be en")
    published = [normalize_locale(item) for item in manifest.get("publishedLocales", [])]
    if SOURCE_LOCALE not in published or FALLBACK_LOCALE not in published:
        errors.append("publishedLocales must include zh and en")

    ui_entries = load_ui_sources(root)
    ui_by_key: dict[str, dict[str, Any]] = {}
    for entry in ui_entries:
        key = entry.get("key")
        if not key:
            errors.append("UI source entry missing key")
            continue
        if key in ui_by_key:
            errors.append(f"duplicate UI key {key}")
            continue
        ui_by_key[key] = entry
        source = entry.get("source", "")
        syntax = placeholder_syntax_error(source)
        if syntax:
            errors.append(f"{key}: source placeholder syntax is malformed ({syntax})")
        expected_hash = source_hash(
            source=source,
            arguments=list(entry.get("arguments") or []),
            rich_text=bool(entry.get("richText")),
            description=entry.get("description") or "",
        )
        if entry.get("sourceHash") and entry["sourceHash"] != expected_hash:
            errors.append(f"{key}: stored sourceHash does not match source contract")

    dialogue = load_dialogue_sources(root)
    seen_candidates: set[str] = set()
    seen_turns: set[tuple[str, str]] = set()
    dialogue_by_id: dict[str, dict[str, Any]] = {}
    for candidate in dialogue:
        cid = candidate.get("candidateId")
        if not cid:
            errors.append("dialogue candidate missing candidateId")
            continue
        if cid in seen_candidates:
            errors.append(f"duplicate candidateId {cid}")
            continue
        seen_candidates.add(cid)
        dialogue_by_id[cid] = candidate
        turns = candidate.get("turns") or []
        if not turns:
            errors.append(f"{cid}: candidate has no turns")
        for turn in turns:
            tid = turn.get("turnId")
            pair = (cid, tid)
            if pair in seen_turns:
                errors.append(f"duplicate turn {cid}+{tid}")
            seen_turns.add(pair)
            if not isinstance(turn.get("speakerSlot"), int):
                errors.append(f"{cid}.{tid}: speakerSlot must be an int")

    for locale in published:
        if locale == SOURCE_LOCALE:
            continue
        locale_entries = {item["key"]: item for item in load_ui_locale(root, locale) if "key" in item}
        for key, source_entry in ui_by_key.items():
            loc = locale_entries.get(key)
            if loc is None:
                errors.append(f"{locale}: missing translation {key}")
                continue
            status = loc.get("status")
            if status == "draft":
                errors.append(f"{locale}: draft translation {key}")
            expected = source_hash(
                source=source_entry.get("source", ""),
                arguments=list(source_entry.get("arguments") or []),
                rich_text=bool(source_entry.get("richText")),
                description=source_entry.get("description") or "",
            )
            if loc.get("sourceHash") != expected:
                errors.append(f"{locale}: stale translation {key}")
            source_tokens = placeholder_tokens(source_entry.get("source", ""))
            text_tokens = placeholder_tokens(loc.get("text", ""))
            if source_tokens != text_tokens:
                errors.append(f"{locale}: {key}: translation placeholders differ")
            syntax = placeholder_syntax_error(loc.get("text", ""))
            if syntax:
                errors.append(f"{locale}: {key}: translation placeholder syntax is malformed ({syntax})")
        extra = set(locale_entries) - set(ui_by_key)
        for key in sorted(extra):
            errors.append(f"{locale}: unknown translation key {key}")

        loc_dialogue = {item["candidateId"]: item for item in load_dialogue_locale(root, locale) if "candidateId" in item}
        for cid, source_candidate in dialogue_by_id.items():
            loc = loc_dialogue.get(cid)
            if loc is None:
                errors.append(f"{locale}: missing dialogue candidate {cid}")
                continue
            if loc.get("status") == "draft":
                errors.append(f"{locale}: draft dialogue candidate {cid}")
            src_turns = source_candidate.get("turns") or []
            loc_turns = loc.get("turns") or []
            loc_by_id = {turn.get("turnId"): turn for turn in loc_turns}
            src_ids = [turn.get("turnId") for turn in src_turns]
            loc_ids = [turn.get("turnId") for turn in loc_turns]
            if not loc_ids:
                errors.append(f"{locale}: {cid}: locale candidate has no turns")
            # Shared prefix of turn ids must keep speaker slots. Extra meme turns
            # on either side are allowed because some C# pools were never 1:1.
            shared = min(len(src_ids), len(loc_ids))
            for src_turn, loc_turn in zip(src_turns[:shared], loc_turns[:shared]):
                if src_turn.get("turnId") != loc_turn.get("turnId"):
                    errors.append(
                        f"{locale}: {cid}: turnId {loc_turn.get('turnId')!r} != source {src_turn.get('turnId')!r}"
                    )
                if src_turn.get("speakerSlot") != loc_turn.get("speakerSlot"):
                    errors.append(
                        f"{locale}: {cid}.{src_turn.get('turnId')}: speakerSlot mismatch"
                    )
                expected = dialogue_turn_hash(
                    source=src_turn.get("source", ""),
                    speaker_slot=int(loc_turn.get("speakerSlot", 0)),
                    turn_id=src_turn.get("turnId", ""),
                )
                if loc_turn.get("sourceHash") != expected:
                    errors.append(f"{locale}: stale dialogue turn {cid}.{src_turn.get('turnId')}")
            for tid in loc_ids[shared:]:
                extra = loc_by_id[tid]
                if extra.get("speakerSlot") is None or extra.get("text") in (None, ""):
                    errors.append(f"{locale}: {cid}.{tid}: extra locale turn is incomplete")
        extra_cids = set(loc_dialogue) - set(dialogue_by_id)
        for cid in sorted(extra_cids):
            errors.append(f"{locale}: unknown dialogue candidate {cid}")

    return errors


def _ui_trie(entries: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {"fields": [], "children": {}, "order": []}
    for entry in entries:
        parts = entry["key"].split(".")
        node = root
        for part in parts[:-1]:
            if part not in node["children"]:
                node["children"][part] = {"fields": [], "children": {}, "order": []}
                node["order"].append(part)
            node = node["children"][part]
        node["fields"].append((parts[-1], entry["source"]))
    return root


def render_strings_cs(entries: list[dict[str, Any]]) -> str:
    trie = _ui_trie(entries)
    strings = trie["children"].get("STRINGS")
    if strings is None:
        raise RuntimeError("catalog has no STRINGS root")

    lines = [
        "// <auto-generated> oni-ai-social-i18n export. Do not edit. </auto-generated>",
        "namespace ONIAiSocial",
        "{",
    ]

    def emit(name: str, node: dict[str, Any], indent: str) -> None:
        lines.append(f"{indent}public class {name}")
        lines.append(f"{indent}{{")
        inner = indent + "    "
        for field, source in node["fields"]:
            lines.append(f'{inner}public static LocString {field} = "{escape_cs(source)}";')
        for child in node["order"]:
            if node["fields"] or child != node["order"][0]:
                if node["fields"] or True:
                    lines.append("")
            emit(child, node["children"][child], inner)
        lines.append(f"{indent}}}")

    emit("STRINGS", strings, "    ")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def render_po(entries: list[dict[str, Any]], translations: dict[str, str] | None) -> str:
    header = (
        'msgid ""\nmsgstr ""\n'
        '"Application: Oxygen Not Included\\n"\n'
        '"POT Version: 2.0\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
    )
    blocks = [header]
    for entry in entries:
        key = entry["key"]
        default = entry["source"]
        ctx = f'msgctxt "ONIAiSocial.{key}"'
        if translations is None:
            blocks.append(f'{ctx}\nmsgid "{escape_po(default)}"\nmsgstr ""\n')
        else:
            blocks.append(
                f'{ctx}\nmsgid "{escape_po(default)}"\nmsgstr "{escape_po(translations[key])}"\n'
            )
    return "\n".join(blocks)


def compact_dialogue(root: Path, locale: str) -> dict[str, Any]:
    sources = load_dialogue_sources(root)
    locale_map = None
    if locale != SOURCE_LOCALE:
        locale_map = {item["candidateId"]: item for item in load_dialogue_locale(root, locale)}

    storylets: dict[str, Any] = {}
    fallback: dict[str, list[list[str]]] = {"ordinary": [], "breaking": []}

    for candidate in sources:
        cid = candidate["candidateId"]
        src_turns = candidate["turns"]
        if locale == SOURCE_LOCALE:
            turn_texts = [(turn["speakerSlot"], turn["source"]) for turn in src_turns]
        else:
            loc = locale_map[cid]
            turn_texts = [(turn["speakerSlot"], turn["text"]) for turn in loc["turns"]]

        if candidate.get("family") == "fallback" or str(candidate.get("storyletId", "")).lower() == "fallback":
            category = (candidate.get("variant") or {}).get("value") or "ordinary"
            fallback.setdefault(category, []).append([text for _, text in turn_texts])
            continue

        storylet_id = candidate["storyletId"]
        variant = candidate.get("variant") or {"kind": "base"}
        bucket = storylets.setdefault(storylet_id, {"base": [], "tags": {}})
        compact_turns = [{"slot": slot, "text": text} for slot, text in turn_texts]
        if variant.get("kind") == "initiatorTag":
            tag = variant["value"]
            bucket["tags"].setdefault(tag, []).append(compact_turns)
        else:
            bucket["base"].append(compact_turns)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "locale": locale,
        "storylets": storylets,
        "fallback": fallback,
    }


def export_dist(root: Path) -> dict[str, bytes]:
    """Return mapping of dist-relative paths to UTF-8 bytes. Deterministic."""
    manifest = load_manifest(root)
    published = [normalize_locale(item) for item in manifest["publishedLocales"]]
    ui_entries = load_ui_sources(root)
    files: dict[str, bytes] = {}
    files["generated/STRINGS.g.cs"] = render_strings_cs(ui_entries).encode("utf-8")

    locale_texts: dict[str, dict[str, str]] = {}
    for locale in published:
        if locale == SOURCE_LOCALE:
            continue
        locale_texts[locale] = {item["key"]: item["text"] for item in load_ui_locale(root, locale)}

    files["translations/strings_template.pot"] = render_po(ui_entries, None).encode("utf-8")
    for locale, translations in locale_texts.items():
        files[f"translations/{locale}.po"] = render_po(ui_entries, translations).encode("utf-8")

    for locale in published:
        payload = compact_dialogue(root, locale)
        files[f"dialogue/{locale}.json"] = dumps(payload).encode("utf-8")
    return files


def write_dist(root: Path) -> list[Path]:
    dist = root / "dist"
    written: list[Path] = []
    files = export_dist(root)
    # Remove stale dist files that we own so regenerate is a clean tree.
    expected = {dist / relative for relative in files}
    if dist.exists():
        for existing in dist.rglob("*"):
            if existing.is_file() and existing not in expected:
                # Keep unknown files only if outside generated/translations/dialogue.
                rel = existing.relative_to(dist).as_posix()
                if rel.startswith(("generated/", "translations/", "dialogue/")):
                    existing.unlink()
    for relative, data in files.items():
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
    return written
