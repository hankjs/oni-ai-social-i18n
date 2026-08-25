#!/usr/bin/env python3
"""Schema-v2 authoring, quality-gate and unit-fallback contracts."""

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
from i18nlib import authoring_report, export_dist, validate_catalog


class I18nValidationTests(unittest.TestCase):
    def copied_catalog(self, temporary: str) -> Path:
        target = Path(temporary) / "i18n"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return target

    @staticmethod
    def rewrite(path: Path, edit) -> None:
        payload = json.loads(path.read_text(encoding="utf-8")); edit(payload)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_committed_catalog_is_valid(self) -> None:
        self.assertEqual([], validate_catalog(ROOT))

    def test_v1_catalog_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            (root / "catalog").mkdir(); (root / "catalog/stale.json").write_text("{}\n")
            self.assertTrue(any("v1 catalog" in error for error in validate_catalog(root)))

    def test_unknown_review_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.tab.json"
            self.rewrite(path, lambda value: value["entries"][0].update(status="typo"))
            self.assertTrue(any("not in" in error for error in validate_catalog(root)))

    def test_dialogue_turn_shapes_are_locale_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: value["candidates"][0]["turns"].pop())
            self.assertEqual([], validate_catalog(root))

    def test_dialogue_candidate_ids_are_not_cross_locale_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            def edit(value):
                item = dict(value["candidates"][-1]); item["candidateId"] = "storylet.casual.en-only.999"
                item["ordinal"] = 999
                value["candidates"].append(item)
            self.rewrite(path, edit)
            self.assertEqual([], validate_catalog(root))

    def test_chronicle_template_ids_are_not_cross_locale_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            def edit(value):
                item = dict(value["templates"][-1]); item["templateId"] = "chronicle.en-only.local.005"; item["ordinal"] = 5
                value["templates"].append(item)
            self.rewrite(path, edit)
            stability = root / "locales/en/stability/chronicle.json"
            self.rewrite(stability, lambda value: next(item for item in value["pools"]
                if item["poolId"] == "chronicle.socialize.with-place").update(
                    highestStableNumber=5))
            self.assertEqual([], validate_catalog(root))

    def test_chronicle_slots_only_follow_local_text_and_pool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            def edit(value): value["templates"][0].update(text="A quiet moment.", requiredSlots=[])
            self.rewrite(path, edit)
            self.assertEqual([], validate_catalog(root))

    def test_chronicle_rejects_local_placeholder_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            self.rewrite(path, lambda value: value["templates"][0].update(text="A quiet moment."))
            self.assertTrue(any("requiredSlots must exactly match" in error for error in validate_catalog(root)))

    def test_ui_rejects_contract_placeholder_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.announce.json"
            target = next(i for i in json.loads(path.read_text())["entries"] if "{" in i["text"])
            self.rewrite(path, lambda value: next(i for i in value["entries"] if i["key"] == target["key"]).update(text="No arguments."))
            self.assertTrue(any("placeholders differ" in error for error in validate_catalog(root)))

    def test_ui_rejects_contract_max_length(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.settings.json"
            key = "STRINGS.SOCIAL.SETTINGS.LANGUAGE_JA_PREVIEW"
            self.rewrite(path, lambda value: next(item for item in value["entries"]
                if item["key"] == key).update(text="x" * 61))
            self.assertTrue(any("exceeds maxLength 60" in error
                                for error in validate_catalog(root)))

    def test_stale_and_draft_entries_are_filtered_not_exported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.tab.json"
            key = json.loads(path.read_text())["entries"][0]["key"]
            self.rewrite(path, lambda value: value["entries"][0].update(status="draft"))
            self.assertEqual([], validate_catalog(root))
            payload = json.loads(export_dist(root)["ui/en.json"])
            self.assertEqual("zh", next(item for item in payload["entries"] if item["key"] == key)["resolvedLocale"])

    def test_stable_prompt_critical_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/prompts/social.json"
            self.rewrite(path, lambda value: value["entries"].pop())
            self.assertTrue(any("prompts.critical" in error for error in validate_catalog(root)))

    def test_stable_ui_critical_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.settings.json"
            key = "STRINGS.SOCIAL.SETTINGS.LANGUAGE_JA_PREVIEW"
            self.rewrite(path, lambda value: value.update(entries=[item
                for item in value["entries"] if item["key"] != key]))
            self.assertTrue(any("release.en.ui.critical" in error
                                for error in validate_catalog(root)))

    def test_stable_dialogue_required_pool_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: [item.update(status="draft")
                for item in value["candidates"]
                if item["storyletId"] == "Casual" and ".base." in item["candidateId"]])
            self.assertTrue(any("release.en.dialogue.Casual" in error
                                for error in validate_catalog(root)))

    def test_stable_chronicle_required_pool_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "contracts/chronicle/routine.json"
            self.rewrite(path, lambda value: next(item for item in value["pools"]
                if item["poolId"] == "chronicle.greet.baseline").update(minimumStable=9999))
            self.assertTrue(any("release.en.chronicle.chronicle.greet.baseline" in error
                                for error in validate_catalog(root)))

    def test_stability_rejects_hiding_published_content_as_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            self.rewrite(path, lambda value: next(item for item in value["templates"]
                if item["poolId"] == "chronicle.greet.baseline" and
                item["ordinal"] == 1).update(status="draft"))
            self.assertTrue(any("published ordinal was removed: 1" in error
                                for error in validate_catalog(root)))

    def test_stability_rejects_reviewed_content_above_the_high_water(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/stability/chronicle.json"
            self.rewrite(path, lambda value: next(item for item in value["pools"]
                if item["poolId"] == "chronicle.greet.baseline").update(highestStableNumber=47))
            self.assertTrue(any("reviewed ordinal 48 is above highestStableNumber 47" in error
                                for error in validate_catalog(root)))

    def test_dialogue_rejects_unknown_selection_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: value["candidates"][0]["selection"].update(tempo=[]))
            self.assertTrue(any("unknown selection dimension" in error
                                for error in validate_catalog(root)))

    def test_dialogue_selection_must_be_declared_and_enum_backed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            contract = root / "contracts/dialogue/storylets.json"
            self.rewrite(contract, lambda value: next(item for item in value["storylets"]
                if item["storyletId"] == "Casual")["selectionDimensions"].remove("voices"))
            self.assertTrue(any("voices is outside contract selectionDimensions" in error
                                for error in validate_catalog(root)))
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: value["candidates"][0]["selection"].update(
                causes=["not-a-core-cause"]))
            self.assertTrue(any("invalid causes" in error
                                for error in validate_catalog(root)))

    def test_stability_rejects_removing_a_published_ordinal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            self.rewrite(path, lambda value: value.update(templates=[item
                for item in value["templates"]
                if not (item["poolId"] == "chronicle.greet.baseline" and item["ordinal"] == 1)]))
            self.assertTrue(any("published ordinal was removed: 1" in error
                                for error in validate_catalog(root)))

    def test_preview_resolves_each_unit_and_reports_provenance(self) -> None:
        payloads = export_dist(ROOT); ui = json.loads(payloads["ui/ja.json"]); dialogue = json.loads(payloads["dialogue/ja.json"])
        language = next(item for item in ui["entries"]
                        if item["key"] == "STRINGS.SOCIAL.SETTINGS.LANGUAGE_JA_PREVIEW")
        self.assertEqual("ja", language["resolvedLocale"])
        self.assertEqual("日本語（プレビュー・未完成）", language["text"])
        self.assertEqual({"en", "ja"}, {item["resolvedLocale"] for item in ui["entries"]})
        self.assertEqual({"en"}, {item["resolvedLocale"] for item in dialogue["storylets"].values()})
        ja = next(item for item in json.loads(payloads["manifest.json"])["locales"] if item["id"] == "ja")
        self.assertEqual("preview", ja["status"])
        native_count = sum(item["resolvedLocale"] == "ja" for item in ui["entries"])
        self.assertEqual(14, native_count)
        self.assertEqual(native_count, ja["coverage"]["ui"]["exact"])
        self.assertEqual(len(ui["entries"]) - native_count,
                         ja["coverage"]["ui"]["fallback"])
        self.assertNotIn("ui/ko.json", payloads)
        self.assertNotIn("translations/ko.po", payloads)

    def test_every_registered_locale_owns_a_stability_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            (root / "locales/ja/stability/chronicle.json").unlink()
            self.assertTrue(any("stability ledger is missing" in error for error in validate_catalog(root)))

    def test_broken_provenance_link_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "links/dialogue.json"
            self.rewrite(path, lambda value: value["links"].append({"from": {"locale": "en", "kind": "dialogue", "id": "missing"}, "relation": "inspiredBy", "to": {"locale": "zh", "kind": "dialogue", "id": "also-missing"}, "targetRevision": 1}))
            errors, warnings = authoring_report(root)
            self.assertEqual([], errors); self.assertTrue(warnings); self.assertEqual([], validate_catalog(root))

    def test_export_is_byte_deterministic(self) -> None:
        self.assertEqual(export_dist(ROOT), export_dist(ROOT))

    def test_export_check_rejects_any_stale_dist_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); (root / "dist/chronicle/stale.json").write_text("{}\n")
            result = subprocess.run([sys.executable, str(root / "tools/export.py"), "--root", str(root), "--check"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(0, result.returncode); self.assertIn("dist extra", result.stderr)


if __name__ == "__main__": unittest.main()
