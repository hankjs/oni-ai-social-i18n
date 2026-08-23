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
            payload["pools"][0]["templates"][0]["description"] += " changed"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(
                any("stale chronicle template chronicle.chat.base.001" in error
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
            path = root / "catalog" / "chronicle" / "routine.json"
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


if __name__ == "__main__":
    unittest.main()
