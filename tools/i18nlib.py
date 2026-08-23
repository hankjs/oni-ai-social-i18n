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
MAX_UI_TEXT_LENGTH = 10000
MAX_DIALOGUE_TEXT_LENGTH = 2000
MAX_CHRONICLE_TEXT_LENGTH = 2000
ALLOWED_RICH_TEXT_TAGS = {"b", "i", "color"}

# Legacy pools were not all literal translations. These exact per-locale turn
# shapes preserve the shipped dialogue without weakening the structure contract
# for every other candidate.
DIALOGUE_TURN_EXCEPTIONS = {
    ("en", "storylet.argument.base.012"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.bestfriend.base.007"): (("a", "b", "c"), ("a", "b")),
    ("en", "storylet.casual.base.018"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.casual.base.020"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.casual.base.021"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.casual.base.022"): (("a", "b", "c"), ("a", "b")),
    ("en", "storylet.casual.base.023"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.date.base.007"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.date.base.008"): (("a", "b"), ("a", "b", "c")),
    ("en", "storylet.sharedmeal.base.014"): (("a", "b", "c"), ("a", "b")),
}


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


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_json_schema(value: Any, schema: dict[str, Any], location: str) -> list[str]:
    """Validate the JSON-Schema subset used by this repository without network dependencies."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_schema_type_matches(value, item) for item in choices):
            errors.append(f"{location}: expected type {' or '.join(choices)}")
            return errors
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value {value!r} is not in {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(f"{location}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{location}: string is longer than maxLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{location}: value does not match {pattern!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{location}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{location}: value is above maximum {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{location}: array is shorter than minItems")
        if schema.get("uniqueItems"):
            encoded = [canonical_json(item) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{location}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, item_schema, f"{location}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for required in schema.get("required") or []:
            if required not in value:
                errors.append(f"{location}: missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{location}: unknown property {key!r}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(validate_json_schema(value[key], child_schema, f"{location}.{key}"))
    return errors


def validate_schema_files(root: Path) -> list[str]:
    errors: list[str] = []
    schemas = {
        name: load_json(root / "schemas" / f"{name}.schema.json")
        for name in (
            "manifest", "ui-source", "ui-locale", "dialogue-source", "dialogue-locale",
            "chronicle-source", "chronicle-locale", "chronicle-stability",
        )
    }
    routes: list[tuple[Path, str, str | None]] = [
        (root / "manifest.json", "manifest", None),
        (root / "contracts" / "chronicle-stability.json", "chronicle-stability", None),
    ]
    routes.extend((path, "ui-source", None) for path in iter_ui_source_files(root))
    routes.extend((path, "dialogue-source", None) for path in iter_dialogue_source_files(root))
    routes.extend((path, "chronicle-source", None) for path in iter_chronicle_source_files(root))
    locales_root = root / "locales"
    if locales_root.is_dir():
        for locale_dir in sorted((path for path in locales_root.iterdir() if path.is_dir()), key=lambda p: p.name):
            locale = normalize_locale(locale_dir.name)
            routes.extend((path, "ui-locale", locale) for path in sorted_paths(locale_dir / "ui", "*.json"))
            routes.extend(
                (path, "dialogue-locale", locale)
                for path in sorted_paths(locale_dir / "dialogue", "*.json")
            )
            routes.extend(
                (path, "chronicle-locale", locale)
                for path in sorted_paths(locale_dir / "chronicle", "*.json")
            )
    for path, schema_name, expected_locale in routes:
        try:
            payload = load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"{path.relative_to(root)}: invalid JSON ({error})")
            continue
        label = path.relative_to(root).as_posix()
        errors.extend(validate_json_schema(payload, schemas[schema_name], label))
        if expected_locale is not None and isinstance(payload, dict):
            actual = normalize_locale(payload.get("locale", ""))
            if actual != expected_locale:
                errors.append(f"{label}: locale {actual!r} does not match directory {expected_locale!r}")
    return errors


def rich_text_error(text: str, enabled: bool) -> str | None:
    tags = list(re.finditer(r"<[^>]*>", text or ""))
    if not tags:
        return None
    if not enabled:
        return "rich-text markup is present while richText is false"
    stack: list[str] = []
    for match in tags:
        raw = match.group(0)
        parsed = re.fullmatch(r"<(/?)([A-Za-z]+)(?:=(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{8}))?>", raw)
        if parsed is None:
            return f"unsupported rich-text tag {raw!r}"
        closing, tag, argument = parsed.groups()
        tag = tag.lower()
        if tag not in ALLOWED_RICH_TEXT_TAGS:
            return f"rich-text tag {tag!r} is not allowed"
        if tag == "color" and not closing and argument is None:
            return "color tag requires a six- or eight-digit hex value"
        if tag != "color" and argument is not None:
            return f"rich-text tag {tag!r} does not accept attributes"
        if closing:
            if argument is not None or not stack or stack[-1] != tag:
                return f"unbalanced rich-text closing tag {raw!r}"
            stack.pop()
        else:
            stack.append(tag)
    if stack:
        return f"unclosed rich-text tag {stack[-1]!r}"
    return None


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


def chronicle_template_hash(*, source: str, description: str, pool_id: str,
                            allowed_slots: list[str]) -> str:
    payload = {
        "allowedSlots": sorted(allowed_slots),
        "description": description or "",
        "poolId": pool_id,
        "source": source,
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


def iter_chronicle_source_files(root: Path) -> list[Path]:
    return sorted_paths(root / "catalog" / "chronicle", "*.json")


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


def load_chronicle_pools(root: Path) -> list[dict[str, Any]]:
    pools: list[dict[str, Any]] = []
    for path in iter_chronicle_source_files(root):
        payload = load_json(path)
        family = payload.get("family", "")
        for pool in payload.get("pools", []):
            item = dict(pool)
            item["family"] = family
            pools.append(item)
    return pools


def load_chronicle_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for path in sorted_paths(root / "locales" / locale / "chronicle", "*.json"):
        payload = load_json(path)
        templates.extend(payload.get("templates", []))
    return templates


def normalized_chronicle_text(text: str) -> str:
    """Collapse punctuation/spacing/case so trivial duplicates cannot satisfy pool capacity."""
    return "".join(char.lower() for char in (text or "") if char.isalnum())


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
    errors = validate_schema_files(root)
    if errors:
        return errors
    manifest = load_manifest(root)
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"manifest schemaVersion must be {SCHEMA_VERSION}")
    if manifest.get("sourceLocale") != SOURCE_LOCALE:
        errors.append("manifest sourceLocale must be zh")
    if manifest.get("fallbackLocale") != FALLBACK_LOCALE:
        errors.append("manifest fallbackLocale must be en")
    content_version = manifest.get("contentVersion")
    if not isinstance(content_version, str) or not content_version:
        errors.append("manifest contentVersion must be a non-empty SemVer")
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
        if len(source) > MAX_UI_TEXT_LENGTH:
            errors.append(f"{key}: source exceeds {MAX_UI_TEXT_LENGTH} characters")
        max_length = entry.get("maxLength")
        if isinstance(max_length, int) and len(source) > max_length:
            errors.append(f"{key}: source exceeds maxLength {max_length}")
        rich_error = rich_text_error(source, bool(entry.get("richText")))
        if rich_error:
            errors.append(f"{key}: {rich_error}")
        syntax = placeholder_syntax_error(source)
        if syntax:
            errors.append(f"{key}: source placeholder syntax is malformed ({syntax})")
        declared_tokens = [str(item.get("token", "")) for item in entry.get("arguments") or []]
        if len(declared_tokens) != len(set(declared_tokens)):
            errors.append(f"{key}: duplicate declared argument token")
        source_tokens = placeholder_tokens(source)
        if set(declared_tokens) != source_tokens:
            errors.append(
                f"{key}: declared arguments {sorted(set(declared_tokens))!r} do not match "
                f"source placeholders {sorted(source_tokens)!r}"
            )
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
        storylet_id = str(candidate.get("storyletId") or "")
        variant = candidate.get("variant") or {}
        variant_kind = variant.get("kind")
        variant_value = variant.get("value")
        if storylet_id.lower() == "fallback":
            if variant_kind != "category" or variant_value not in ("ordinary", "breaking"):
                errors.append(
                    f"{cid}: fallback dialogue must use category ordinary or breaking"
                )
        elif variant_kind == "category":
            errors.append(f"{cid}: category variants are reserved for fallback dialogue")
        elif variant_kind == "initiatorTag" and not variant_value:
            errors.append(f"{cid}: initiatorTag variant requires a non-empty value")
        elif variant_kind == "base" and variant_value is not None:
            errors.append(f"{cid}: base variant must not declare a value")
        turns = candidate.get("turns") or []
        if not turns:
            errors.append(f"{cid}: candidate has no turns")
        for turn in turns:
            tid = turn.get("turnId")
            pair = (cid, tid)
            if pair in seen_turns:
                errors.append(f"duplicate turn {cid}+{tid}")
            seen_turns.add(pair)
            speaker_slot = turn.get("speakerSlot")
            if not isinstance(speaker_slot, int):
                errors.append(f"{cid}.{tid}: speakerSlot must be an int")
            elif speaker_slot < 0:
                errors.append(f"{cid}.{tid}: speakerSlot must be non-negative")
            text = turn.get("source", "")
            if len(text) > MAX_DIALOGUE_TEXT_LENGTH:
                errors.append(f"{cid}.{tid}: source exceeds {MAX_DIALOGUE_TEXT_LENGTH} characters")
            rich_error = rich_text_error(text, False)
            if rich_error:
                errors.append(f"{cid}.{tid}: {rich_error}")

    chronicle_pools = load_chronicle_pools(root)
    chronicle_by_id: dict[str, dict[str, Any]] = {}
    chronicle_pool_by_id: dict[str, dict[str, Any]] = {}
    for pool in chronicle_pools:
        pool_id = pool.get("poolId")
        if not pool_id:
            errors.append("chronicle pool missing poolId")
            continue
        if pool_id in chronicle_pool_by_id:
            errors.append(f"duplicate chronicle poolId {pool_id}")
            continue
        chronicle_pool_by_id[pool_id] = pool
        allowed_slots = list(pool.get("allowedSlots") or [])
        active_count = 0
        normalized_texts: dict[str, str] = {}
        for template in pool.get("templates") or []:
            template_id = template.get("templateId")
            if not template_id:
                errors.append(f"{pool_id}: chronicle template missing templateId")
                continue
            if template_id in chronicle_by_id:
                errors.append(f"duplicate chronicle templateId {template_id}")
                continue
            if not template_id.startswith(pool_id + "."):
                errors.append(f"{template_id}: templateId must be namespaced below {pool_id}")
            source = template.get("source", "")
            if len(source) > MAX_CHRONICLE_TEXT_LENGTH:
                errors.append(
                    f"{template_id}: source exceeds {MAX_CHRONICLE_TEXT_LENGTH} characters"
                )
            syntax = placeholder_syntax_error(source)
            if syntax:
                errors.append(
                    f"{template_id}: source placeholder syntax is malformed ({syntax})"
                )
            slots = placeholder_tokens(source)
            unknown_slots = slots - set(allowed_slots)
            if unknown_slots:
                errors.append(
                    f"{template_id}: slots {sorted(unknown_slots)!r} are not allowed by {pool_id}"
                )
            rich_error = rich_text_error(source, False)
            if rich_error:
                errors.append(f"{template_id}: {rich_error}")
            normalized = normalized_chronicle_text(source)
            if normalized in normalized_texts:
                errors.append(
                    f"{template_id}: duplicate normalized chronicle text with "
                    f"{normalized_texts[normalized]}"
                )
            else:
                normalized_texts[normalized] = template_id
            if not template.get("deprecated", False):
                active_count += 1
            enriched = dict(template)
            enriched["poolId"] = pool_id
            enriched["allowedSlots"] = allowed_slots
            enriched["family"] = pool.get("family", "")
            chronicle_by_id[template_id] = enriched
        minimum = pool.get("minimumPublished", 0)
        if not isinstance(minimum, int) or minimum < 1:
            errors.append(f"{pool_id}: minimumPublished must be a positive integer")
        elif active_count < minimum:
            errors.append(
                f"{pool_id}: has {active_count} active templates, below minimumPublished {minimum}"
            )

    stability = load_json(root / "contracts" / "chronicle-stability.json")
    stable_pools: dict[str, dict[str, Any]] = {}
    for item in stability.get("pools") or []:
        pool_id = item.get("poolId")
        if pool_id in stable_pools:
            errors.append(f"duplicate chronicle stability pool {pool_id}")
            continue
        stable_pools[pool_id] = item
    for pool_id, pool in chronicle_pool_by_id.items():
        stable = stable_pools.get(pool_id)
        if stable is None:
            errors.append(f"{pool_id}: missing chronicle stability registration")
            continue
        high = stable.get("highestStableNumber")
        if not isinstance(high, int) or high < 1:
            continue
        actual = {item.get("templateId") for item in pool.get("templates") or []}
        expected = {f"{pool_id}.{number:03d}" for number in range(1, high + 1)}
        for template_id in sorted(expected - actual):
            errors.append(
                f"{template_id}: persisted chronicle templateId was removed; deprecate it instead"
            )
        for template_id in sorted(actual - expected):
            errors.append(
                f"{template_id}: chronicle templateId is not registered in the stability contract"
            )
    for pool_id in sorted(set(stable_pools) - set(chronicle_pool_by_id)):
        errors.append(f"{pool_id}: persisted chronicle pool was removed")

    used_turn_exceptions: set[tuple[str, str]] = set()
    for locale in published:
        if locale == SOURCE_LOCALE:
            continue
        locale_entries: dict[str, dict[str, Any]] = {}
        for item in load_ui_locale(root, locale):
            key = item.get("key")
            if not key:
                continue
            if key in locale_entries:
                errors.append(f"{locale}: duplicate translation {key}")
                continue
            locale_entries[key] = item
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
            text = loc.get("text", "")
            if len(text) > MAX_UI_TEXT_LENGTH:
                errors.append(f"{locale}: {key}: translation exceeds {MAX_UI_TEXT_LENGTH} characters")
            max_length = source_entry.get("maxLength")
            if isinstance(max_length, int) and len(text) > max_length:
                errors.append(f"{locale}: {key}: translation exceeds maxLength {max_length}")
            rich_error = rich_text_error(text, bool(source_entry.get("richText")))
            if rich_error:
                errors.append(f"{locale}: {key}: {rich_error}")
        extra = set(locale_entries) - set(ui_by_key)
        for key in sorted(extra):
            errors.append(f"{locale}: unknown translation key {key}")

        loc_dialogue: dict[str, dict[str, Any]] = {}
        for item in load_dialogue_locale(root, locale):
            cid = item.get("candidateId")
            if not cid:
                continue
            if cid in loc_dialogue:
                errors.append(f"{locale}: duplicate dialogue candidate {cid}")
                continue
            loc_dialogue[cid] = item
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
            if src_ids != loc_ids:
                exception_key = (locale, cid)
                expected = DIALOGUE_TURN_EXCEPTIONS.get(exception_key)
                actual = (tuple(src_ids), tuple(loc_ids))
                if expected != actual:
                    errors.append(
                        f"{locale}: {cid}: turn structure {actual!r} does not match source "
                        "or an explicit legacy exception"
                    )
                else:
                    used_turn_exceptions.add(exception_key)
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
                text = loc_turn.get("text", "")
                if len(text) > MAX_DIALOGUE_TEXT_LENGTH:
                    errors.append(
                        f"{locale}: {cid}.{src_turn.get('turnId')}: translation exceeds "
                        f"{MAX_DIALOGUE_TEXT_LENGTH} characters"
                    )
                rich_error = rich_text_error(text, False)
                if rich_error:
                    errors.append(f"{locale}: {cid}.{src_turn.get('turnId')}: {rich_error}")
            for tid in loc_ids[shared:]:
                extra = loc_by_id[tid]
                if extra.get("speakerSlot") is None or extra.get("text") in (None, ""):
                    errors.append(f"{locale}: {cid}.{tid}: extra locale turn is incomplete")
                elif len(extra["text"]) > MAX_DIALOGUE_TEXT_LENGTH:
                    errors.append(
                        f"{locale}: {cid}.{tid}: translation exceeds "
                        f"{MAX_DIALOGUE_TEXT_LENGTH} characters"
                    )
                else:
                    rich_error = rich_text_error(extra["text"], False)
                    if rich_error:
                        errors.append(f"{locale}: {cid}.{tid}: {rich_error}")
        extra_cids = set(loc_dialogue) - set(dialogue_by_id)
        for cid in sorted(extra_cids):
            errors.append(f"{locale}: unknown dialogue candidate {cid}")

        locale_chronicle: dict[str, dict[str, Any]] = {}
        for item in load_chronicle_locale(root, locale):
            template_id = item.get("templateId")
            if not template_id:
                continue
            if template_id in locale_chronicle:
                errors.append(f"{locale}: duplicate chronicle template {template_id}")
                continue
            locale_chronicle[template_id] = item
        for template_id, source_template in chronicle_by_id.items():
            loc = locale_chronicle.get(template_id)
            if loc is None:
                errors.append(f"{locale}: missing chronicle template {template_id}")
                continue
            if loc.get("status") == "draft":
                errors.append(f"{locale}: draft chronicle template {template_id}")
            expected = chronicle_template_hash(
                source=source_template.get("source", ""),
                description=source_template.get("description", ""),
                pool_id=source_template.get("poolId", ""),
                allowed_slots=list(source_template.get("allowedSlots") or []),
            )
            if loc.get("sourceHash") != expected:
                errors.append(f"{locale}: stale chronicle template {template_id}")
            source_tokens = placeholder_tokens(source_template.get("source", ""))
            text_tokens = placeholder_tokens(loc.get("text", ""))
            if source_tokens != text_tokens:
                errors.append(
                    f"{locale}: {template_id}: chronicle translation placeholders differ"
                )
            syntax = placeholder_syntax_error(loc.get("text", ""))
            if syntax:
                errors.append(
                    f"{locale}: {template_id}: chronicle placeholder syntax is malformed ({syntax})"
                )
            text = loc.get("text", "")
            if len(text) > MAX_CHRONICLE_TEXT_LENGTH:
                errors.append(
                    f"{locale}: {template_id}: translation exceeds "
                    f"{MAX_CHRONICLE_TEXT_LENGTH} characters"
                )
            rich_error = rich_text_error(text, False)
            if rich_error:
                errors.append(f"{locale}: {template_id}: {rich_error}")
        extra_templates = set(locale_chronicle) - set(chronicle_by_id)
        for template_id in sorted(extra_templates):
            errors.append(f"{locale}: unknown chronicle template {template_id}")

    unused_exceptions = set(DIALOGUE_TURN_EXCEPTIONS) - used_turn_exceptions
    for locale, cid in sorted(unused_exceptions):
        if locale in published:
            errors.append(f"{locale}: stale dialogue turn exception {cid}")

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


def compact_chronicle(root: Path, locale: str) -> dict[str, Any]:
    locale_map = None
    if locale != SOURCE_LOCALE:
        locale_map = {
            item["templateId"]: item for item in load_chronicle_locale(root, locale)
        }
    pools: dict[str, list[dict[str, Any]]] = {}
    for pool in sorted(load_chronicle_pools(root), key=lambda item: item["poolId"]):
        templates: list[dict[str, Any]] = []
        for template in sorted(pool["templates"], key=lambda item: item["templateId"]):
            template_id = template["templateId"]
            text = template["source"] if locale == SOURCE_LOCALE else locale_map[template_id]["text"]
            templates.append({
                "id": template_id,
                "text": text,
                "deprecated": bool(template.get("deprecated", False)),
            })
        pools[pool["poolId"]] = templates
    return {
        "schemaVersion": SCHEMA_VERSION,
        "locale": locale,
        "pools": pools,
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
        chronicle = compact_chronicle(root, locale)
        files[f"chronicle/{locale}.json"] = dumps(chronicle).encode("utf-8")
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
                # Keep unknown files only if outside generated/translations/dialogue/chronicle.
                rel = existing.relative_to(dist).as_posix()
                if rel.startswith(("generated/", "translations/", "dialogue/", "chronicle/")):
                    existing.unlink()
    for relative, data in files.items():
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
    return written
