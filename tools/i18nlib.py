#!/usr/bin/env python3
"""Schema-v2 validation and deterministic, unit-resolved frozen export."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2
FORMAT_ITEM_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*|\d+)(?:\s*,\s*[-+]?\d+)?(?:\s*:[^{}]*)?\}(?!\})")
SEMANTIC_FORM_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
PROMPT_SLOT_RE = re.compile(r"\[\[([a-z][a-zA-Z0-9]*)\]\]")
LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
ALLOWED_RICH_TEXT_TAGS = {"b", "i", "color"}
ALLOWED_DIALOGUE_EMOTIONS = {"neutral", "joy", "affection", "hope", "relief", "sadness", "grief", "anger", "anxiety", "fear", "guilt", "embarrassment", "exhaustion"}
ALLOWED_DIALOGUE_INTENSITIES = {"calm", "mild", "strong", "breaking"}
ALLOWED_DIALOGUE_STANCES = {"open", "supportive", "intimate", "awkward", "guarded", "defensive", "hostile"}
ALLOWED_DIALOGUE_PERSONALITIES = {"hothead", "crybaby", "loud", "eater", "nervous", "jumpy", "gentle", "curious", "slow", "early", "night", "sleepy", "athlete"}
ALLOWED_DIALOGUE_VOICES = ALLOWED_DIALOGUE_PERSONALITIES
ALLOWED_DIALOGUE_MOODS = {"buoyant", "settled", "discouraged", "strained", "overwhelmed"}
ALLOWED_CONVERSATION_KINDS = {"recent_thing", "amount_state", "current_job"}
ALLOWED_TOPIC_DOMAINS = {"food", "bed", "decor", "element", "building", "creature", "plant", "equipment", "item", "stress", "morale", "health", "satiety", "stamina", "immunity", "current_job", "energy", "hunger", "oxygen", "unknown"}
ALLOWED_UTTERANCE_MODES = {"query", "statement", "agreement", "disagreement", "musing", "satisfaction", "nominal", "dissatisfaction", "stressing", "segue", "end"}
ALLOWED_APPRAISALS = {"positive", "neutral", "negative", "stressed", "unspecified"}
ALLOWED_RESPONSE_ACTS = {"acknowledge", "reassure", "practical_help", "gentle_boundary", "defer"}
ALLOWED_LISTENER_AVAILABILITIES = {"receptive", "reserved", "unavailable"}
RESOLVED_TOPIC_RE = re.compile(r"^(?:recent|amount|thought)\.[a-z_]+\.[a-z_]+$|^current_job\.[a-z_]+$")
ALLOWED_RELATIONSHIP_STATES = {"Strangers", "Acquainted", "Friends", "Crush", "Couple", "ColdWar", "BrokenUp", "Grieving", "Mourning", "Rival"}
ALLOWED_ARGUMENT_CAUSES = {"Unknown", "Stress", "LowAffinity", "TraitClash", "Discord", "Chemistry", "HazardDuty"}
ALLOWED_PERSON_FORMS = {"subject", "object", "possessive", "possessiveCapitalized", "pairSubject", "pairObject", "pairPossessive", "pairReflexive"}
PERSON_SLOTS = {"actor", "other", "third", "subject", "a", "b"}
REPEATED_WORD_RE = re.compile(
    r"\b([^\W\d_]{2,})(?:[\s,.;:!?—–-]+\1){2,}\b", re.IGNORECASE)


def normalize_locale(value: str) -> str:
    return (value or "").strip().replace("_", "-").lower()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def runtime_dumps(value: Any) -> str:
    """Keep large browser/runtime catalogs compact while retaining readable sources."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(value).encode("utf-8"))


def sorted_paths(root: Path, pattern: str) -> list[Path]:
    return sorted((path for path in root.glob(pattern) if path.is_file()), key=lambda path: path.as_posix())


def placeholder_tokens(text: str) -> set[str]:
    return {match.group(1) for match in FORMAT_ITEM_RE.finditer(text or "")}


def semantic_slots(text: str) -> set[str]:
    return placeholder_tokens(text) | {match.group(1) for match in SEMANTIC_FORM_RE.finditer(text or "")}


def prompt_slots(text: str) -> set[str]:
    return {match.group(1) for match in PROMPT_SLOT_RE.finditer(text or "")}


def prompt_syntax_error(text: str) -> str | None:
    stripped = PROMPT_SLOT_RE.sub("", text or "")
    return "malformed [[slot]] token" if "[[" in stripped or "]]" in stripped else None


def placeholder_syntax_error(text: str, semantic: bool = False) -> str | None:
    value = SEMANTIC_FORM_RE.sub("", text or "") if semantic else (text or "")
    index = 0
    while index < len(value):
        if value[index] == "{":
            if index + 1 < len(value) and value[index + 1] == "{":
                index += 2
                continue
            match = FORMAT_ITEM_RE.match(value, index)
            if match is None:
                return f"invalid '{{' at character {index + 1}"
            index = match.end()
            continue
        if value[index] == "}":
            if index + 1 < len(value) and value[index + 1] == "}":
                index += 2
                continue
            return f"unmatched '}}' at character {index + 1}"
        index += 1
    return None


def rich_text_error(text: str, enabled: bool) -> str | None:
    tags = re.findall(r"<\s*/?\s*([A-Za-z][A-Za-z0-9]*)[^>]*>", text or "")
    if tags and not enabled:
        return "rich-text markup is not allowed by the contract"
    unknown = sorted({tag.lower() for tag in tags} - ALLOWED_RICH_TEXT_TAGS)
    return "unsupported rich-text tag(s): " + ", ".join(unknown) if unknown else None


def translation_artifact_error(text: str) -> str | None:
    """Reject obvious runaway MT output without imposing cross-locale sentence shapes."""
    value = text or ""
    if unicodedata.normalize("NFC", value) != value:
        return "text must use NFC-normalized Unicode"
    if len(value) > 4000:
        return "text exceeds the translation-artifact safety ceiling"
    # Short onomatopoeia such as "ha-ha-ha" is legitimate dialogue. Repeated words inside a
    # longer sentence are instead a strong signal of a stuck decoder and must be reviewed.
    if len(value) >= 80 and REPEATED_WORD_RE.search(value):
        return "probable repeated-word translation artifact"
    return None


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object": return isinstance(value, dict)
    if expected == "array": return isinstance(value, list)
    if expected == "string": return isinstance(value, str)
    if expected == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number": return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean": return isinstance(value, bool)
    if expected == "null": return value is None
    return False


def validate_json_schema(value: Any, schema: dict[str, Any], location: str,
                         root_schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    root_schema = root_schema or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return [f"{location}: unsupported schema reference {reference!r}"]
        target: Any = root_schema
        for part in reference[2:].split("/"):
            target = target.get(part) if isinstance(target, dict) else None
        if not isinstance(target, dict):
            return [f"{location}: unresolved schema reference {reference!r}"]
        return validate_json_schema(value, target, location, root_schema)
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_schema_type_matches(value, item) for item in choices):
            return [f"{location}: expected type {' or '.join(choices)}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value {value!r} is not in {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)): errors.append(f"{location}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]): errors.append(f"{location}: string is longer than maxLength")
        if schema.get("pattern") and re.search(schema["pattern"], value) is None: errors.append(f"{location}: value does not match {schema['pattern']!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]: errors.append(f"{location}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]: errors.append(f"{location}: value is above maximum {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)): errors.append(f"{location}: array is shorter than minItems")
        if schema.get("uniqueItems") and len({canonical_json(item) for item in value}) != len(value): errors.append(f"{location}: array items must be unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value): errors.extend(validate_json_schema(item, schema["items"], f"{location}[{index}]", root_schema))
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for required in schema.get("required") or []:
            if required not in value: errors.append(f"{location}: missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties: errors.append(f"{location}: unknown property {key!r}")
        for key, child in properties.items():
            if key in value: errors.extend(validate_json_schema(value[key], child, f"{location}.{key}", root_schema))
    return errors


def load_manifest(root: Path) -> dict[str, Any]:
    return load_json(root / "manifest.json")


def _locale_specs(root: Path) -> dict[str, dict[str, Any]]:
    return {normalize_locale(item["id"]): item for item in load_manifest(root).get("locales", [])}


def shipped_locales(root: Path) -> list[str]:
    return sorted(locale for locale, spec in _locale_specs(root).items() if spec.get("ship"))


def fallback_chain(locale: str, registered: Iterable[str], fallback_locale: str = "en", default_locale: str = "zh") -> list[str]:
    supported = {normalize_locale(item) for item in registered}
    exact = normalize_locale(locale)
    result: list[str] = []
    for candidate in (exact, exact.split("-", 1)[0] if "-" in exact else "", normalize_locale(fallback_locale), normalize_locale(default_locale)):
        if candidate and candidate in supported and candidate not in result: result.append(candidate)
    return result


def iter_ui_contract_files(root: Path) -> list[Path]: return sorted_paths(root / "contracts" / "ui", "*.json")
def iter_prompt_contract_files(root: Path) -> list[Path]: return sorted_paths(root / "contracts" / "prompts", "*.json")
def iter_chronicle_contract_files(root: Path) -> list[Path]:
    return sorted_paths(root / "contracts" / "chronicle", "*.json") + [root / "contracts" / "compatibility" / "legacy-chronicle-text.json"]


def load_ui_contracts(root: Path) -> list[dict[str, Any]]:
    return [item for path in iter_ui_contract_files(root) for item in load_json(path)["entries"]]


def load_prompt_contracts(root: Path) -> list[dict[str, Any]]:
    return [item for path in iter_prompt_contract_files(root) for item in load_json(path)["entries"]]


def load_dialogue_contracts(root: Path) -> list[dict[str, Any]]:
    return load_json(root / "contracts" / "dialogue" / "storylets.json")["storylets"]


def load_topic_coverage(root: Path) -> dict[str, set[str]]:
    payload = load_json(root / "contracts" / "dialogue" / "topic-coverage.json")
    return {normalize_locale(locale): set(value.get("readyTopics", []))
            for locale, value in payload.get("locales", {}).items()}


def load_chronicle_contracts(root: Path) -> list[dict[str, Any]]:
    return [item for path in iter_chronicle_contract_files(root) if path.is_file() for item in load_json(path)["pools"]]


def load_ui_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    return [item for path in sorted_paths(root / "locales" / normalize_locale(locale) / "ui", "*.json") for item in load_json(path)["entries"]]


def load_prompt_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    return [item for path in sorted_paths(root / "locales" / normalize_locale(locale) / "prompts", "*.json") for item in load_json(path)["entries"]]


def load_dialogue_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    return [item for path in sorted_paths(root / "locales" / normalize_locale(locale) / "dialogue", "*.json") for item in load_json(path)["candidates"]]


def load_chronicle_locale(root: Path, locale: str) -> list[dict[str, Any]]:
    return [item for path in sorted_paths(root / "locales" / normalize_locale(locale) / "chronicle", "*.json") for item in load_json(path)["templates"]]


def _schema_routes(root: Path) -> list[tuple[Path, str, str | None]]:
    routes: list[tuple[Path, str, str | None]] = [(root / "manifest.json", "manifest", None)]
    routes.append((root / "glossary.json", "glossary", None))
    routes += [(path, "ui-contract", None) for path in iter_ui_contract_files(root)]
    routes += [(path, "prompt-contract", None) for path in iter_prompt_contract_files(root)]
    routes += [(root / "contracts" / "dialogue" / "storylets.json", "dialogue-contract", None)]
    routes += [(root / "contracts" / "dialogue" / "topic-coverage.json",
                "dialogue-topic-coverage", None)]
    routes += [(path, "chronicle-contract", None) for path in iter_chronicle_contract_files(root)]
    routes += [(path, "link", None) for path in sorted_paths(root / "links", "*.json")]
    routes += [(path, "provenance", normalize_locale(path.stem))
               for path in sorted_paths(root / "provenance", "*.json")]
    routes += [(path, "review-overrides", normalize_locale(path.stem))
               for path in sorted_paths(root / "review-overrides", "*.json")]
    locales_root = root / "locales"
    if locales_root.is_dir():
        for locale_dir in sorted((item for item in locales_root.iterdir() if item.is_dir()), key=lambda item: item.name):
            locale = normalize_locale(locale_dir.name)
            routes += [(path, "text-locale", locale) for path in sorted_paths(locale_dir / "ui", "*.json")]
            routes += [(path, "text-locale", locale) for path in sorted_paths(locale_dir / "prompts", "*.json")]
            routes += [(path, "dialogue-locale", locale) for path in sorted_paths(locale_dir / "dialogue", "*.json")]
            routes += [(path, "chronicle-locale", locale) for path in sorted_paths(locale_dir / "chronicle", "*.json")]
            stability = locale_dir / "stability" / "chronicle.json"
            if stability.is_file(): routes.append((stability, "chronicle-stability", locale))
    return routes


def validate_schema_files(root: Path) -> list[str]:
    schemas = {path.stem.removesuffix(".schema"): load_json(path) for path in sorted_paths(root / "schemas", "*.schema.json")}
    errors: list[str] = []
    for path, schema_name, expected_locale in _schema_routes(root):
        label = path.relative_to(root).as_posix()
        if not path.is_file():
            errors.append(f"{label}: required file is missing")
            continue
        try: payload = load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"{label}: invalid JSON ({error})")
            continue
        schema = schemas.get(schema_name)
        if schema is None:
            errors.append(f"schemas/{schema_name}.schema.json: required schema is missing")
            continue
        errors.extend(validate_json_schema(payload, schema, label))
        if expected_locale is not None and isinstance(payload, dict):
            locale_field = "targetLocale" if schema_name == "provenance" else "locale"
            if normalize_locale(payload.get(locale_field, "")) != expected_locale:
                errors.append(f"{label}: {locale_field} {payload.get(locale_field)!r} "
                              f"does not match file/directory {expected_locale!r}")
    return errors


def _duplicate_errors(items: Iterable[dict[str, Any]], key: str, label: str) -> list[str]:
    seen: set[str] = set(); errors: list[str] = []
    for item in items:
        value = str(item.get(key, ""))
        if value in seen: errors.append(f"{label}: duplicate {key} {value!r}")
        seen.add(value)
    return errors


def _eligible(item: dict[str, Any], contract: dict[str, Any]) -> bool:
    return item.get("status") == "reviewed" and item.get("contractRevision") == contract.get("contractRevision")


def _validate_manifest(root: Path, errors: list[str]) -> None:
    manifest = load_manifest(root)
    if (root / "catalog").exists(): errors.append("release.v1-residue: v1 catalog/ directory must be deleted")
    specs = manifest.get("locales", [])
    ids = [normalize_locale(item.get("id", "")) for item in specs]
    if len(ids) != len(set(ids)): errors.append("manifest.locales: duplicate locale id")
    if any(item != normalize_locale(item) or not LOCALE_RE.fullmatch(item) for item in ids): errors.append("manifest.locales: locale ids must be canonical lowercase BCP 47")
    by_id = {normalize_locale(item.get("id", "")): item for item in specs}
    for role in ("defaultLocale", "fallbackLocale"):
        locale = normalize_locale(manifest.get(role, "")); spec = by_id.get(locale)
        if spec is None: errors.append(f"manifest.{role}: unknown locale {locale!r}")
        elif spec.get("status") != "stable" or not spec.get("ship"): errors.append(f"manifest.{role}: must be stable and shipped")
    for item in specs:
        if item.get("status") == "draft" and item.get("ship"): errors.append(f"manifest.locales: draft locale {item.get('id')!r} cannot ship")
    for directory in sorted((root / "locales").iterdir() if (root / "locales").is_dir() else []):
        if directory.is_dir() and normalize_locale(directory.name) not in by_id: errors.append(f"locales/{directory.name}: locale is not registered in manifest")


def _validate_ui(root: Path, locales: list[str], errors: list[str]) -> None:
    contracts = load_ui_contracts(root); by_id = {item["key"]: item for item in contracts}
    errors.extend(_duplicate_errors(contracts, "key", "contracts/ui"))
    for locale in locales:
        entries = load_ui_locale(root, locale); errors.extend(_duplicate_errors(entries, "key", f"locales/{locale}/ui"))
        for item in entries:
            key = item.get("key", ""); contract = by_id.get(key)
            if contract is None: errors.append(f"locales/{locale}/ui: unknown key {key!r}"); continue
            if item.get("contractRevision", 0) > contract["contractRevision"]: errors.append(f"locales/{locale}/ui: future contract revision for {key}")
            text = item.get("text", ""); syntax = placeholder_syntax_error(text)
            if syntax: errors.append(f"locales/{locale}/ui {key}: {syntax}")
            declared = {str(argument["token"]) for argument in contract["arguments"]}
            if placeholder_tokens(text) != declared: errors.append(f"locales/{locale}/ui {key}: placeholders differ from contract arguments")
            markup = rich_text_error(text, contract["richText"])
            if markup: errors.append(f"locales/{locale}/ui {key}: {markup}")
            if len(text) > contract["maxLength"]: errors.append(f"locales/{locale}/ui {key}: text exceeds maxLength {contract['maxLength']}")
            artifact = translation_artifact_error(text)
            if artifact: errors.append(f"locales/{locale}/ui {key}: {artifact}")


def _validate_prompts(root: Path, locales: list[str], errors: list[str]) -> None:
    contracts = load_prompt_contracts(root); by_id = {item["promptId"]: item for item in contracts}
    errors.extend(_duplicate_errors(contracts, "promptId", "contracts/prompts"))
    for locale in locales:
        entries = load_prompt_locale(root, locale); errors.extend(_duplicate_errors(entries, "promptId", f"locales/{locale}/prompts"))
        for item in entries:
            prompt_id = item.get("promptId", ""); contract = by_id.get(prompt_id)
            if contract is None: errors.append(f"locales/{locale}/prompts: unknown promptId {prompt_id!r}"); continue
            if item.get("contractRevision", 0) > contract["contractRevision"]: errors.append(f"locales/{locale}/prompts: future contract revision for {prompt_id}")
            syntax = prompt_syntax_error(item.get("text", ""))
            if syntax: errors.append(f"locales/{locale}/prompts {prompt_id}: {syntax}")
            if prompt_slots(item.get("text", "")) != set(contract["requiredSlots"]): errors.append(f"locales/{locale}/prompts {prompt_id}: prompt slots differ from contract")
            artifact = translation_artifact_error(item.get("text", ""))
            if artifact: errors.append(f"locales/{locale}/prompts {prompt_id}: {artifact}")


def _validate_selection(selection: dict[str, Any], locale: str, candidate_id: str,
                        actor_slots: set[int], allowed_dimensions: set[str],
                        errors: list[str]) -> None:
    allowed_top = {"actors", "relationshipStates", "causes", "resolvedTopics",
                   "conversationKinds", "topicDomains", "utteranceModes", "appraisals",
                   "responseActs", "listenerAvailabilities", "moodWildcardEmergency"}
    for key in selection:
        if key not in allowed_top: errors.append(f"locales/{locale}/dialogue {candidate_id}: unknown selection dimension {key!r}")
    enum_fields = {"emotions": ALLOWED_DIALOGUE_EMOTIONS,
                   "intensities": ALLOWED_DIALOGUE_INTENSITIES,
                   "stances": ALLOWED_DIALOGUE_STANCES,
                   "voices": ALLOWED_DIALOGUE_VOICES,
                   "personalities": ALLOWED_DIALOGUE_PERSONALITIES,
                   "moods": ALLOWED_DIALOGUE_MOODS}
    for actor in selection.get("actors", []):
        if actor.get("slot") != -1 and actor.get("slot") not in actor_slots: errors.append(f"locales/{locale}/dialogue {candidate_id}: actor selection slot is outside contract")
        for field, allowed in enum_fields.items():
            values = actor.get(field, [])
            if not all(isinstance(value, str) and value in allowed for value in values): errors.append(f"locales/{locale}/dialogue {candidate_id}: invalid {field}")
            if values and field not in allowed_dimensions: errors.append(f"locales/{locale}/dialogue {candidate_id}: {field} is outside contract selectionDimensions")
        for key in actor:
            if key not in {"slot", *enum_fields}: errors.append(f"locales/{locale}/dialogue {candidate_id}: unknown actor selection dimension {key!r}")
    for field, allowed in (("relationshipStates", ALLOWED_RELATIONSHIP_STATES),
                           ("causes", ALLOWED_ARGUMENT_CAUSES),
                           ("conversationKinds", ALLOWED_CONVERSATION_KINDS),
                           ("topicDomains", ALLOWED_TOPIC_DOMAINS),
                           ("utteranceModes", ALLOWED_UTTERANCE_MODES),
                           ("appraisals", ALLOWED_APPRAISALS),
                           ("responseActs", ALLOWED_RESPONSE_ACTS),
                           ("listenerAvailabilities", ALLOWED_LISTENER_AVAILABILITIES)):
        values = selection.get(field, [])
        if not all(isinstance(value, str) and value in allowed for value in values):
            errors.append(f"locales/{locale}/dialogue {candidate_id}: invalid {field}")
        if values and field not in allowed_dimensions:
            errors.append(f"locales/{locale}/dialogue {candidate_id}: {field} is outside contract selectionDimensions")
    topics = selection.get("resolvedTopics", [])
    if not all(isinstance(value, str) and RESOLVED_TOPIC_RE.fullmatch(value)
               for value in topics):
        errors.append(f"locales/{locale}/dialogue {candidate_id}: invalid resolvedTopics")
    if topics and "resolvedTopics" not in allowed_dimensions:
        errors.append(f"locales/{locale}/dialogue {candidate_id}: resolvedTopics is outside contract selectionDimensions")
    if selection.get("moodWildcardEmergency") and "moodWildcardEmergency" not in allowed_dimensions:
        errors.append(f"locales/{locale}/dialogue {candidate_id}: moodWildcardEmergency is outside contract selectionDimensions")


def _validate_dialogue(root: Path, locales: list[str], errors: list[str]) -> None:
    contracts = load_dialogue_contracts(root); by_id = {item["storyletId"]: item for item in contracts}
    errors.extend(_duplicate_errors(contracts, "storyletId", "contracts/dialogue"))
    diversity_by_candidate: dict[str, str] = {}
    selection_by_candidate: dict[str, str] = {}
    coverage = load_topic_coverage(root)
    for locale in locales:
        candidates = load_dialogue_locale(root, locale); errors.extend(_duplicate_errors(candidates, "candidateId", f"locales/{locale}/dialogue"))
        ordinals: set[tuple[str, int]] = set()
        for item in candidates:
            candidate_id = item.get("candidateId", ""); contract = by_id.get(item.get("storyletId", ""))
            if contract is None: errors.append(f"locales/{locale}/dialogue {candidate_id}: unknown storyletId"); continue
            diversity_key = item.get("diversityKey")
            if diversity_key is not None and (not isinstance(diversity_key, str) or not diversity_key.strip()):
                errors.append(f"locales/{locale}/dialogue {candidate_id}: diversityKey must be a non-empty string")
            resolved_diversity = _dialogue_diversity_key(item)
            previous_diversity = diversity_by_candidate.setdefault(candidate_id, resolved_diversity)
            if previous_diversity != resolved_diversity:
                errors.append(f"locales/{locale}/dialogue {candidate_id}: diversityKey differs across locales")
            selection_shape = canonical_json(item.get("selection", {}))
            previous_selection = selection_by_candidate.setdefault(candidate_id, selection_shape)
            if previous_selection != selection_shape:
                errors.append(f"locales/{locale}/dialogue {candidate_id}: selection metadata differs across locales")
            if item.get("contractRevision", 0) > contract["contractRevision"]: errors.append(f"locales/{locale}/dialogue {candidate_id}: future contract revision")
            ordinal_key = (item["storyletId"], item.get("ordinal", 0))
            if ordinal_key in ordinals: errors.append(f"locales/{locale}/dialogue {item['storyletId']}: duplicate ordinal {item.get('ordinal')}")
            ordinals.add(ordinal_key)
            _validate_selection(item.get("selection", {}), locale, candidate_id,
                                set(contract["actorSlots"]),
                                set(contract["selectionDimensions"]), errors)
            turn_ids: set[str] = set()
            for turn in item.get("turns", []):
                if turn.get("turnId") in turn_ids: errors.append(f"locales/{locale}/dialogue {candidate_id}: duplicate turnId {turn.get('turnId')!r}")
                turn_ids.add(turn.get("turnId", ""))
                if turn.get("speakerSlot") not in contract["actorSlots"]: errors.append(f"locales/{locale}/dialogue {candidate_id}: speakerSlot outside contract")
                syntax = placeholder_syntax_error(turn.get("text", ""))
                if syntax: errors.append(f"locales/{locale}/dialogue {candidate_id}/{turn.get('turnId')}: {syntax}")
                artifact = translation_artifact_error(turn.get("text", ""))
                if artifact: errors.append(f"locales/{locale}/dialogue {candidate_id}/{turn.get('turnId')}: {artifact}")
        _validate_ready_topic_matrix(locale, candidates, by_id, coverage.get(locale, set()), errors)


def _validate_ready_topic_matrix(locale: str, candidates: list[dict[str, Any]],
                                 contracts: dict[str, dict[str, Any]], ready: set[str],
                                 errors: list[str]) -> None:
    for topic in sorted(ready):
        if RESOLVED_TOPIC_RE.fullmatch(topic) is None:
            errors.append(f"coverage.{locale}: invalid ready Topic {topic!r}")
            continue
        cells: dict[tuple[str, str], set[str]] = defaultdict(set)
        for item in candidates:
            selection = item.get("selection", {})
            if topic not in selection.get("resolvedTopics", []):
                continue
            contract = contracts.get(item.get("storyletId", ""))
            if item.get("storyletId") != "Casual" or contract is None or not _eligible(item, contract):
                continue
            if selection.get("resolvedTopics") != [topic]:
                errors.append(f"coverage.{locale}.{topic} {item.get('candidateId')}: ready candidate must constrain exactly one resolved Topic")
                continue
            actor_zero = [actor for actor in selection.get("actors", []) if actor.get("slot") == 0]
            if len(actor_zero) != 1 or len(actor_zero[0].get("personalities", [])) != 1 or len(actor_zero[0].get("moods", [])) != 1:
                errors.append(f"coverage.{locale}.{topic} {item.get('candidateId')}: ready candidate needs exactly one slot 0 personality and mood")
                continue
            if any(actor.get("slot") == 1 and actor.get("personalities")
                   for actor in selection.get("actors", [])):
                errors.append(f"coverage.{locale}.{topic} {item.get('candidateId')}: slot 1 personality cannot be mandatory")
            personality = actor_zero[0]["personalities"][0]
            mood = actor_zero[0]["moods"][0]
            cells[(personality, mood)].add(_dialogue_diversity_key(item))
        for personality in sorted(ALLOWED_DIALOGUE_PERSONALITIES):
            for mood in sorted(ALLOWED_DIALOGUE_MOODS):
                count = len(cells.get((personality, mood), set()))
                if count < 5:
                    errors.append(f"coverage.{locale}.{topic}: {personality} × {mood} has {count}/5 unique diversityKey candidates")


def _validate_chronicle(root: Path, locales: list[str], errors: list[str]) -> None:
    contracts = load_chronicle_contracts(root); by_id = {item["poolId"]: item for item in contracts}
    locale_specs = _locale_specs(root)
    errors.extend(_duplicate_errors(contracts, "poolId", "contracts/chronicle"))
    for locale in locales:
        templates = load_chronicle_locale(root, locale); errors.extend(_duplicate_errors(templates, "templateId", f"locales/{locale}/chronicle"))
        ordinals: set[tuple[str, int]] = set(); by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in templates:
            template_id = item.get("templateId", ""); contract = by_id.get(item.get("poolId", ""))
            if contract is None: errors.append(f"locales/{locale}/chronicle {template_id}: unknown poolId"); continue
            by_pool[item["poolId"]].append(item)
            if item.get("contractRevision", 0) > contract["contractRevision"]: errors.append(f"locales/{locale}/chronicle {template_id}: future contract revision")
            ordinal_key = (item["poolId"], item.get("ordinal", 0))
            if ordinal_key in ordinals: errors.append(f"locales/{locale}/chronicle {item['poolId']}: duplicate ordinal {item.get('ordinal')}")
            ordinals.add(ordinal_key)
            text = item.get("text", ""); syntax = placeholder_syntax_error(text, semantic=True)
            if syntax: errors.append(f"locales/{locale}/chronicle {template_id}: {syntax}")
            for match in SEMANTIC_FORM_RE.finditer(text):
                if match.group(1) not in PERSON_SLOTS or match.group(2) not in ALLOWED_PERSON_FORMS: errors.append(f"locales/{locale}/chronicle {template_id}: invalid semantic person form")
            slots = semantic_slots(text)
            if slots != set(item.get("requiredSlots", [])): errors.append(f"locales/{locale}/chronicle {template_id}: requiredSlots must exactly match text placeholders")
            if not slots.issubset(set(contract["allowedSlots"])): errors.append(f"locales/{locale}/chronicle {template_id}: placeholder is outside pool allowedSlots")
            artifact = translation_artifact_error(text)
            if artifact: errors.append(f"locales/{locale}/chronicle {template_id}: {artifact}")
        stability_path = root / "locales" / locale / "stability" / "chronicle.json"
        if not stability_path.is_file():
            spec = locale_specs.get(locale, {})
            locale_root = root / "locales" / locale
            if spec.get("status") == "draft" and spec.get("ship") is False and not locale_root.exists():
                # A registered target locale may intentionally have no authoring tree while a
                # clean-room translation is pending. Once any locale tree exists, its ledger is
                # mandatory again.
                continue
            errors.append(f"locales/{locale}/stability/chronicle.json: required locale-owned stability ledger is missing")
            continue
        stability_items = load_json(stability_path)["pools"]
        errors.extend(_duplicate_errors(stability_items, "poolId",
                                        f"locales/{locale}/stability"))
        high = {item["poolId"]: item["highestStableNumber"] for item in stability_items}
        for pool_id in high:
            if pool_id not in by_id:
                errors.append(f"locales/{locale}/stability {pool_id}: unknown poolId")
        shipped = locale_specs.get(locale, {}).get("ship") is True
        eligible_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for pool_id, items in by_pool.items():
            contract = by_id[pool_id]
            eligible_by_pool[pool_id] = [item for item in items if _eligible(item, contract)]
        for pool_id, highest in high.items():
            current = eligible_by_pool.get(pool_id, []) if shipped else by_pool.get(pool_id, [])
            ordinals_present = {item["ordinal"] for item in current}
            missing = [ordinal for ordinal in range(1, highest + 1) if ordinal not in ordinals_present]
            if missing: errors.append(f"locales/{locale}/stability {pool_id}: published ordinal was removed: {missing[0]}")
            for item in current:
                if item["ordinal"] <= highest and not item.get("templateId", "").endswith(f".{item['ordinal']:03d}"):
                    errors.append(f"locales/{locale}/stability {pool_id}: stable ordinal/id mismatch for {item['templateId']}")
        if shipped:
            for pool_id, items in eligible_by_pool.items():
                highest = high.get(pool_id, 0)
                for item in items:
                    if item["ordinal"] > highest:
                        errors.append(f"locales/{locale}/stability {pool_id}: reviewed ordinal "
                                      f"{item['ordinal']} is above highestStableNumber {highest}")


def _all_content_ids(root: Path, locales: list[str]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for locale in locales:
        result |= {(locale, "dialogue", item["candidateId"]) for item in load_dialogue_locale(root, locale)}
        result |= {(locale, "chronicle", item["templateId"]) for item in load_chronicle_locale(root, locale)}
    return result


def _validate_links(root: Path, locales: list[str], warnings: list[str]) -> None:
    ids = _all_content_ids(root, locales)
    for path in sorted_paths(root / "links", "*.json"):
        for index, link in enumerate(load_json(path).get("links", [])):
            for side in ("from", "to"):
                target = link.get(side, {}); key = (normalize_locale(target.get("locale", "")), target.get("kind", ""), target.get("id", ""))
                if key not in ids: warnings.append(f"{path.relative_to(root)} links[{index}].{side}: missing authoring target {key}")
            target_revision = link.get("targetRevision", 0)
            if target_revision < 1: warnings.append(f"{path.relative_to(root)} links[{index}]: stale target revision")


def _locale_content_files(root: Path, locale: str) -> dict[str, Path]:
    base = root / "locales" / normalize_locale(locale)
    result: dict[str, Path] = {}
    for family in ("ui", "dialogue", "chronicle", "prompts"):
        for path in sorted_paths(base / family, "*.json"):
            result[path.relative_to(base).as_posix()] = path
    return result


def _content_identity(path: Path) -> tuple[Any, ...]:
    payload = load_json(path)
    if "entries" in payload:
        id_name = "key" if payload["entries"] and "key" in payload["entries"][0] else "promptId"
        return tuple(item[id_name] for item in payload["entries"])
    if "candidates" in payload:
        return tuple((item["candidateId"], item["storyletId"],
                      tuple((turn["turnId"], turn["speakerSlot"])
                            for turn in item["turns"]))
                     for item in payload["candidates"])
    if "templates" in payload:
        return tuple((item["templateId"], item["poolId"], item["ordinal"],
                      tuple(item["requiredSlots"])) for item in payload["templates"])
    return ()


def _content_hash(path: Path) -> str:
    return _sha(canonical_json(load_json(path)))


def _validate_provenance(root: Path, locales: list[str], errors: list[str]) -> None:
    manifest = load_manifest(root)
    source_locale = normalize_locale(manifest["defaultLocale"])
    source_files = _locale_content_files(root, source_locale)
    specs = _locale_specs(root)
    for locale in locales:
        if locale == source_locale:
            continue
        path = root / "provenance" / f"{locale}.json"
        required = specs.get(locale, {}).get("ship") or specs.get(locale, {}).get("status") == "stable"
        if not path.is_file():
            if required:
                errors.append(f"provenance/{locale}.json: stable/shipped locale requires "
                              f"{source_locale}-based provenance")
            continue
        payload = load_json(path)
        if normalize_locale(payload.get("sourceLocale", "")) != source_locale:
            errors.append(f"provenance/{locale}.json: sourceLocale must be {source_locale!r}")
        if normalize_locale(payload.get("targetLocale", "")) != locale:
            errors.append(f"provenance/{locale}.json: targetLocale must be {locale!r}")
        rows = payload.get("files", [])
        by_path = {item.get("path", ""): item for item in rows}
        if len(by_path) != len(rows):
            errors.append(f"provenance/{locale}.json: duplicate content path")
        target_files = _locale_content_files(root, locale)
        expected = set(source_files)
        if set(target_files) != expected:
            missing = sorted(expected - set(target_files))
            extra = sorted(set(target_files) - expected)
            if missing:
                errors.append(f"provenance/{locale}.json: missing target content file {missing[0]}")
            if extra:
                errors.append(f"provenance/{locale}.json: unexpected target content file {extra[0]}")
        if set(by_path) != expected:
            missing = sorted(expected - set(by_path))
            extra = sorted(set(by_path) - expected)
            if missing:
                errors.append(f"provenance/{locale}.json: missing provenance row {missing[0]}")
            if extra:
                errors.append(f"provenance/{locale}.json: unexpected provenance row {extra[0]}")
        for relative in sorted(expected & set(target_files) & set(by_path)):
            row = by_path[relative]
            source_path = source_files[relative]
            target_path = target_files[relative]
            if row.get("sourceHash") != _content_hash(source_path):
                errors.append(f"provenance/{locale}.json {relative}: stale Chinese source hash")
            if row.get("targetHash") != _content_hash(target_path):
                errors.append(f"provenance/{locale}.json {relative}: target hash does not match translation")
            if required and row.get("reviewStatus") != "reviewed":
                errors.append(f"provenance/{locale}.json {relative}: stable/shipped translation "
                              "must be reviewed")


def authoring_report(root: Path) -> tuple[list[str], list[str]]:
    errors = validate_schema_files(root); warnings: list[str] = []
    try:
        _validate_manifest(root, errors)
        locales = sorted(_locale_specs(root))
        _validate_ui(root, locales, errors); _validate_prompts(root, locales, errors)
        _validate_dialogue(root, locales, errors); _validate_chronicle(root, locales, errors)
        _validate_links(root, locales, warnings)
        _validate_provenance(root, locales, errors)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"authoring: cannot complete semantic validation ({error})")
    return sorted(set(errors)), sorted(set(warnings))


def _eligible_maps(root: Path):
    specs = _locale_specs(root); locales = sorted(specs)
    ui_contracts = {item["key"]: item for item in load_ui_contracts(root)}
    prompt_contracts = {item["promptId"]: item for item in load_prompt_contracts(root)}
    dialogue_contracts = {item["storyletId"]: item for item in load_dialogue_contracts(root)}
    chronicle_contracts = {item["poolId"]: item for item in load_chronicle_contracts(root)}
    topic_coverage = load_topic_coverage(root)
    ui = {}; prompts = {}; dialogue = {}; chronicle = {}
    for locale in locales:
        ui[locale] = {item["key"]: item for item in load_ui_locale(root, locale) if item.get("key") in ui_contracts and _eligible(item, ui_contracts[item["key"]])}
        prompts[locale] = {item["promptId"]: item for item in load_prompt_locale(root, locale) if item.get("promptId") in prompt_contracts and _eligible(item, prompt_contracts[item["promptId"]])}
        dgroups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in load_dialogue_locale(root, locale):
            contract = dialogue_contracts.get(item.get("storyletId"))
            topics = item.get("selection", {}).get("resolvedTopics", [])
            topic_is_ready = not topics or (len(topics) == 1 and
                topics[0] in topic_coverage.get(locale, set()))
            if contract and _eligible(item, contract) and topic_is_ready:
                dgroups[item["storyletId"]].append(item)
        dialogue[locale] = dgroups
        cgroups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in load_chronicle_locale(root, locale):
            contract = chronicle_contracts.get(item.get("poolId"))
            if contract and _eligible(item, contract): cgroups[item["poolId"]].append(item)
        chronicle[locale] = cgroups
    return specs, ui_contracts, prompt_contracts, dialogue_contracts, chronicle_contracts, ui, prompts, dialogue, chronicle


def _resolve_unit(unit: str, maps: dict[str, Any], chain: list[str]):
    for locale in chain:
        value = maps.get(locale, {}).get(unit)
        if value: return locale, value
    return "", None


def _source_kind(requested: str, resolved: str) -> str:
    if not resolved: return "unavailable"
    if resolved == requested: return "exact"
    if "-" in requested and resolved == requested.split("-", 1)[0]: return "base"
    return "fallback"


def _coverage(units: Iterable[str], requested: str, maps: dict[str, Any], chain: list[str]) -> tuple[dict[str, int], dict[str, str]]:
    counts = {"exact": 0, "base": 0, "fallback": 0, "unavailable": 0}; resolution = {}
    for unit in sorted(units):
        resolved, _ = _resolve_unit(unit, maps, chain); kind = _source_kind(requested, resolved)
        counts[kind] += 1; resolution[unit] = resolved
    return counts, resolution


def release_quality_errors(root: Path) -> list[str]:
    manifest = load_manifest(root); shipped = shipped_locales(root)
    specs, ui_c, prompt_c, dialogue_c, chronicle_c, ui, prompts, dialogue, chronicle = _eligible_maps(root)
    errors: list[str] = []
    for requested in shipped:
        chain = fallback_chain(requested, shipped, manifest["fallbackLocale"], manifest["defaultLocale"])
        status = specs[requested]["status"]
        for family, contracts, maps, id_name in (("ui", ui_c, ui, "key"), ("prompts", prompt_c, prompts, "promptId")):
            if status != "stable": continue
            exact = sum(_resolve_unit(unit, maps, chain)[0] == requested for unit in contracts)
            if exact != len(contracts):
                errors.append(f"release.{requested}.{family}: exact native coverage "
                              f"{exact}/{len(contracts)} is below 100%")
        if status == "stable":
            for storylet_id, contract in dialogue_c.items():
                resolved, candidates = _resolve_unit(storylet_id, dialogue, chain)
                native = resolved == requested
                base_count = sum(".base." in item["candidateId"] for item in (candidates or []))
                if not native or base_count < contract["minimumBaseCandidates"]:
                    errors.append(f"release.{requested}.dialogue.{storylet_id}: requires exact native "
                                  f"pool with {contract['minimumBaseCandidates']} base candidates "
                                  f"(got {base_count} from {resolved or 'unavailable'})")
            for pool_id, contract in chronicle_c.items():
                resolved, templates = _resolve_unit(pool_id, chronicle, chain)
                native = resolved == requested
                active = sum(not item["deprecated"] for item in (templates or []))
                if not native or active < contract["minimumStable"]:
                    errors.append(f"release.{requested}.chronicle.{pool_id}: requires exact native "
                                  f"pool with {contract['minimumStable']} templates "
                                  f"(got {active} from {resolved or 'unavailable'})")
    default = manifest["defaultLocale"]
    for unit, contract in {**ui_c, **prompt_c}.items():
        if contract["importance"] in {"critical", "standard"}:
            maps = ui if unit in ui_c else prompts
            if unit not in maps.get(default, {}): errors.append(f"release.{default}: default locale must directly provide {unit}")
    return sorted(set(errors))


def validate_catalog(root: Path) -> list[str]:
    errors, _ = authoring_report(root)
    # Provenance/schema diagnostics and release coverage answer different questions. Report both
    # whenever the catalog remains readable so a stale hash cannot hide the actual release
    # regression that caused it. Truly malformed input is already explained by authoring_report.
    try:
        errors.extend(release_quality_errors(root))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return sorted(set(errors))


def escape_cs(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")


def unescape_cs(text: str) -> str:
    return bytes(text, "utf-8").decode("unicode_escape")


def escape_po(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _ui_trie(entries: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for item in entries:
        node = root
        for part in item["key"].split(".")[1:]: node = node.setdefault(part, {})
        node["__text__"] = item["text"]
    return root


def render_strings_cs(entries: list[dict[str, Any]]) -> str:
    lines = ["// <auto-generated> oni-ai-social-i18n export. Do not edit. </auto-generated>",
             "namespace ONIAiSocial", "{", "    public class STRINGS", "    {"]
    def emit(node: dict[str, Any], indent: int) -> None:
        for key in sorted(item for item in node if item != "__text__"):
            child = node[key]
            if set(child) == {"__text__"}:
                lines.append(" " * indent +
                             f'public static LocString {key} = "{escape_cs(child["__text__"])}";')
                continue
            lines.append(" " * indent + f"public class {key}")
            lines.append(" " * indent + "{")
            emit(child, indent + 4)
            lines.append(" " * indent + "}")
    emit(_ui_trie(entries), 8)
    lines.extend(["    }", "}", ""])
    return "\n".join(lines)


def render_po(entries: list[dict[str, Any]], locale: str) -> str:
    lines = ['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"', '"Language: ' + escape_po(locale) + '\\n"', ""]
    for item in entries:
        lines.append(f"#. resolved-locale: {item['resolvedLocale']}")
        if item["resolvedLocale"] != locale: lines.append(f"#. fallback for {locale}")
        # Klei registers the generated ONIAiSocial.STRINGS tree with the assembly namespace.
        # Authoring/runtime JSON keeps language-neutral STRINGS.* keys; only the PO adapter owns
        # the engine-specific prefix.
        context = item["key"] if item["key"].startswith("ONIAiSocial.") else "ONIAiSocial." + item["key"]
        lines += [f"#. {item['key']}", f'msgctxt "{escape_po(context)}"', f'msgid "{escape_po(item["sourceText"])}"', f'msgstr "{escape_po(item["text"])}"', ""]
    return "\n".join(lines)


def parse_locstring_cs(path: Path) -> list[tuple[str, str]]:
    stack: list[str] = []; result: list[tuple[str, str]] = []
    class_re = re.compile(r"^\s*public (?:static )?class ([A-Za-z_][A-Za-z0-9_]*)")
    value_re = re.compile(r'^\s*public static LocString ([A-Za-z_][A-Za-z0-9_]*) = "((?:\\.|[^"\\])*)";')
    pending = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = class_re.match(line)
        if match: pending = match.group(1); continue
        if pending and line.strip() == "{": stack.append(pending); pending = None; continue
        match = value_re.match(line)
        if match:
            path_parts = [part for part in stack if part != "STRINGS"] + [match.group(1)]
            result.append(("STRINGS." + ".".join(path_parts),
                           json.loads('"' + match.group(2) + '"')))
        if line.strip() == "}" and stack: stack.pop()
    return result


def parse_po_catalog(path: Path) -> tuple[dict[str, str], list[str]]:
    result: dict[str, str] = {}; errors: list[str] = []; context = None; msgstr = None
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if line.startswith("msgctxt "):
            try: context = json.loads(line[8:])
            except ValueError: errors.append("invalid msgctxt")
        elif line.startswith("msgstr "):
            try: msgstr = json.loads(line[7:])
            except ValueError: errors.append("invalid msgstr")
        elif line == "" and context is not None:
            key = context.removeprefix("ONIAiSocial.")
            if key in result: errors.append(f"duplicate msgctxt {context}")
            result[key] = msgstr or ""; context = None; msgstr = None
    return result, errors


def _dialogue_diversity_key(item: dict[str, Any]) -> str:
    """Return a stable semantic key while preserving an explicit authoring override.

    personality-authored candidates use
    storylet.<scene>.personality.<voice>.<content-number>.  The voice is a rendition,
    not new content, so all six voices for the same content-number share one key.
    Other authored candidates default to their exact id until authors deliberately group them.
    """
    explicit = item.get("diversityKey")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    candidate_id = item["candidateId"]
    parts = candidate_id.split(".")
    if len(parts) >= 5 and parts[-3] == "personality":
        return ".".join(parts[:-2] + [parts[-1]])
    return candidate_id


def _resolved_catalogs(root: Path):
    manifest = load_manifest(root); shipped = shipped_locales(root)
    specs, ui_c, prompt_c, dialogue_c, chronicle_c, ui, prompts, dialogue, chronicle = _eligible_maps(root)
    topic_coverage = load_topic_coverage(root)
    result = {}
    for requested in shipped:
        chain = fallback_chain(requested, shipped, manifest["fallbackLocale"], manifest["defaultLocale"])
        ui_entries = []
        for key, contract in sorted(ui_c.items()):
            resolved, item = _resolve_unit(key, ui, chain)
            if item is None: continue
            ui_entries.append({"key": key, "text": item["text"], "resolvedLocale": resolved,
                               "requiredSlots": [str(arg["token"]) for arg in contract["arguments"]],
                               "richText": contract["richText"], "contractRevision": contract["contractRevision"]})
        prompt_entries = []
        for prompt_id, contract in sorted(prompt_c.items()):
            resolved, item = _resolve_unit(prompt_id, prompts, chain)
            if item is None: continue
            prompt_entries.append({"promptId": prompt_id, "text": item["text"], "resolvedLocale": resolved,
                                   "requiredSlots": contract["requiredSlots"], "contractRevision": contract["contractRevision"]})
        storylets = {}
        for storylet_id, contract in sorted(dialogue_c.items()):
            resolved, items = _resolve_unit(storylet_id, dialogue, chain)
            if items is None: continue
            frozen_candidates = []
            for item in items:
                # Review state and per-source revision are authoring concerns. The frozen
                # pool already carries its validated contract revision, and runtime DTOs do
                # not consume either field; omitting them keeps materialized matrices bounded.
                frozen = {key: value for key, value in item.items()
                          if key not in {"status", "contractRevision"}}
                frozen["diversityKey"] = _dialogue_diversity_key(item)
                frozen_candidates.append(frozen)
            storylets[storylet_id] = {"resolvedLocale": resolved, "contractRevision": contract["contractRevision"],
                                      "candidates": sorted(frozen_candidates, key=lambda item: (item["ordinal"], item["candidateId"]))}
        pools = {}
        for pool_id, contract in sorted(chronicle_c.items()):
            resolved, items = _resolve_unit(pool_id, chronicle, chain)
            if items is None: continue
            pools[pool_id] = {"resolvedLocale": resolved, "family": contract["family"], "angle": contract["angle"],
                              "participantMode": contract["participantMode"], "contractRevision": contract["contractRevision"],
                              "templates": sorted(items, key=lambda item: (item["ordinal"], item["templateId"]))}
        coverage = {}
        resolutions = {}
        for name, units, maps in (("ui", ui_c, ui), ("prompts", prompt_c, prompts), ("dialogue", dialogue_c, dialogue), ("chronicle", chronicle_c, chronicle)):
            coverage[name], resolutions[name] = _coverage(units, requested, maps, chain)
        result[requested] = {"chain": chain, "ui": ui_entries, "prompts": prompt_entries, "storylets": storylets,
                             "readyTopics": sorted(topic_coverage.get(requested, set())),
                             "pools": pools, "coverage": coverage, "resolutions": resolutions}
    return manifest, specs, result


def export_dist(root: Path) -> dict[str, bytes]:
    manifest, specs, resolved = _resolved_catalogs(root); files: dict[str, bytes] = {}
    family_hashes: dict[str, dict[str, str]] = {}
    default_ui = []
    for locale, value in sorted(resolved.items()):
        ui_payload = {"schemaVersion": 2, "requestedLocale": locale, "fallbackChain": value["chain"], "entries": value["ui"]}
        prompt_payload = {"schemaVersion": 2, "requestedLocale": locale, "fallbackChain": value["chain"], "entries": value["prompts"]}
        dialogue_payload = {"schemaVersion": 2, "requestedLocale": locale, "fallbackChain": value["chain"],
                            "readyTopics": value["readyTopics"], "storylets": value["storylets"]}
        chronicle_payload = {"schemaVersion": 2, "requestedLocale": locale, "fallbackChain": value["chain"], "pools": value["pools"]}
        family_text = {"ui": runtime_dumps(ui_payload),
                       "prompts": runtime_dumps(prompt_payload),
                       "dialogue": runtime_dumps(dialogue_payload),
                       "chronicle": runtime_dumps(chronicle_payload)}
        family_hashes[locale] = {name: _sha(text) for name, text in family_text.items()}
        for name, text in family_text.items(): files[f"{name}/{locale}.json"] = text.encode()
        if locale == manifest["defaultLocale"]: default_ui = value["ui"]
    default_sources = {item["key"]: item["text"] for item in default_ui}
    files["generated/STRINGS.g.cs"] = render_strings_cs(default_ui).encode()
    for locale, value in sorted(resolved.items()):
        po_entries = [{**item, "sourceText": default_sources[item["key"]]} for item in value["ui"]]
        files[f"translations/{locale}.po"] = render_po(po_entries, locale).encode()
    pot_entries = [{**item, "sourceText": item["text"]} for item in default_ui]
    files["translations/strings_template.pot"] = render_po(pot_entries, manifest["defaultLocale"]).encode()
    compatibility = load_json(root / "contracts" / "compatibility" / "legacy-chronicle-index.json")
    files["compatibility/legacy-chronicle.json"] = runtime_dumps(compatibility).encode()
    locale_manifests = []
    for locale, value in sorted(resolved.items()):
        snapshot_material = {"requestedLocale": locale, "fallbackChain": value["chain"], "resolutions": value["resolutions"],
                             "ui": value["ui"], "prompts": value["prompts"], "dialogue": value["storylets"], "chronicle": value["pools"]}
        locale_manifests.append({"id": locale, "status": specs[locale]["status"], "coverage": value["coverage"],
                                 "resolutions": value["resolutions"], "familyHashes": family_hashes[locale],
                                 "snapshotHash": _sha(canonical_json(snapshot_material))})
    dist_manifest = {"schemaVersion": 2, "contentVersion": manifest["contentVersion"], "defaultLocale": manifest["defaultLocale"],
                     "fallbackLocale": manifest["fallbackLocale"], "locales": locale_manifests}
    dist_manifest["topicCoverage"] = {locale: value["readyTopics"]
                                      for locale, value in sorted(resolved.items())}
    dist_manifest["snapshotHash"] = _sha(canonical_json(dist_manifest))
    files["manifest.json"] = runtime_dumps(dist_manifest).encode()
    return dict(sorted(files.items()))


def write_dist(root: Path) -> list[Path]:
    files = export_dist(root); dist = root / "dist"; expected = set(files)
    if dist.is_dir():
        for path in sorted((item for item in dist.rglob("*") if item.is_file()), reverse=True):
            if path.relative_to(dist).as_posix() not in expected: path.unlink()
    written = []
    for relative, data in files.items():
        path = dist / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); written.append(path)
    return written
