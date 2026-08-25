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
DIALOGUE_SCHEMA_VERSION = 2
SOURCE_LOCALE = "zh"
FALLBACK_LOCALE = "en"
TURN_LETTERS = "abcdefghijklmnopqrstuvwxyz"
MAX_UI_TEXT_LENGTH = 10000
MAX_DIALOGUE_TEXT_LENGTH = 2000
MAX_CHRONICLE_TEXT_LENGTH = 2000
ALLOWED_RICH_TEXT_TAGS = {"b", "i", "color"}
ALLOWED_DIALOGUE_EMOTIONS = {
    "neutral", "joy", "affection", "hope", "relief", "sadness", "grief",
    "anger", "anxiety", "fear", "guilt", "embarrassment", "exhaustion",
}
ALLOWED_DIALOGUE_INTENSITIES = {"calm", "mild", "strong", "breaking"}
ALLOWED_DIALOGUE_STANCES = {
    "open", "supportive", "intimate", "awkward", "guarded", "defensive", "hostile",
}
ALLOWED_DIALOGUE_VOICES = {
    "hothead", "crybaby", "loud", "eater", "nervous", "jumpy", "gentle",
    "curious", "slow", "early", "night", "sleepy",
}
ALLOWED_PERSON_FORMS = {
    "subject", "object", "possessive", "possessiveCapitalized",
    "pairSubject", "pairObject",
    "pairPossessive", "pairReflexive",
}
PERSON_SLOTS = {"actor", "other", "third", "subject", "a", "b"}
SEMANTIC_FORM_RE = re.compile(
    r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)\}(?!\})"
)
MIN_ACTIVE_CHRONICLE_TEMPLATES = 900
MAX_ACTIVE_CHRONICLE_TEMPLATES = 2200
CHRONICLE_ACTIVE_FAMILIES = (
    "routine", "support", "relationship", "colony", "dark", "connective",
)
CHRONICLE_COMPATIBILITY_FILE = "compatibility/legacy-pair.json"
CHRONICLE_ANGLE_FLOORS = {
    "high-frequency base": 120,
    "high-frequency relationship": 90,
    "high-frequency actor trait": 120,
    "support and growth": 60,
    "relationship events": 140,
    "colony and stress": 64,
    "dark events": 90,
    "shared history and connective": 60,
}

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


PROMPT_SLOT_RE = re.compile(r"\[\[([a-z][a-zA-Z0-9]*)\]\]")


def prompt_slots(text: str) -> set[str]:
    return {match.group(1) for match in PROMPT_SLOT_RE.finditer(text or "")}


def prompt_syntax_error(text: str) -> str | None:
    stripped = PROMPT_SLOT_RE.sub("", text or "")
    return "malformed [[slot]] token" if "[[" in stripped or "]]" in stripped else None


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
            "chronicle-migration",
            "prompt-source", "prompt-locale",
        )
    }
    routes: list[tuple[Path, str, str | None]] = [
        (root / "manifest.json", "manifest", None),
        (root / "contracts" / "chronicle-stability.json", "chronicle-stability", None),
        (root / "contracts" / "chronicle-migration.json", "chronicle-migration", None),
    ]
    routes.extend((path, "ui-source", None) for path in iter_ui_source_files(root))
    routes.extend((path, "dialogue-source", None) for path in iter_dialogue_source_files(root))
    routes.extend((path, "chronicle-source", None) for path in iter_chronicle_source_files(root))
    routes.extend((path, "prompt-source", None) for path in iter_prompt_source_files(root))
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
                for path in sorted_paths(locale_dir / "chronicle", "**/*.json")
            )
            routes.extend(
                (path, "prompt-locale", locale)
                for path in sorted_paths(locale_dir / "prompts", "*.json")
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
                            allowed_slots: list[str], angle: str = "",
                            participant_mode: str = "",
                            required_slots: list[str] | None = None) -> str:
    payload = {
        "allowedSlots": sorted(allowed_slots),
        "angle": angle,
        "description": description or "",
        "participantMode": participant_mode,
        "poolId": pool_id,
        "requiredSlots": sorted(required_slots or []),
        "source": source,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def chronicle_migration_parity_hash(*, zh_text: str, en_text: str,
                                    target_kind: str, required_slots: Iterable[str],
                                    participant_mode: str) -> str:
    """Hash the approved bilingual text and semantic shape of one migration side."""
    payload = {
        "en": en_text or "",
        "participantMode": participant_mode or "",
        "requiredSlots": sorted(required_slots or []),
        "targetKind": target_kind or "",
        "zh": zh_text or "",
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def prompt_hash(*, source: str, description: str, required_slots: list[str]) -> str:
    payload = {
        "description": description or "",
        "requiredSlots": sorted(required_slots),
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
    return sorted_paths(root / "catalog" / "chronicle", "**/*.json")


def iter_prompt_source_files(root: Path) -> list[Path]:
    return sorted_paths(root / "catalog" / "prompts", "*.json")


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
    for path in sorted_paths(root / "locales" / locale / "chronicle", "**/*.json"):
        payload = load_json(path)
        templates.extend(payload.get("templates", []))
    return templates


def load_prompt_sources(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in iter_prompt_source_files(root):
        entries.extend(load_json(path).get("entries", []))
    return entries


def load_prompt_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted_paths(root / "locales" / locale / "prompts", "*.json"):
        entries.extend(load_json(path).get("entries", []))
    return entries


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

    expected_chronicle_files = {
        *(f"{family}.json" for family in CHRONICLE_ACTIVE_FAMILIES),
        CHRONICLE_COMPATIBILITY_FILE,
    }
    source_root = root / "catalog" / "chronicle"
    actual_source_files = {
        path.relative_to(source_root).as_posix()
        for path in iter_chronicle_source_files(root)
    }
    if actual_source_files != expected_chronicle_files:
        errors.append(
            "chronicle source layout is not canonical: missing=" +
            repr(sorted(expected_chronicle_files - actual_source_files)) +
            " extra=" + repr(sorted(actual_source_files - expected_chronicle_files))
        )
    for locale in published:
        if locale == SOURCE_LOCALE:
            continue
        locale_root = root / "locales" / locale / "chronicle"
        actual_locale_files = {
            path.relative_to(locale_root).as_posix()
            for path in sorted_paths(locale_root, "**/*.json")
        }
        if actual_locale_files != expected_chronicle_files:
            errors.append(
                f"chronicle locale layout for {locale} is not canonical: missing=" +
                repr(sorted(expected_chronicle_files - actual_locale_files)) +
                " extra=" + repr(sorted(actual_locale_files - expected_chronicle_files))
            )

    for family in CHRONICLE_ACTIVE_FAMILIES:
        family_path = source_root / f"{family}.json"
        if not family_path.is_file():
            continue
        payload = load_json(family_path)
        if payload.get("family") != family:
            errors.append(f"chronicle/{family}.json must declare family {family}")
        for pool in payload.get("pools") or []:
            for template in pool.get("templates") or []:
                if template.get("deprecated", False):
                    errors.append(
                        f"{template.get('templateId')}: deprecated templates belong only in "
                        f"{CHRONICLE_COMPATIBILITY_FILE}"
                    )
    compatibility_path = source_root / CHRONICLE_COMPATIBILITY_FILE
    if compatibility_path.is_file():
        compatibility = load_json(compatibility_path)
        if compatibility.get("family") != "compatibility":
            errors.append("legacy-pair.json must declare family compatibility")
        for pool in compatibility.get("pools") or []:
            if pool.get("angle") != "compatibility" or \
                    pool.get("participantMode") != "compatibilityPair":
                errors.append(f"{pool.get('poolId')}: invalid compatibility pool contract")
            for template in pool.get("templates") or []:
                if not template.get("deprecated", False):
                    errors.append(
                        f"{template.get('templateId')}: compatibility template must be deprecated"
                    )

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
        selection = candidate.get("selection") or {}
        actors = selection.get("actors") or []
        slots: set[int] = set()
        for actor in actors:
            slot = actor.get("slot")
            if not isinstance(slot, int) or slot < -1:
                errors.append(f"{cid}: selection actor slot must be -1 or greater")
                continue
            if slot in slots:
                errors.append(f"{cid}: duplicate selection actor slot {slot}")
            slots.add(slot)
            for key, allowed in (
                ("emotions", ALLOWED_DIALOGUE_EMOTIONS),
                ("intensities", ALLOWED_DIALOGUE_INTENSITIES),
                ("stances", ALLOWED_DIALOGUE_STANCES),
            ):
                unknown = set(actor.get(key) or []) - allowed
                if unknown:
                    errors.append(f"{cid}: unknown {key} {sorted(unknown)!r}")
            voices = actor.get("voices") or []
            if any(not isinstance(item, str) or not item for item in voices):
                errors.append(f"{cid}: voices must be non-empty strings")
            unknown_voices = set(voices) - ALLOWED_DIALOGUE_VOICES
            if unknown_voices:
                errors.append(f"{cid}: unknown voices {sorted(unknown_voices)!r}")
        weight = candidate.get("weight")
        if not isinstance(weight, int) or weight < 1 or weight > 100:
            errors.append(f"{cid}: weight must be an integer from 1 to 100")
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
    chronicle_active_by_pool: dict[str, int] = {}
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
        angle = pool.get("angle", "")
        participant_mode = pool.get("participantMode", "")
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
            required_slots = set(template.get("requiredSlots") or [])
            if slots != required_slots:
                errors.append(
                    f"{template_id}: requiredSlots must exactly match source placeholders"
                )
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
                if "pair" in slots:
                    errors.append(f"{template_id}: active chronicle template cannot use pair")
                if any(mark in source for mark in ",;:!?"):
                    errors.append(
                        f"{template_id}: active Chinese Chronicle source uses ASCII punctuation"
                    )
            enriched = dict(template)
            enriched["poolId"] = pool_id
            enriched["allowedSlots"] = allowed_slots
            enriched["angle"] = angle
            enriched["participantMode"] = participant_mode
            enriched["family"] = pool.get("family", "")
            chronicle_by_id[template_id] = enriched
        minimum = pool.get("minimumPublished", 0)
        if not isinstance(minimum, int) or minimum < 0:
            errors.append(f"{pool_id}: minimumPublished must be a non-negative integer")
        elif active_count < minimum:
            errors.append(
                f"{pool_id}: has {active_count} active templates, below minimumPublished {minimum}"
            )
        chronicle_active_by_pool[pool_id] = active_count

    active_chronicle_total = sum(chronicle_active_by_pool.values())
    if not MIN_ACTIVE_CHRONICLE_TEMPLATES <= active_chronicle_total <= \
            MAX_ACTIVE_CHRONICLE_TEMPLATES:
        errors.append(
            "active Chronicle template total "
            f"{active_chronicle_total} is outside release range "
            f"{MIN_ACTIVE_CHRONICLE_TEMPLATES}–{MAX_ACTIVE_CHRONICLE_TEMPLATES}"
        )

    def angle_count(predicate: Any) -> int:
        return sum(
            chronicle_active_by_pool.get(pool_id, 0)
            for pool_id, pool in chronicle_pool_by_id.items()
            if predicate(pool)
        )

    chronicle_angle_counts = {
        "high-frequency base": angle_count(
            lambda pool: pool.get("family") == "routine" and pool.get("angle") == "base"
        ),
        "high-frequency relationship": angle_count(
            lambda pool: pool.get("family") == "routine" and
            pool.get("angle") == "relationship"
        ),
        "high-frequency actor trait": angle_count(
            lambda pool: pool.get("family") == "routine" and
            pool.get("angle") == "actorTrait"
        ),
        "support and growth": angle_count(lambda pool: pool.get("family") == "support"),
        "relationship events": angle_count(
            lambda pool: pool.get("family") == "relationship"
        ),
        "colony and stress": angle_count(lambda pool: pool.get("family") == "colony"),
        "dark events": angle_count(lambda pool: pool.get("family") == "dark"),
        "shared history and connective": angle_count(
            lambda pool: pool.get("angle") == "sharedHistory" or
            pool.get("family") == "connective"
        ),
    }
    for name, floor in CHRONICLE_ANGLE_FLOORS.items():
        actual = chronicle_angle_counts[name]
        if actual < floor:
            errors.append(
                f"Chronicle {name} has {actual} active templates, below release floor {floor}"
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

    migration = load_json(root / "contracts" / "chronicle-migration.json")
    mappings = list(migration.get("mappings") or [])
    legacy_story_keys = {
        item.get("key") for item in ui_entries
        if str(item.get("key", "")).startswith("STRINGS.SOCIAL.LOG_STORY.")
    }
    mapped_keys = [item.get("legacyKey") for item in mappings]
    if len(mappings) != migration.get("expectedLegacyCount"):
        errors.append("chronicle migration count does not match expectedLegacyCount")
    if len(mapped_keys) != len(set(mapped_keys)):
        errors.append("chronicle migration contains duplicate legacy keys")
    if set(mapped_keys) != legacy_story_keys:
        missing_keys = sorted(legacy_story_keys - set(mapped_keys))
        if missing_keys:
            errors.append("migration.legacy-key-unmapped: " + ", ".join(missing_keys))
        errors.append("chronicle migration must cover every LOG_STORY key exactly once")
    active_legacy_keys: list[str] = []
    for template_id, template in chronicle_by_id.items():
        if template.get("deprecated", False):
            continue
        if "pair" in placeholder_tokens(template.get("source", "")):
            errors.append(f"{template_id}: active chronicle pair slot survived migration")
        legacy_key = template.get("legacyKey")
        if legacy_key:
            active_legacy_keys.append(legacy_key)
    if len(active_legacy_keys) != len(set(active_legacy_keys)):
        errors.append("multiple active chronicle templates claim the same legacyKey")
    en_ui_by_key = {
        item.get("key"): item for item in load_ui_locale(root, "en") if item.get("key")
    }
    en_chronicle_by_id = {
        item.get("templateId"): item for item in load_chronicle_locale(root, "en")
        if item.get("templateId")
    }
    for migration_locale in published:
        migration_texts: dict[str, str] = {}
        localized_ui = ui_by_key if migration_locale == SOURCE_LOCALE else {
            item.get("key"): item for item in load_ui_locale(root, migration_locale)
            if item.get("key")
        }
        for mapping in mappings:
            if mapping.get("targetKind") not in {"body", "lead", "tail", "merge"}:
                continue
            localized = localized_ui.get(mapping.get("legacyKey"), {})
            text = localized.get("source", "") if migration_locale == SOURCE_LOCALE \
                else localized.get("text", "")
            prior = migration_texts.get(text)
            if text and prior and prior != mapping.get("targetId"):
                errors.append(
                    f"migration.parity-mismatch: {migration_locale} legacy text is ambiguous"
                )
            elif text:
                migration_texts[text] = mapping.get("targetId")
    for mapping in mappings:
        legacy_key = mapping.get("legacyKey")
        target_kind = mapping.get("targetKind")
        target_id = mapping.get("targetId")
        legacy_source = ui_by_key.get(legacy_key, {})
        legacy_en = en_ui_by_key.get(legacy_key, {})
        actual_legacy_hash = chronicle_migration_parity_hash(
            zh_text=legacy_source.get("source", ""),
            en_text=legacy_en.get("text", ""), target_kind="legacy",
            required_slots=placeholder_tokens(legacy_source.get("source", "")),
            participant_mode="legacy",
        )
        actual_target_hash = ""
        if target_kind in {"body", "lead", "tail", "merge"}:
            if target_id not in chronicle_by_id:
                errors.append(f"{legacy_key}: missing Chronicle target {target_id}")
            else:
                target = chronicle_by_id[target_id]
                localized = en_chronicle_by_id.get(target_id, {})
                actual_target_hash = chronicle_migration_parity_hash(
                    zh_text=target.get("source", ""), en_text=localized.get("text", ""),
                    target_kind=target_kind,
                    required_slots=target.get("requiredSlots") or [],
                    participant_mode=target.get("participantMode", ""),
                )
        elif target_id not in ui_by_key:
            errors.append(f"{legacy_key}: missing shared UI target {target_id}")
        else:
            target = ui_by_key[target_id]
            localized = en_ui_by_key.get(target_id, {})
            actual_target_hash = chronicle_migration_parity_hash(
                zh_text=target.get("source", ""), en_text=localized.get("text", ""),
                target_kind=target_kind,
                required_slots=placeholder_tokens(target.get("source", "")),
                participant_mode="ui" if target_kind == "uiFrame" else "slot",
            )
        if (mapping.get("parityStatus") != "approved" or
                mapping.get("legacyParityHash") != actual_legacy_hash or
                mapping.get("targetParityHash") != actual_target_hash):
            errors.append(f"migration.parity-mismatch: {legacy_key}")

    prompt_by_id: dict[str, dict[str, Any]] = {}
    for entry in load_prompt_sources(root):
        prompt_id = entry.get("promptId")
        if not prompt_id:
            errors.append("prompt entry missing promptId")
            continue
        if prompt_id in prompt_by_id:
            errors.append(f"duplicate promptId {prompt_id}")
            continue
        prompt_by_id[prompt_id] = entry
        source = entry.get("source", "")
        required = set(entry.get("requiredSlots") or [])
        if required != prompt_slots(source):
            errors.append(f"{prompt_id}: requiredSlots do not match prompt slots")
        syntax = prompt_syntax_error(source)
        if syntax:
            errors.append(f"{prompt_id}: {syntax}")

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
                angle=source_template.get("angle", ""),
                participant_mode=source_template.get("participantMode", ""),
                required_slots=list(source_template.get("requiredSlots") or []),
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
            for form_match in SEMANTIC_FORM_RE.finditer(text):
                form_slot, form_name = form_match.groups()
                if form_slot not in PERSON_SLOTS or form_name not in ALLOWED_PERSON_FORMS:
                    errors.append(
                        f"{locale}: {template_id}: unsupported semantic person form "
                        f"{form_slot}:{form_name}"
                    )
            if (locale == "en" and not source_template.get("deprecated", False) and
                    re.search(r"\{(?:actor|other|third|subject|a|b)\}'s", text)):
                errors.append(
                    f"{locale}: {template_id}: raw person possessive bypasses semantic form"
                )
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

        locale_prompts: dict[str, dict[str, Any]] = {}
        for item in load_prompt_locale(root, locale):
            prompt_id = item.get("promptId")
            if prompt_id in locale_prompts:
                errors.append(f"{locale}: duplicate prompt {prompt_id}")
                continue
            locale_prompts[prompt_id] = item
        for prompt_id, source_prompt in prompt_by_id.items():
            loc = locale_prompts.get(prompt_id)
            if loc is None:
                errors.append(f"{locale}: missing prompt {prompt_id}")
                continue
            if loc.get("status") == "draft":
                errors.append(f"{locale}: draft prompt {prompt_id}")
            required = list(source_prompt.get("requiredSlots") or [])
            expected = prompt_hash(source=source_prompt.get("source", ""),
                description=source_prompt.get("description", ""),
                required_slots=required)
            if loc.get("sourceHash") != expected:
                errors.append(f"{locale}: stale prompt {prompt_id}")
            if prompt_slots(loc.get("text", "")) != set(required):
                errors.append(f"{locale}: {prompt_id}: prompt slots differ")
            syntax = prompt_syntax_error(loc.get("text", ""))
            if syntax:
                errors.append(f"{locale}: {prompt_id}: {syntax}")
        for prompt_id in sorted(set(locale_prompts) - set(prompt_by_id)):
            errors.append(f"{locale}: unknown prompt {prompt_id}")

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

    runtime_candidates: list[dict[str, Any]] = []
    ordinals: dict[str, int] = {}

    for candidate in sources:
        cid = candidate["candidateId"]
        src_turns = candidate["turns"]
        if locale == SOURCE_LOCALE:
            turn_texts = [(turn["speakerSlot"], turn["source"]) for turn in src_turns]
            runtime_turns = [
                {"turnId": turn["turnId"], "speakerSlot": turn["speakerSlot"],
                 "text": turn["source"]}
                for turn in src_turns
            ]
        else:
            loc = locale_map[cid]
            turn_texts = [(turn["speakerSlot"], turn["text"]) for turn in loc["turns"]]
            runtime_turns = [
                {"turnId": turn["turnId"], "speakerSlot": turn["speakerSlot"],
                 "text": turn["text"]}
                for turn in loc["turns"]
            ]
        selection = candidate.get("selection") or {}
        ordinal_key = candidate["storyletId"]
        ordinals[ordinal_key] = ordinals.get(ordinal_key, 0) + 1
        runtime_candidates.append({
            "candidateId": cid,
            "storyletId": candidate["storyletId"],
            "selection": selection,
            "weight": candidate.get("weight", 1),
            "ordinal": ordinals[ordinal_key],
            "turns": runtime_turns,
        })

    return {
        "schemaVersion": DIALOGUE_SCHEMA_VERSION,
        "locale": locale,
        "runtimeCandidates": runtime_candidates,
    }


def compact_ui(root: Path, locale: str) -> dict[str, Any]:
    sources = load_ui_sources(root)
    localized = None if locale == SOURCE_LOCALE else {
        item["key"]: item["text"] for item in load_ui_locale(root, locale)
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "locale": locale,
        "entries": [
            {
                "key": item["key"],
                "text": item["source"] if localized is None else localized[item["key"]],
                "requiredSlots": sorted(arg["token"] for arg in item.get("arguments") or []),
                "richText": bool(item.get("richText", False)),
            }
            for item in sources
        ],
    }


def compact_prompts(root: Path, locale: str) -> dict[str, Any]:
    sources = load_prompt_sources(root)
    localized = None if locale == SOURCE_LOCALE else {
        item["promptId"]: item["text"] for item in load_prompt_locale(root, locale)
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "locale": locale,
        "entries": [
            {
                "promptId": item["promptId"],
                "text": item["source"] if localized is None else localized[item["promptId"]],
                "requiredSlots": list(item.get("requiredSlots") or []),
            }
            for item in sorted(sources, key=lambda value: value["promptId"])
        ],
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
                "ordinal": int(template.get("ordinal", 0)),
                "requiredSlots": list(template.get("requiredSlots") or []),
            })
        pools[pool["poolId"]] = {
            "angle": pool.get("angle", ""),
            "participantMode": pool.get("participantMode", ""),
            "templates": templates,
        }
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
        ui = compact_ui(root, locale)
        files[f"ui/{locale}.json"] = dumps(ui).encode("utf-8")
        prompts = compact_prompts(root, locale)
        files[f"prompts/{locale}.json"] = dumps(prompts).encode("utf-8")
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
                # Keep unknown files only if outside generated runtime-owned directories.
                rel = existing.relative_to(dist).as_posix()
                if rel.startswith(("generated/", "translations/", "ui/", "dialogue/",
                                   "chronicle/", "prompts/")):
                    existing.unlink()
    for relative, data in files.items():
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
    return written
