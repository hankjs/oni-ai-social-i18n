#!/usr/bin/env python3
"""Schema-v2 authoring, quality-gate and unit-fallback contracts."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from i18nlib import (_content_hash, authoring_report, export_dist,
                     semantic_runtime_syntax_error, validate_catalog)


class I18nValidationTests(unittest.TestCase):
    def copied_catalog(self, temporary: str) -> Path:
        target = Path(temporary) / "i18n"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return target

    @staticmethod
    def rewrite(path: Path, edit) -> None:
        payload = json.loads(path.read_text(encoding="utf-8")); edit(payload)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def refresh_target_provenance(self, root: Path, locale: str, relative: str) -> None:
        path = root / "provenance" / f"{locale}.json"
        self.rewrite(path, lambda value: next(item for item in value["files"]
            if item["path"] == relative).update(targetHash=_content_hash(
                root / "locales" / locale / relative)))

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
            self.refresh_target_provenance(root, "en", "dialogue/casual.json")
            self.assertEqual([], validate_catalog(root))

    def test_dialogue_rejects_rich_text_markup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: value["candidates"][0]["turns"][0].update(
                text="A linked <link=\"Water\">subject</link> must not reach a bubble."))
            self.assertTrue(any("rich-text markup is not allowed" in error
                                for error in validate_catalog(root)))

    def test_dialogue_candidate_ids_are_not_cross_locale_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/dialogue/casual.json"
            def edit(value):
                item = dict(value["candidates"][-1]); item["candidateId"] = "storylet.casual.en-only.999"
                item["ordinal"] = 999
                value["candidates"].append(item)
            self.rewrite(path, edit)
            self.refresh_target_provenance(root, "en", "dialogue/casual.json")
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
            self.refresh_target_provenance(root, "en", "chronicle/routine.json")
            self.assertEqual([], validate_catalog(root))

    def test_chronicle_slots_only_follow_local_text_and_pool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            def edit(value): value["templates"][0].update(text="A quiet moment.", requiredSlots=[])
            self.rewrite(path, edit)
            self.refresh_target_provenance(root, "en", "chronicle/routine.json")
            self.assertEqual([], validate_catalog(root))

    def test_chronicle_rejects_local_placeholder_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            self.rewrite(path, lambda value: value["templates"][0].update(text="A quiet moment."))
            self.assertTrue(any("requiredSlots must exactly match" in error for error in validate_catalog(root)))

    def test_runtime_placeholder_grammar_matches_the_csharp_compiler(self) -> None:
        """占位符文法的真值在 C# SemanticTemplateCompiler,不在 string.Format 的正则里。

        FORMAT_ITEM_RE 放行的这些形态会让运行时把整个 locale 的 chronicle family
        判为 damaged,进而冻结**所有语言**的 ledger 分配——校验器全绿,游戏里叙事全灭。
        """
        for good in ("{a}", "{actor}", "{a}{b}", "{actor:subject}", "{a1}", "plain text"):
            self.assertIsNone(semantic_runtime_syntax_error(good), good)
        for bad in ("{Actor}", "{_x}", "{0}", "{a,5}", "{a: subject}", "{a:sub_form}", "{{a}}"):
            self.assertIsNotNone(semantic_runtime_syntax_error(bad), bad)
        self.assertIn("unclosed", semantic_runtime_syntax_error("{a") or "")
        self.assertIn("stray", semantic_runtime_syntax_error("a}") or "")

    def test_chronicle_rejects_a_placeholder_the_runtime_cannot_compile(self) -> None:
        """整份目录必须拦住它,而不只是那个纯函数。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            original = json.loads(path.read_text())["templates"][0]
            self.rewrite(path, lambda value: value["templates"][0].update(
                text=original["text"] + " {a: subject}",
                requiredSlots=sorted(set(original.get("requiredSlots", [])) | {"a"})))
            self.assertTrue(any("not accepted by the runtime" in error
                                for error in validate_catalog(root)))

    def test_ui_rejects_contract_placeholder_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.announce.json"
            target = next(i for i in json.loads(path.read_text())["entries"] if "{" in i["text"])
            self.rewrite(path, lambda value: next(i for i in value["entries"] if i["key"] == target["key"]).update(text="No arguments."))
            self.assertTrue(any("placeholders differ" in error for error in validate_catalog(root)))

    def test_ui_rejects_contract_max_length(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.settings.json"
            key = "STRINGS.SOCIAL.SETTINGS.LANGUAGE_JA"
            self.rewrite(path, lambda value: next(item for item in value["entries"]
                if item["key"] == key).update(text="x" * 61))
            self.assertTrue(any("exceeds maxLength 60" in error
                                for error in validate_catalog(root)))

    def test_probable_repeated_word_translation_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/prompts/social.json"
            self.rewrite(path, lambda value: value["entries"][0].update(
                text="Keep the established facts, but the decoder repeats repeats repeats "
                     "inside an otherwise long player-facing sentence that needs review."))
            self.assertTrue(any("repeated-word translation artifact" in error
                                for error in validate_catalog(root)))

    def test_decomposed_unicode_translation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/prompts/social.json"
            self.rewrite(path, lambda value: value["entries"][0].update(
                text=value["entries"][0]["text"] + " a\u0301"))
            self.assertTrue(any("NFC-normalized Unicode" in error
                                for error in validate_catalog(root)))

    def test_chinese_source_change_marks_target_provenance_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/zh/ui/social.tab.json"
            self.rewrite(path, lambda value: value["entries"][0].update(
                text=value["entries"][0]["text"] + "。"))
            self.assertTrue(any("stale Chinese source hash" in error
                                for error in validate_catalog(root)))

    def test_target_edit_requires_matching_provenance_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/ui/social.tab.json"
            self.rewrite(path, lambda value: value["entries"][0].update(
                text=value["entries"][0]["text"] + " updated"))
            self.assertTrue(any("target hash does not match translation" in error
                                for error in validate_catalog(root)))

    def test_glossary_term_requires_all_six_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "glossary.json"
            self.rewrite(path, lambda value: value["terms"][0].pop("vi"))
            self.assertTrue(any("missing required property 'vi'" in error
                                for error in validate_catalog(root)))

    def test_stale_and_draft_entries_are_filtered_not_exported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.tab.json"
            key = json.loads(path.read_text())["entries"][0]["key"]
            self.rewrite(path, lambda value: value["entries"][0].update(status="draft"))
            self.assertTrue(any("release.en.ui" in error for error in validate_catalog(root)))
            payload = json.loads(export_dist(root)["ui/en.json"])
            self.assertEqual("zh", next(item for item in payload["entries"] if item["key"] == key)["resolvedLocale"])

    def test_draft_base_locale_cannot_supply_a_shipped_regional_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            manifest = root / "manifest.json"
            def edit_manifest(value):
                next(item for item in value["locales"] if item["id"] == "ko").update(
                    status="draft", ship=False)
                value["locales"].append(
                    {"id": "ko-kr", "status": "preview", "ship": True})
            self.rewrite(manifest, edit_manifest)
            source = json.loads((root / "locales/en/ui/social.tab.json").read_text())
            source["locale"] = "ko"
            source["entries"][0]["text"] = "초안 소셜"
            draft = root / "locales/ko/ui/social.tab.json"
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

            payload = json.loads(export_dist(root)["ui/ko-kr.json"])
            title = next(item for item in payload["entries"]
                         if item["key"] == "STRINGS.SOCIAL.TAB.TITLE")
            self.assertEqual("en", title["resolvedLocale"])
            self.assertEqual("Social", title["text"])

    def test_stable_prompt_critical_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/prompts/social.json"
            self.rewrite(path, lambda value: value["entries"].pop())
            self.assertTrue(any("release.en.prompts" in error for error in validate_catalog(root)))

    def test_stable_ui_critical_missing_is_a_release_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/ui/social.settings.json"
            key = "STRINGS.SOCIAL.SETTINGS.LANGUAGE_JA"
            self.rewrite(path, lambda value: value.update(entries=[item
                for item in value["entries"] if item["key"] != key]))
            self.assertTrue(any("release.en.ui" in error
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

    def test_non_ready_topic_content_is_valid_but_excluded_from_dist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/dialogue/casual.json"
            candidate_id = "storylet.casual.matrix.draft.001"
            def edit(value):
                item = dict(value["candidates"][-1])
                item.update(candidateId=candidate_id, ordinal=999,
                            diversityKey="observation")
                item["selection"] = {"resolvedTopics": ["recent.decor.appraise_positive"],
                                     "actors": [{"slot": 0,
                                                 "personalities": ["athlete"],
                                                 "moods": ["settled"]}]}
                value["candidates"].append(item)
            self.rewrite(path, edit)
            self.refresh_target_provenance(root, "en", "dialogue/casual.json")
            self.assertEqual([], validate_catalog(root), "athlete is a valid primary personality")
            payload = json.loads(export_dist(root)["dialogue/en.json"])
            ids = {item["candidateId"] for item in payload["storylets"]["Casual"]["candidates"]}
            self.assertNotIn(candidate_id, ids)

    def test_ready_topic_requires_all_65_cells_and_five_diversity_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            coverage = root / "contracts/dialogue/topic-coverage.json"
            self.rewrite(coverage, lambda value: value["locales"]["en"]["readyTopics"].append(
                "recent.food.appraise_positive"))
            errors = validate_catalog(root)
            self.assertTrue(any("hothead × settled has 0/5" in error for error in errors))
            self.assertTrue(any("athlete × overwhelmed has 0/5" in error for error in errors))

    def test_ready_topic_rejects_mandatory_listener_personality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/dialogue/casual.json"
            topic = "recent.food.appraise_positive"
            def edit(value):
                item = dict(value["candidates"][-1])
                item.update(candidateId="storylet.casual.matrix.listener.001", ordinal=999,
                            diversityKey="observation")
                item["selection"] = {"resolvedTopics": [topic], "actors": [
                    {"slot": 0, "personalities": ["hothead"], "moods": ["settled"]},
                    {"slot": 1, "personalities": ["gentle"]}]}
                value["candidates"].append(item)
            self.rewrite(path, edit)
            self.refresh_target_provenance(root, "en", "dialogue/casual.json")
            coverage = root / "contracts/dialogue/topic-coverage.json"
            self.rewrite(coverage, lambda value: value["locales"]["en"]["readyTopics"].append(topic))
            self.assertTrue(any("slot 1 personality cannot be mandatory" in error
                                for error in validate_catalog(root)))

    def test_native_utterance_axis_requires_five_angles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/dialogue/topic-fallback.json"
            self.rewrite(path, lambda value: value.update(candidates=[item
                for item in value["candidates"]
                if item["candidateId"] !=
                "native-utterance.base.query.angle-5"]))
            self.refresh_target_provenance(root, "en", "dialogue/topic-fallback.json")
            errors = validate_catalog(root)
            self.assertTrue(any("query.unspecified: native utterance templates have 4/5"
                                in error for error in errors))

    def test_selection_metadata_must_match_when_candidate_id_is_shared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            path = root / "locales/en/dialogue/casual.json"
            self.rewrite(path, lambda value: value["candidates"][0]["selection"].update(
                moods=["settled"]))
            self.refresh_target_provenance(root, "en", "dialogue/casual.json")
            self.assertTrue(any("selection metadata differs across locales" in error
                                for error in validate_catalog(root)))

    def test_stability_rejects_removing_a_published_ordinal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary); path = root / "locales/en/chronicle/routine.json"
            self.rewrite(path, lambda value: value.update(templates=[item
                for item in value["templates"]
                if not (item["poolId"] == "chronicle.greet.baseline" and item["ordinal"] == 1)]))
            self.assertTrue(any("published ordinal was removed: 1" in error
                                for error in validate_catalog(root)))

    def test_every_shipped_locale_resolves_every_family_exactly(self) -> None:
        payloads = export_dist(ROOT)
        manifest = json.loads(payloads["manifest.json"])
        self.assertEqual({"zh", "en", "ko", "ru", "ja", "vi"},
                         {item["id"] for item in manifest["locales"]})
        for item in manifest["locales"]:
            locale = item["id"]
            self.assertEqual("stable", item["status"])
            for family in ("ui", "prompts", "dialogue", "chronicle"):
                self.assertEqual(0, item["coverage"][family]["fallback"],
                                 f"{locale}/{family}")
                self.assertTrue(item["coverage"][family]["exact"] > 0)
                self.assertEqual({locale}, set(item["resolutions"][family].values()))
            self.assertIn(f"translations/{locale}.po", payloads)
        encoded = [value if isinstance(value, bytes) else value.encode("utf-8")
                   for value in payloads.values()]
        # Six fully materialized 13×5×5 Topic matrices intentionally trade raw
        # repetition for a simple, auditable runtime contract. They remain below
        # 20 MiB as a set and below 1.5 MiB over normal HTTP compression.
        self.assertLessEqual(sum(map(len, encoded)), 20 * 1024 * 1024,
                             "the complete six-language dist exceeds 20 MiB")
        self.assertLessEqual(sum(len(gzip.compress(value, compresslevel=9, mtime=0))
                                 for value in encoded),
                             int(1.5 * 1024 * 1024),
                             "the complete six-language dist exceeds 1.5 MiB compressed")

    def test_every_registered_locale_owns_a_stability_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_catalog(temporary)
            (root / "locales/en/stability/chronicle.json").unlink()
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
