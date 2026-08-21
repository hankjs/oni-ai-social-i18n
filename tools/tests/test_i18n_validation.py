#!/usr/bin/env python3
"""Negative validation contracts for the public i18n content boundary."""

from __future__ import annotations

import json
import shutil
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


if __name__ == "__main__":
    unittest.main()
