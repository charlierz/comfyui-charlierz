from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from nodes.PromptHelper import PromptHelperFillRequest, _read_category_tags


class PromptHelperCategoryTagTests(unittest.TestCase):
    def test_reads_category_tags_from_tag_pools(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "body/hair/color.tsv", "tag\tcount\nblue_hair\t10\nred hair\t5\n")
            with patch("nodes.PromptHelper.TAG_POOLS_DIR", temp_dir):
                tags = _read_category_tags("appearance_anatomy", 1)

        self.assertEqual(tags, ["blue hair"])

    def test_fill_request_can_include_category_tags_without_legacy_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(temp_dir, "body/hair/color.tsv", "tag\tcount\nblue_hair\t10\n")
            with patch("nodes.PromptHelper.TAG_POOLS_DIR", temp_dir):
                (prompt,) = PromptHelperFillRequest().build(
                    "{}",
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    5,
                    "",
                )

        self.assertIn("appearance_anatomy:", prompt)
        self.assertIn("blue hair", prompt)

    def _write(self, root: str, rel_path: str, content: str) -> None:
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
