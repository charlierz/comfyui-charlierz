from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from modules import prompt_catalog
from nodes.WildcardExpander import WildcardExpander


class WildcardExpanderNodeTests(unittest.TestCase):
    def setUp(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        prompt_catalog.clear_prompt_catalog_caches()

    def test_expands_wildcard_text(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            prompt_catalog, "WILDCARDS_DIR", temp_dir
        ), patch.object(prompt_catalog, "TAG_POOLS_DIR", os.path.join(temp_dir, "missing_tag_pools")):
            os.makedirs(os.path.join(temp_dir, "color"))
            with open(os.path.join(temp_dir, "color", "basic.txt"), "w", encoding="utf-8") as f:
                f.write("red\n")

            result = WildcardExpander().expand("__color/basic__ dress", 0, "count")

        self.assertEqual(result["result"], ("red dress",))
        self.assertEqual(result["ui"], {"last_seed": [0]})

    def test_invalid_weight_mode_falls_back_to_sqrt(self):
        result = WildcardExpander().expand("plain text", 0, "invalid")
        self.assertEqual(result["result"], ("plain text",))

    def test_expands_structured_prompt_json_and_preserves_json(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            prompt_catalog, "WILDCARDS_DIR", temp_dir
        ), patch.object(prompt_catalog, "TAG_POOLS_DIR", os.path.join(temp_dir, "missing_tag_pools")):
            os.makedirs(os.path.join(temp_dir, "color"))
            with open(os.path.join(temp_dir, "color", "basic.txt"), "w", encoding="utf-8") as f:
                f.write("red\n")

            result = WildcardExpander().expand(
                '{"style": "anime", "clothes": "__color/basic__ dress"}',
                0,
                "count",
            )

        self.assertEqual(
            json.loads(result["result"][0]),
            {"style": "anime", "clothes": "red dress"},
        )


if __name__ == "__main__":
    unittest.main()
