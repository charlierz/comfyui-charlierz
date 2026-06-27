from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from modules import prompt_catalog
from modules.prompt_catalog import TagRecord, WildcardRecord, WildcardTag
from nodes.WildcardProcessor import WildcardProcessor


class PromptCatalogExpansionTests(unittest.TestCase):
    def setUp(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def test_expands_exact_wildcard_reference_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_tag_pools_dir:
            self._write(temp_dir, "appearance/hair/color.txt", "red hair\nblue hair\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", empty_tag_pools_dir
            ):
                result, diagnostics = prompt_catalog.expand_wildcards("1girl, __appearance/hair/color__", seed=1)

        self.assertTrue(result.startswith("1girl, "))
        self.assertIn(result.removeprefix("1girl, "), {"red hair", "blue hair"})
        self.assertEqual(diagnostics, [])

    def test_wildcard_scan_is_reused_across_catalog_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_tag_pools_dir:
            self._write(temp_dir, "appearance/hair/color.txt", "red hair\nblue hair\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", empty_tag_pools_dir
            ), patch.object(
                prompt_catalog, "_read_wildcard_tags", wraps=prompt_catalog._read_wildcard_tags
            ) as read_wildcard_tags:
                prompt_catalog.list_wildcards()
                prompt_catalog.get_wildcard_detail("appearance/hair/color")
                prompt_catalog.expand_wildcards("__appearance/hair/color__", seed=1)

        self.assertEqual(read_wildcard_tags.call_count, 1)

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
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_tag_pools_dir:
            self._write(temp_dir, "scene/day.txt", "day\n")
            self._write(temp_dir, "scene/night/dark.txt", "night\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", temp_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", empty_tag_pools_dir
            ):
                single_level, _ = prompt_catalog.expand_wildcards("__scene/*__", seed=1)
                recursive, _ = prompt_catalog.expand_wildcards("__scene/**__", seed=1)

        self.assertEqual(single_level, "day")
        self.assertIn(recursive, {"day", "night"})

    def test_expands_tag_pool_virtual_wildcard(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_wildcards_dir:
            self._write(temp_dir, "appearance/hair/color.tsv", "tag\tcount\nred hair\t10\nblue hair\t1\n")
            with patch.object(prompt_catalog, "TAG_POOLS_DIR", temp_dir), patch.object(
                prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir
            ):
                result, diagnostics = prompt_catalog.expand_wildcards("__appearance/hair/color__", seed=1)

        self.assertIn(result, {"red hair", "blue hair"})
        self.assertEqual(diagnostics, [])

    def test_score_quality_tags_preserve_underscores(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_wildcards_dir:
            self._write(temp_dir, "style/quality.tsv", "tag\tcount\nscore_9\t\nscore_8_up\t\n")
            with patch.object(prompt_catalog, "TAG_POOLS_DIR", temp_dir), patch.object(
                prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir
            ):
                result, diagnostics = prompt_catalog.expand_wildcards("__style/quality__", seed=1)
                tags = {record.label for record in prompt_catalog.read_tag_records()}

        self.assertIn(result, {"score_9", "score_8_up"})
        self.assertIn("score_9", tags)
        self.assertIn("score_8_up", tags)
        self.assertEqual(diagnostics, [])

    def test_expands_character_entity_wildcard_with_primary_franchise(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_wildcards_dir = os.path.join(temp_dir, "wildcards")
            empty_tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            os.makedirs(empty_wildcards_dir)
            os.makedirs(empty_tag_pools_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nhatsune miku\t100\tvocaloid, project voltage\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nvocaloid\t1000\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", empty_tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ):
                character_result, character_diagnostics = prompt_catalog.expand_wildcards("__characters__", seed=1)
                franchise_result, franchise_diagnostics = prompt_catalog.expand_wildcards("__franchises__", seed=1)

        self.assertEqual(character_result, "vocaloid, hatsune miku")
        self.assertEqual(character_diagnostics, [])
        self.assertEqual(franchise_result, "vocaloid")
        self.assertEqual(franchise_diagnostics, [])

    def test_character_related_wildcards_use_selected_character(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wildcards_dir = os.path.join(temp_dir, "wildcards")
            tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            relationships_path = os.path.join(temp_dir, "character_tags.tsv")
            os.makedirs(wildcards_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nhatsune miku\t100\tvocaloid\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nvocaloid\t1000\n")
            self._write(temp_dir, "character_tags.tsv", "tag\trelated\nhatsune miku\tlong hair, skirt, blue eyes, shirt, solo\n")
            self._write(tag_pools_dir, "appearance/hair.tsv", "tag\tcount\nlong hair\t1\nblue eyes\t1\n")
            self._write(tag_pools_dir, "clothes/tops.tsv", "tag\tcount\nshirt\t1\n")
            self._write(tag_pools_dir, "clothes/bottoms.tsv", "tag\tcount\nskirt\t1\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ), patch.object(prompt_catalog, "CHARACTER_TAGS_FILE", relationships_path):
                result, diagnostics = prompt_catalog.expand_wildcards(
                    "__characters__\nappearance: __character_appearance__\nclothes: __character_clothes__",
                    seed=1,
                )

        self.assertEqual(diagnostics, [])
        self.assertIn("vocaloid, hatsune miku", result)
        self.assertIn("appearance: long hair, blue eyes", result)
        self.assertIn("clothes: skirt, shirt", result)

    def test_character_related_wildcards_use_relationship_order_not_weight_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wildcards_dir = os.path.join(temp_dir, "wildcards")
            tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            relationships_path = os.path.join(temp_dir, "character_tags.tsv")
            os.makedirs(wildcards_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nhatsune miku\t100\tvocaloid\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nvocaloid\t1000\n")
            self._write(temp_dir, "character_tags.tsv", "tag\trelated\nhatsune miku\tblue eyes, long hair\n")
            self._write(tag_pools_dir, "appearance/hair.tsv", "tag\tcount\nlong hair\t100\nblue eyes\t3\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ), patch.object(prompt_catalog, "CHARACTER_TAGS_FILE", relationships_path):
                result, diagnostics = prompt_catalog.expand_wildcards(
                    "__characters__\n__character_appearance__",
                    seed=1,
                    weight_mode="log",
                )

        self.assertEqual(diagnostics, [])
        self.assertIn("blue eyes, long hair", result)

    def test_character_related_wildcards_use_literal_character_tag_before_special_wildcard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wildcards_dir = os.path.join(temp_dir, "wildcards")
            tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            relationships_path = os.path.join(temp_dir, "character_tags.tsv")
            os.makedirs(wildcards_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nhatsune miku\t100\tvocaloid\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nvocaloid\t1000\n")
            self._write(temp_dir, "character_tags.tsv", "tag\trelated\nhatsune miku\tlong hair, blue eyes, shirt\n")
            self._write(tag_pools_dir, "appearance/hair.tsv", "tag\tcount\nlong hair\t1\nblue eyes\t1\n")
            self._write(tag_pools_dir, "clothes/tops.tsv", "tag\tcount\nshirt\t1\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ), patch.object(prompt_catalog, "CHARACTER_TAGS_FILE", relationships_path):
                result, diagnostics = prompt_catalog.expand_wildcards(
                    "hatsune miku\nappearance: __character_appearance__\nclothes: __character_clothes__",
                    seed=1,
                )

        self.assertEqual(diagnostics, [])
        self.assertIn("appearance: long hair, blue eyes", result)
        self.assertIn("clothes: shirt", result)

    def test_character_related_wildcards_take_first_ten_matching_tags(self):
        appearance_tags = [f"appearance tag {index}" for index in range(12)]
        related_tags = [tag for pair in zip(appearance_tags, ["shirt"] * 12, strict=True) for tag in pair]

        with tempfile.TemporaryDirectory() as temp_dir:
            wildcards_dir = os.path.join(temp_dir, "wildcards")
            tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            relationships_path = os.path.join(temp_dir, "character_tags.tsv")
            os.makedirs(wildcards_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nhatsune miku\t100\tvocaloid\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nvocaloid\t1000\n")
            self._write(temp_dir, "character_tags.tsv", f"tag\trelated\nhatsune miku\t{', '.join(related_tags)}\n")
            self._write(
                tag_pools_dir,
                "appearance/test.tsv",
                "tag\tcount\n" + "".join(f"{tag}\t1\n" for tag in appearance_tags),
            )
            self._write(tag_pools_dir, "clothes/test.tsv", "tag\tcount\nshirt\t1\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ), patch.object(prompt_catalog, "CHARACTER_TAGS_FILE", relationships_path):
                result, diagnostics = prompt_catalog.expand_wildcards("__characters__\n__character_appearance__", seed=1)

        self.assertEqual(diagnostics, [])
        self.assertIn(", ".join(appearance_tags[:10]), result)
        self.assertNotIn(appearance_tags[10], result)

    def test_empty_character_related_wildcards_expand_to_blank(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wildcards_dir = os.path.join(temp_dir, "wildcards")
            tag_pools_dir = os.path.join(temp_dir, "tag_pools")
            characters_path = os.path.join(temp_dir, "characters.tsv")
            franchises_path = os.path.join(temp_dir, "franchises.tsv")
            relationships_path = os.path.join(temp_dir, "character_tags.tsv")
            os.makedirs(wildcards_dir)
            os.makedirs(tag_pools_dir)
            self._write(temp_dir, "characters.tsv", "tag\tcount\tfranchises\nayasaki hayate\t100\thayate no gotoku!\n")
            self._write(temp_dir, "franchises.tsv", "tag\tcount\nhayate no gotoku!\t1000\n")
            self._write(temp_dir, "character_tags.tsv", "tag\trelated\nayasaki hayate\tsolo, smile\n")
            with patch.object(prompt_catalog, "WILDCARDS_DIR", wildcards_dir), patch.object(
                prompt_catalog, "TAG_POOLS_DIR", tag_pools_dir
            ), patch.object(prompt_catalog, "CHARACTERS_ENTITIES_FILE", characters_path), patch.object(
                prompt_catalog, "FRANCHISES_FILE", franchises_path
            ), patch.object(prompt_catalog, "CHARACTER_TAGS_FILE", relationships_path):
                result, diagnostics = prompt_catalog.expand_wildcards(
                    "__characters__\n__character_appearance__\n__character_clothes__",
                    seed=1,
                )

        self.assertEqual(result, "hayate no gotoku!, ayasaki hayate\n\n")
        self.assertNotIn("[empty character appearance", result)
        self.assertNotIn("[empty character clothes", result)
        self.assertEqual(
            diagnostics,
            [
                "No appearance related tags found for character: ayasaki hayate",
                "No clothes related tags found for character: ayasaki hayate",
            ],
        )

    def test_globs_tag_pool_virtual_wildcards(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_wildcards_dir:
            self._write(temp_dir, "appearance/hair/color.tsv", "tag\tcount\nred hair\t1\n")
            self._write(temp_dir, "appearance/hair/length.tsv", "tag\tcount\nlong hair\t1\n")
            with patch.object(prompt_catalog, "TAG_POOLS_DIR", temp_dir), patch.object(
                prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir
            ):
                result, _ = prompt_catalog.expand_wildcards("__appearance/hair/*__", seed=1)

        self.assertIn(result, {"red hair", "long hair"})

    def test_expands_tag_pool_directory_wildcard(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_wildcards_dir:
            self._write(temp_dir, "pose/action.tsv", "tag\tcount\nrunning\t1\n")
            self._write(temp_dir, "pose/gesture.tsv", "tag\tcount\nwaving\t1\n")
            with patch.object(prompt_catalog, "TAG_POOLS_DIR", temp_dir), patch.object(
                prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir
            ):
                result, diagnostics = prompt_catalog.expand_wildcards("__pose__", seed=1)
                detail = prompt_catalog.get_wildcard_detail("pose")

        self.assertIn(result, {"running", "waving"})
        self.assertEqual(detail["tagCount"], 2)
        self.assertEqual(diagnostics, [])

    def test_expands_nested_tag_pool_directory_wildcard(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as empty_wildcards_dir:
            self._write(temp_dir, "appearance/breasts/size.tsv", "tag\tcount\nlarge breasts\t1\n")
            self._write(temp_dir, "appearance/breasts/shape.tsv", "tag\tcount\nround breasts\t1\n")
            with patch.object(prompt_catalog, "TAG_POOLS_DIR", temp_dir), patch.object(
                prompt_catalog, "WILDCARDS_DIR", empty_wildcards_dir
            ):
                result, diagnostics = prompt_catalog.expand_wildcards("__appearance/breasts__", seed=1)
                detail = prompt_catalog.get_wildcard_detail("appearance/breasts")

        self.assertIn(result, {"large breasts", "round breasts"})
        self.assertEqual(detail["id"], "appearance/breasts")
        self.assertEqual(detail["tagCount"], 2)
        self.assertEqual(diagnostics, [])

    def test_tag_pool_weight_modes_transform_counts(self):
        self.assertEqual(prompt_catalog._transform_tag_pool_weight(100.0, "count"), 100.0)
        self.assertAlmostEqual(prompt_catalog._transform_tag_pool_weight(100.0, "sqrt"), 10.0)
        self.assertAlmostEqual(prompt_catalog._transform_tag_pool_weight(100.0, "log"), 4.61512051684126)
        self.assertEqual(prompt_catalog._transform_tag_pool_weight(100.0, "random"), 1.0)

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
    def setUp(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def test_input_order_matches_process_signature_to_preserve_saved_widget_values(self):
        required = WildcardProcessor.INPUT_TYPES()["required"]

        self.assertEqual(list(required), ["wildcard_text", "preview_text", "weight_mode", "frozen", "seed"])

    def test_node_uses_preview_text_when_frozen(self):
        result = WildcardProcessor().process("{red|blue}", "frozen output", "sqrt", True, 1)

        self.assertEqual(result, ("frozen output",))

    def test_node_generates_when_not_frozen(self):
        result = WildcardProcessor().process("{red|blue}", "previous preview", "sqrt", False, 1)

        self.assertEqual(result["result"], ("red",))
        self.assertEqual(result["ui"], {"last_seed": [1], "text": (result["result"][0],)})


class PromptCatalogSearchTests(unittest.TestCase):
    def setUp(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        prompt_catalog.clear_prompt_catalog_caches()

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

    def test_get_wildcard_detail_returns_tags(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            tags=(WildcardTag("red hair", 1.0, 1), WildcardTag("blue hair", 2.0, 2)),
            metadata={},
        )
        with patch.object(prompt_catalog, "wildcard_map", return_value=({wildcard.id: wildcard}, [])):
            detail = prompt_catalog.get_wildcard_detail("__appearance/hair/color__")

        self.assertEqual(detail["insertText"], "__appearance/hair/color__")
        self.assertEqual(detail["tags"][1]["text"], "blue hair")
        self.assertEqual(detail["tags"][1]["weight"], 2.0)

    def test_list_wildcards_returns_nested_tree(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            tags=(WildcardTag("red hair", 1.0, 1), WildcardTag("blue hair", 1.0, 2)),
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
        self.assertEqual(color["tagCount"], 2)

    def test_search_prefers_prefix_tags_then_sorts_by_count(self):
        tags = [
            TagRecord(label="hair ornament", normalized="hair_ornament", category="clothing_accessories", rank=0, count=10),
            TagRecord(label="long hair", normalized="long_hair", category="appearance_anatomy", rank=1, count=1000),
            TagRecord(label="hair bow", normalized="hair_bow", category="clothing_accessories", rank=2, count=100),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog("hair", types={"tag"})["results"]

        self.assertEqual([result["label"] for result in results], ["hair bow", "hair ornament", "long hair"])

    def test_search_preserves_prompt_helper_priority_classes(self):
        tags = [
            TagRecord(label="hatsune miku", normalized="hatsune_miku", category="characters", rank=0),
            TagRecord(label="miku symphony", normalized="miku_symphony", category="copyrights", rank=1),
            TagRecord(label="miku pose", normalized="miku_pose", category="pose", rank=2),
            TagRecord(label="miku costume", normalized="miku_costume", category="theme", rank=3),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog(
                "miku",
                types={"tag"},
                category="theme",
            )["results"]

        priority_by_label = {result["label"]: result["priorityClass"] for result in results}
        self.assertEqual(priority_by_label["hatsune miku"], "character-priority-match")
        self.assertEqual(priority_by_label["miku symphony"], "copyright-priority-match")
        self.assertEqual(priority_by_label["miku costume"], "category-priority-match")
        self.assertIsNone(priority_by_label["miku pose"])

    def test_search_prioritizes_matching_category_before_count(self):
        tags = [
            TagRecord(label="hair ribbon", normalized="hair_ribbon", category="clothing_accessories", rank=0, count=10),
            TagRecord(label="hair ornament", normalized="hair_ornament", category="appearance_anatomy", rank=1, count=100000),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog("hair", types={"tag"}, category="clothing_accessories")["results"]

        self.assertEqual([result["label"] for result in results], ["hair ribbon", "hair ornament"])

    def test_search_prioritizes_matching_category_before_prefix_match_quality(self):
        tags = [
            TagRecord(label="hair ornament", normalized="hair_ornament", category="appearance_anatomy", rank=0, count=100000),
            TagRecord(label="long hair", normalized="long_hair", category="clothing_accessories", rank=1, count=10),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=tags), patch.object(
            prompt_catalog, "scan_wildcards", return_value=([], [])
        ):
            results = prompt_catalog.search_catalog("hair", types={"tag"}, category="clothing_accessories")["results"]

        self.assertEqual([result["label"] for result in results], ["long hair", "hair ornament"])

    def test_wildcard_context_ranks_wildcards_before_tags(self):
        tags = [TagRecord(label="hair color", normalized="hair_color", category="appearance_anatomy", rank=0)]
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            tags=(WildcardTag("red hair", 1.0, 1),),
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

    def test_wildcard_search_prefers_early_path_segments_over_leaf_only_matches(self):
        wildcards = [
            WildcardRecord(id="clothes/accessory/hair", path="tag_pools/clothes/accessory/hair.tsv", label="hair", tags=(), metadata={}),
            WildcardRecord(id="appearance/hair/color", path="tag_pools/appearance/hair/color.tsv", label="color", tags=(), metadata={}),
            WildcardRecord(id="appearance/pussy/pubic_hair", path="tag_pools/appearance/pussy/pubic_hair.tsv", label="pubic hair", tags=(), metadata={}),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=[]), patch.object(
            prompt_catalog, "scan_wildcards", return_value=(wildcards, [])
        ):
            results = prompt_catalog.search_catalog("hair", context="wildcard", types={"wildcard"})["results"]

        self.assertEqual([result["id"] for result in results], ["appearance/hair/color", "clothes/accessory/hair", "appearance/pussy/pubic_hair"])

    def test_search_strips_wildcard_delimiters_for_wildcard_queries(self):
        wildcard = WildcardRecord(
            id="appearance/hair/color",
            path="appearance/hair/color.txt",
            label="color",
            tags=(WildcardTag("red hair", 1.0, 1),),
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

    def test_wildcard_search_does_not_match_by_category_only(self):
        wildcards = [
            WildcardRecord(
                id="pose/hands",
                path="tag_pools/pose/hands.tsv",
                label="hands",
                tags=(),
                metadata={"promptCategory": "pose"},
            ),
            WildcardRecord(
                id="pose/gesture",
                path="tag_pools/pose/gesture.tsv",
                label="gesture",
                tags=(),
                metadata={"promptCategory": "pose"},
            ),
        ]
        with patch.object(prompt_catalog, "read_tag_records", return_value=[]), patch.object(
            prompt_catalog, "scan_wildcards", return_value=(wildcards, [])
        ):
            results = prompt_catalog.search_catalog(
                "xyz",
                context="wildcard",
                category="pose",
                types={"wildcard"},
            )["results"]

        self.assertEqual(results, [])


class PromptCatalogPromptTests(unittest.TestCase):
    def setUp(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def test_lists_nested_prompt_tree_and_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "portraits/soft-lighting.txt", "1girl, __appearance/hair/color__\n")
            with patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
                tree = prompt_catalog.list_prompts()["tree"]
                detail = prompt_catalog.get_prompt_detail("portraits/soft-lighting")

        portraits = tree["children"][0]
        prompt = portraits["children"][0]
        self.assertEqual(portraits["label"], "portraits")
        self.assertEqual(prompt["id"], "portraits/soft-lighting")
        self.assertEqual(prompt["label"], "soft-lighting")
        self.assertEqual(detail["insertText"], "1girl, __appearance/hair/color__\n")

    def test_search_prompts_matches_id_and_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "portraits/soft-lighting.txt", "cinematic rim light\n")
            self._write(temp_dir, "scene/night.txt", "moonlit city\n")
            with patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
                id_results = prompt_catalog.search_prompts("soft lighting")["results"]
                text_results = prompt_catalog.search_prompts("moonlit")["results"]

        self.assertEqual(id_results[0]["id"], "portraits/soft-lighting")
        self.assertEqual(text_results[0]["id"], "scene/night")

    def test_prompt_tree_preserves_children_when_prompt_exists_at_same_path_as_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "x.txt", "parent prompt\n")
            self._write(temp_dir, "x/child.txt", "child prompt\n")
            with patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
                tree = prompt_catalog.list_prompts()["tree"]

        x = tree["children"][0]
        self.assertEqual(x["type"], "directory")
        self.assertEqual(x["id"], "x")
        self.assertEqual(x["insertText"], "parent prompt\n")
        self.assertEqual(x["children"][0]["id"], "x/child")

    def test_save_prompt_normalizes_id_trims_text_and_rejects_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            detail = prompt_catalog.save_prompt("Portraits/Soft Lighting", "\n  1girl  \n", overwrite=False)
            path = os.path.join(temp_dir, "portraits", "soft_lighting.txt")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            with self.assertRaises(ValueError):
                prompt_catalog.save_prompt("empty", "  \n", overwrite=False)

        self.assertEqual(detail["id"], "portraits/soft_lighting")
        self.assertEqual(content, "1girl\n")

    def test_save_prompt_requires_overwrite_for_existing_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            prompt_catalog.save_prompt("portrait", "first", overwrite=False)
            with self.assertRaises(FileExistsError):
                prompt_catalog.save_prompt("portrait", "second", overwrite=False)
            prompt_catalog.save_prompt("portrait", "second", overwrite=True)
            detail = prompt_catalog.get_prompt_detail("portrait")

        self.assertEqual(detail["text"], "second\n")

    def test_save_structured_prompt_preserves_categories_as_json(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            detail = prompt_catalog.save_prompt(
                "portraits/miku",
                "ignored flat text",
                categories={"style": "best quality", "theme": "vocaloid, hatsune miku"},
                overwrite=False,
            )
            path = os.path.join(temp_dir, "portraits", "miku.json")
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            searched = prompt_catalog.search_prompts("hatsune")

        self.assertTrue(detail["structured"])
        self.assertEqual(detail["categories"]["style"], "best quality")
        self.assertEqual(detail["categories"]["theme"], "vocaloid, hatsune miku")
        self.assertEqual(detail["text"], "best quality\n\nvocaloid, hatsune miku\n")
        self.assertEqual(payload["type"], "prompt_helper")
        self.assertEqual(searched["results"][0]["id"], "portraits/miku")

    def test_rename_and_delete_prompt_refresh_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            prompt_catalog.save_prompt("old/name", "text", overwrite=False)
            renamed = prompt_catalog.rename_prompt("old/name", "new/name", overwrite=False)
            self.assertEqual(renamed["id"], "new/name")
            self.assertEqual(prompt_catalog.search_prompts("old")["results"], [])
            self.assertEqual(prompt_catalog.search_prompts("new")["results"][0]["id"], "new/name")
            deleted = prompt_catalog.delete_prompt("new/name")
            self.assertEqual(deleted, {"deleted": True, "id": "new/name"})
            with self.assertRaises(ValueError):
                prompt_catalog.get_prompt_detail("new/name")

    def test_rejects_unsafe_prompt_ids(self):
        for prompt_id in ("../secret", "bad/id!", "", "./bad", "/secret", "bad//id", "bad/"):
            with self.subTest(prompt_id=prompt_id):
                with self.assertRaises(ValueError):
                    prompt_catalog.normalize_prompt_id(prompt_id)

    def _write(self, root: str, rel_path: str, content: str) -> None:
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
