from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class _Routes:
    def get(self, _path):
        return lambda handler: handler

    def post(self, _path):
        return lambda handler: handler


class _PromptServer:
    instance = types.SimpleNamespace(routes=_Routes())


sys.modules.setdefault("server", types.SimpleNamespace(PromptServer=_PromptServer))

from modules import api  # noqa: E402


class ApiCacheTests(unittest.TestCase):
    def setUp(self):
        api.clear_api_caches()

    def tearDown(self):
        api.clear_api_caches()

    def test_related_tag_file_is_indexed_once_per_method(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            relationships_dir = os.path.join(temp_dir, "tag_relationships")
            os.makedirs(relationships_dir)
            path = os.path.join(relationships_dir, "related_tags_lift.tsv")
            with open(path, "w", encoding="utf-8") as f:
                f.write("tag\trelated\n")
                f.write("blue_eyes\tlong hair, smile\n")

            with patch.object(api, "TAG_RELATIONSHIPS_DIR", relationships_dir), patch.object(
                api, "RELATED_METHOD_FILES", {"lift": "related_tags_lift.tsv"}
            ), patch("builtins.open", wraps=open) as opened:
                first = api._read_related("lift", "appearance_anatomy", "blue eyes")
                second = api._read_related("lift", "appearance_anatomy", "blue_eyes")

        self.assertEqual(first, ["long hair", "smile"])
        self.assertEqual(second, ["long hair", "smile"])
        self.assertEqual(opened.call_count, 1)


if __name__ == "__main__":
    unittest.main()
