from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from modules import prompt_catalog
from modules.prompt_catalog import TagRecord, WildcardEntry, WildcardRecord
from nodes.WildcardProcessor import WildcardProcessor


class PromptCatalogExpansionTests(unittest.TestCase):
    def test_expands_exact_wildcard_reference_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "appearance/hair/color.txt", "red hair\nblue hair\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir):
                result, diagnostics = prompt_catalog.expand_wildcards("1girl, __appearance/hair/color__", seed=1)

        self.assertTrue(result.startswith("1girl, "))
        self.assertIn(result.removeprefix("1girl, "), {"red hair", "blue hair"})
        self.assertEqual(diagnostics, [])

    def test_missing_wildcard_inserts_visible_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir):
            result, diagnostics = prompt_catalog.expand_wildcards("__missing/path__", seed=1)

        self.assertEqual(result, "[missing wildcard: missing/path]")
        self.assertEqual(diagnostics, ["Missing wildcard: missing/path"])

    def test_nested_variant_and_wildcard_expansion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "color.txt", "red\nblue\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir):
                result, diagnostics = prompt_catalog.expand_wildcards("{__color__ {eyes|hair}|green}", seed=4)

        self.assertEqual(diagnostics, [])
        self.assertIn(result, {"red eyes", "red hair", "blue eyes", "blue hair", "green"})

    def test_recursive_glob_matches_descendants_but_single_glob_does_not(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "scene/day.txt", "day\n")
            self._write(temp_dir, "scene/night/dark.txt", "night\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir):
                single_level, _ = prompt_catalog.expand_wildcards("__scene/*__", seed=1)
                recursive, _ = prompt_catalog.expand_wildcards("__scene/**__", seed=1)

        self.assertEqual(single_level, "day")
        self.assertIn(recursive, {"day", "night"})

    def test_cycle_inserts_visible_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "a.txt", "__b__\n")
            self._write(temp_dir, "b.txt", "__a__\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir):
                result, diagnostics = prompt_catalog.expand_wildcards("__a__", seed=1)

        self.assertEqual(result, "[cyclic wildcard: a]")
        self.assertEqual(diagnostics, ["Cyclic wildcard reference: a -> b -> a"])

    def _write(self, root: str, rel_path: str, content: str) -> None:
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


class WildcardProcessorNodeTests(unittest.TestCase):
    def test_node_uses_preview_text_when_frozen(self):
        result = WildcardProcessor().process("{red|blue}", "frozen output", True, 1)

        self.assertEqual(result, ("frozen output",))

    def test_node_generates_when_not_frozen(self):
        result = WildcardProcessor().process("{red|blue}", "previous preview", False, 1)

        self.assertEqual(result, ("red",))


class PromptCatalogSearchTests(unittest.TestCase):
    def test_search_ranks_exact_and_prefix_tags(self):
        tags = [
            TagRecord(label="blue eyes", normalized="blue_eyes", category="appearance_anatomy", rank=10),
            TagRecord(label="eyeshadow", normalized="eyeshadow", category="expressions", rank=0),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog(
                "blue eyes",
                types={"tag"},
                category="appearance_anatomy",
            )["results"]

        self.assertEqual(results[0]["label"], "blue eyes")
        self.assertEqual(results[0]["insertText"], "blue eyes")

    def test_get_wildcard_detail_returns_entries(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            entries=(WildcardEntry("red hair", 1.0, 1), WildcardEntry("blue hair", 2.0, 2)),
            metadata={},
        )
        with patch.object(prompt_catalog, "wildcard_map", return_value=({wildcard.id: wildcard}, [])):
            detail = prompt_catalog.get_wildcard_detail("__appearance/hair/color__")

        self.assertEqual(detail["insertText"], "__appearance/hair/color__")
        self.assertEqual(detail["entries"][1]["text"], "blue hair")
        self.assertEqual(detail["entries"][1]["weight"], 2.0)

    def test_list_wildcards_returns_nested_tree(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            entries=(WildcardEntry("red hair", 1.0, 1), WildcardEntry("blue hair", 1.0, 2)),
            metadata={},
        )
        with patch.object(prompt_catalog, "scan_wildcards", return_value=([wildcard], [])):
            tree = prompt_catalog.list_wildcards()["tree"]

        appearance = tree["children"][0]
        hair = appearance["children"][0]
        color = hair["children"][0]
        self.assertEqual(appearance["label"], "appearance")
        self.assertEqual(hair["label"], "hair")
        self.assertEqual(color["insertText"], "__appearance/hair/color__")
        self.assertEqual(color["entryCount"], 2)

    def test_search_preserves_prompt_helper_priority_classes(self):
        tags = [
            TagRecord(label="hatsune miku", normalized="hatsune_miku", category="characters", rank=0),
            TagRecord(label="miku symphony", normalized="miku_symphony", category="copyrights", rank=1),
            TagRecord(label="miku pose", normalized="miku_pose", category="actions_poses", rank=2),
            TagRecord(label="miku costume", normalized="miku_costume", category="themes_roles", rank=3),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog(
                "miku",
                types={"tag"},
                category="themes_roles",
            )["results"]

        priority_by_label = {result["label"]: result["priorityClass"] for result in results}
        self.assertEqual(priority_by_label["hatsune miku"], "character-priority-match")
        self.assertEqual(priority_by_label["miku symphony"], "copyright-priority-match")
        self.assertEqual(priority_by_label["miku costume"], "category-priority-match")
        self.assertIsNone(priority_by_label["miku pose"])

    def test_wildcard_context_ranks_wildcards_before_tags(self):
        tags = [TagRecord(label="hair color", normalized="hair_color", category="appearance_anatomy", rank=0)]
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            entries=(WildcardEntry("red hair", 1.0, 1),),
            metadata={},
        )
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([wildcard], [])
        ):
            results = prompt_catalog.search_catalog(
                "hair color",
                context="wildcard",
                types={"tag", "wildcard"},
            )["results"]

        self.assertEqual(results[0]["type"], "wildcard")
        self.assertEqual(results[0]["insertText"], "__appearance/hair/color__")

    def test_wildcard_entry_search_requires_query_threshold(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            entries=(WildcardEntry("red hair", 1.0, 1),),
            metadata={},
        )
        with patch.object(prompt_catalog, "read_tag_records", return_value=[]), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([wildcard], [])
        ):
            short_results = prompt_catalog.search_catalog("r", types={"wildcard_entry"})["results"]
            long_results = prompt_catalog.search_catalog("red", types={"wildcard_entry"})["results"]

        self.assertEqual(short_results, [])
        self.assertEqual(long_results[0]["label"], "red hair")

    def test_search_strips_wildcard_delimiters_for_wildcard_queries(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            entries=(WildcardEntry("red hair", 1.0, 1),),
            metadata={},
        )
        with patch.object(prompt_catalog, "read_tag_records", return_value=[]), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([wildcard], [])
        ):
            results = prompt_catalog.search_catalog(
                "__hair/color",
                context="wildcard",
                types={"wildcard"},
            )["results"]

        self.assertEqual(results[0]["insertText"], "__appearance/hair/color__")


if __name__ == "__main__":
    unittest.main()
