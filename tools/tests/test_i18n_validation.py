#!/usr/bin/env python3
"""Negative validation contracts for the public i18n content boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from i18nlib import validate_catalog


class I18nValidationTests(unittest.TestCase):
    def copied_catalog(self, temporary: str) -> Path:
        target = Path(temporary) / "i18n"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git"))
        return target

    def test_committed_catalog_is_valid(self) -> None:
        self.assertEqual([], validate_catalog(ROOT))

    def test_chronicle_rejects_precanonical_parallel_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            source = root / "catalog" / "chronicle" / "routine.json"
            stale = root / "catalog" / "chronicle" / "v2-routine.json"
            shutil.copy2(source, stale)
            self.assertTrue(any(
                "chronicle source layout is not canonical" in error and
                "v2-routine.json" in error
                for error in validate_catalog(root)
            ))

    def test_unknown_review_status_is_rejected_by_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales" / "en" / "ui" / "social.tab.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["entries"][0]["status"] = "typo"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(any("not in" in error for error in validate_catalog(root)))

    def test_unlisted_dialogue_tail_truncation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales" / "en" / "dialogue" / "casual.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidate = next(
                item for item in payload["candidates"]
                if item["candidateId"] == "storylet.casual.crybaby.001"
            )
            candidate["turns"].pop()
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("explicit legacy exception" in error for error in validate_catalog(root))
            )

    def test_rich_markup_is_rejected_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales" / "en" / "ui" / "social.tab.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["entries"][0]["text"] = "<link=bad>Social</link>"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(any("rich-text markup" in error for error in validate_catalog(root)))

    def test_chronicle_pool_capacity_is_a_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "chronicle" / "routine.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["pools"][0]["minimumPublished"] = 25
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("below minimumPublished 25" in error for error in validate_catalog(root))
            )

    def test_chronicle_total_capacity_is_a_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            active = 0
            for path in sorted((root / "catalog" / "chronicle").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                active += sum(not template.get("deprecated", False)
                              for pool in payload["pools"]
                              for template in pool["templates"])
            remaining = active - 899
            for path in sorted((root / "catalog" / "chronicle").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                for pool in payload["pools"]:
                    pool["minimumPublished"] = 0
                    for template in pool["templates"]:
                        if remaining and not template.get("deprecated", False):
                            template["deprecated"] = True
                            remaining -= 1
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            self.assertEqual(0, remaining)
            self.assertTrue(any("outside release range 900–2200" in error
                                for error in validate_catalog(root)))

    def test_chronicle_semantic_angle_floors_are_release_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            base_active = 0
            for path in sorted((root / "catalog" / "chronicle").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("family") == "routine":
                    base_active += sum(
                        not template.get("deprecated", False)
                        for pool in payload["pools"] if pool.get("angle") == "base"
                        for template in pool["templates"])
            remaining = base_active - 119
            for path in sorted((root / "catalog" / "chronicle").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("family") != "routine":
                    continue
                for pool in payload["pools"]:
                    pool["minimumPublished"] = 0
                    if pool.get("angle") != "base":
                        continue
                    for template in pool["templates"]:
                        if remaining and not template.get("deprecated", False):
                            template["deprecated"] = True
                            remaining -= 1
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            self.assertEqual(0, remaining)
            self.assertTrue(any("high-frequency base" in error and
                                "below release floor 120" in error
                                for error in validate_catalog(root)))

    def test_chronicle_translation_must_keep_its_slot_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales" / "en" / "chronicle" / "routine.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["templates"][0]["text"] = "They traded a few words between shifts."
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("chronicle translation placeholders differ" in error
                    for error in validate_catalog(root))
            )

    def test_chronicle_source_change_makes_translation_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "chronicle" / "routine.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            pool = next(item for item in payload["pools"]
                        if item["poolId"] == "chronicle.chat.baseline")
            pool["templates"][0]["description"] += " changed"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("stale chronicle template chronicle.chat.baseline.001" in error
                    for error in validate_catalog(root))
            )

    def test_ui_argument_declaration_must_match_source_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "ui" / "social.announce.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry = next(
                item for item in payload["entries"]
                if item["key"] == "STRINGS.SOCIAL.ANNOUNCE.CONFESSION_BODY"
            )
            entry["arguments"].pop()
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("declared arguments" in error for error in validate_catalog(root))
            )

    def test_dialogue_initiator_tag_requires_a_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "dialogue" / "casual.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidate = next(
                item for item in payload["candidates"]
                if item["variant"]["kind"] == "initiatorTag"
            )
            candidate["variant"].pop("value")
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("initiatorTag variant requires" in error for error in validate_catalog(root))
            )

    def test_negative_dialogue_speaker_slot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "dialogue" / "casual.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candidates"][0]["turns"][0]["speakerSlot"] = -1
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("below minimum 0" in error for error in validate_catalog(root))
            )

    def test_persisted_chronicle_id_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = (root / "catalog" / "chronicle" / "compatibility" /
                    "legacy-pair.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            pool = next(
                item for item in payload["pools"]
                if item["poolId"] == "chronicle.chat.base"
            )
            pool["templates"] = [
                item for item in pool["templates"]
                if item["templateId"] != "chronicle.chat.base.001"
            ]
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("persisted chronicle templateId was removed" in error
                    for error in validate_catalog(root))
            )

    def test_export_check_rejects_stale_chronicle_dist_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            stale = root / "dist" / "chronicle" / "stale.json"
            stale.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(root / "tools" / "export.py"),
                 "--root", str(root), "--check"],
                cwd=str(root), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("dist extra: chronicle/stale.json", result.stderr)

    def test_chronicle_migration_must_cover_all_304_legacy_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "contracts" / "chronicle-migration.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["mappings"].pop()
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any("every LOG_STORY key exactly once" in error or
                                "array is shorter than minItems" in error
                                for error in validate_catalog(root)))

    def test_chronicle_migration_parity_is_an_approved_golden(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "chronicle" / "relationship.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            template = next(
                item for pool in payload["pools"] for item in pool["templates"]
                if item.get("legacyKey") == "STRINGS.SOCIAL.LOG_STORY.APOLOGY_1"
            )
            template["source"] += " "
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any(
                error == "migration.parity-mismatch: STRINGS.SOCIAL.LOG_STORY.APOLOGY_1"
                for error in validate_catalog(root)
            ))

    def test_active_chronicle_template_cannot_reintroduce_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "chronicle" / "routine.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            pool = next(item for item in payload["pools"]
                        if item["poolId"] == "chronicle.chat.baseline")
            pool["allowedSlots"].append("pair")
            pool["templates"][0]["source"] = "{pair}聊了几句。"
            pool["templates"][0]["requiredSlots"] = ["pair"]
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any("active chronicle template cannot use pair" in error or
                                "active chronicle pair slot survived migration" in error
                                for error in validate_catalog(root)))

    def test_active_chronicle_chinese_uses_full_width_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "chronicle" / "routine.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            pool = next(item for item in payload["pools"]
                        if item["poolId"] == "chronicle.chat.baseline")
            pool["templates"][0]["source"] += ","
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any("uses ASCII punctuation" in error
                                for error in validate_catalog(root)))

    def test_prompt_translation_must_keep_semantic_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales" / "en" / "prompts" / "social.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            prompt = next(item for item in payload["entries"]
                          if item["promptId"] == "prompt.conversation.profile")
            prompt["text"] = "A duplicant profile."
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any("prompt slots differ" in error
                                for error in validate_catalog(root)))

    def test_prompt_source_change_makes_translation_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "catalog" / "prompts" / "social.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["entries"][0]["description"] += " changed"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            self.assertTrue(any("stale prompt" in error for error in validate_catalog(root)))


if __name__ == "__main__":
    unittest.main()
