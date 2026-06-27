from __future__ import annotations

import asyncio
import json
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

from modules import api, prompt_catalog  # noqa: E402


class _Request:
    def __init__(self, payload=None, query=None):
        self._payload = payload or {}
        self.query = query or {}

    async def json(self):
        return self._payload


def _json_body(response):
    return json.loads(response.text)


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

    def test_character_tags_with_spaces_are_categorized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = os.path.join(temp_dir, "tag_pools")
            os.makedirs(os.path.join(root, "appearance", "hair"))
            os.makedirs(os.path.join(root, "appearance", "face"))
            character_tags_path = os.path.join(temp_dir, "character_tags.tsv")

            with open(os.path.join(root, "appearance", "hair", "length.tsv"), "w", encoding="utf-8") as f:
                f.write("tag\tcount\n")
                f.write("long hair\t3608339\n")
            with open(os.path.join(root, "appearance", "face", "eyes.tsv"), "w", encoding="utf-8") as f:
                f.write("tag\tcount\n")
                f.write("purple eyes\t685847\n")
            with open(character_tags_path, "w", encoding="utf-8") as f:
                f.write("tag\trelated\n")
                f.write("emilia (re:zero)\tlong hair, purple eyes\n")

            with patch.object(api, "TAG_POOLS_DIR", root), patch.object(api, "CHARACTER_TAGS_FILE", character_tags_path):
                result = api._read_character_tag_groups("emilia_(re:zero)")

        self.assertEqual(result["categories"]["appearance"], ["long hair", "purple eyes"])
        self.assertEqual(result["uncategorized"], [])


class PromptWeightParsingTests(unittest.TestCase):
    """Weighted tags (prompt emphasis parens) must resolve to their canonical tag."""

    def setUp(self):
        api.clear_api_caches()

    def tearDown(self):
        api.clear_api_caches()

    def _write_pools(self, root: str) -> None:
        os.makedirs(os.path.join(root, "appearance", "hair"), exist_ok=True)
        os.makedirs(os.path.join(root, "clothes", "accessory"), exist_ok=True)
        with open(os.path.join(root, "appearance", "hair", "color.tsv"), "w", encoding="utf-8") as f:
            f.write("tag\tcount\nblue hair\t100\n")
        with open(os.path.join(root, "clothes", "accessory", "gem.tsv"), "w", encoding="utf-8") as f:
            f.write("tag\tcount\npearl (gemstone)\t50\n")

    def _write_related(self, root: str) -> None:
        with open(os.path.join(root, "related_tags_jaccard.tsv"), "w", encoding="utf-8") as f:
            f.write("tag\trelated\n")
            f.write("blue hair\tlong hair, smile\n")
            f.write("pearl (gemstone)\tgem, pearl necklace\n")

    def test_decompose_categorizes_weighted_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = os.path.join(temp_dir, "tag_pools")
            self._write_pools(root)
            with patch.object(api, "TAG_POOLS_DIR", root):
                result = api._decompose_prompt_text(
                    "(blue hair:1.3), ((blue hair)), pearl (gemstone), (pearl (gemstone))"
                )

        self.assertEqual(
            result["categories"].get("appearance"),
            ["(blue hair:1.3)", "((blue hair))"],
        )
        self.assertEqual(
            result["categories"].get("clothes"),
            ["pearl (gemstone)", "(pearl (gemstone))"],
        )
        self.assertEqual(result["uncategorized"], [])

    def test_related_lookup_resolves_weighted_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pools_root = os.path.join(temp_dir, "tag_pools")
            self._write_pools(pools_root)
            relationships_dir = os.path.join(temp_dir, "tag_relationships")
            os.makedirs(relationships_dir)
            self._write_related(relationships_dir)

            with patch.object(api, "TAG_POOLS_DIR", pools_root), patch.object(
                api, "TAG_RELATIONSHIPS_DIR", relationships_dir
            ), patch.object(
                api, "RELATED_METHOD_FILES", {"jaccard": "related_tags_jaccard.tsv"}
            ):
                weighted = api._read_related("jaccard", "appearance", "(blue hair:1.3)")
                nested = api._read_related("jaccard", "appearance", "((blue hair))")
                name_paren = api._read_related("jaccard", "clothes", "(pearl (gemstone))")
                detail = api._read_related_detail("jaccard", "appearance", "(blue hair:1.3)")

        self.assertEqual(weighted, ["long hair", "smile"])
        self.assertEqual(nested, ["long hair", "smile"])
        self.assertEqual(name_paren, ["gem", "pearl necklace"])
        self.assertEqual(detail["tag"], "blue_hair")
        self.assertEqual(detail["related"][0]["tag"], "long hair")



class PromptCatalogApiTests(unittest.TestCase):
    def setUp(self):
        api.clear_api_caches()
        prompt_catalog.clear_prompt_catalog_caches()

    def tearDown(self):
        api.clear_api_caches()
        prompt_catalog.clear_prompt_catalog_caches()

    def test_prompt_crud_routes(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            created = asyncio.run(
                api.post_prompt_catalog_prompt(_Request({"id": "Portraits/Soft Lighting", "text": "  1girl  "}))
            )
            created_body = _json_body(created)

            duplicate = asyncio.run(
                api.post_prompt_catalog_prompt(_Request({"id": "portraits/soft_lighting", "text": "other"}))
            )

            detail = asyncio.run(api.get_prompt_catalog_prompt(_Request(query={"id": "portraits/soft_lighting"})))
            renamed = asyncio.run(
                api.post_prompt_catalog_prompt_rename(
                    _Request({"id": "portraits/soft_lighting", "newId": "portraits/final"})
                )
            )
            deleted = asyncio.run(api.post_prompt_catalog_prompt_delete(_Request({"id": "portraits/final"})))

        self.assertEqual(created.status, 200)
        self.assertEqual(created_body["id"], "portraits/soft_lighting")
        self.assertEqual(created_body["text"], "1girl\n")
        self.assertEqual(duplicate.status, 409)
        self.assertEqual(_json_body(detail)["id"], "portraits/soft_lighting")
        self.assertEqual(_json_body(renamed)["id"], "portraits/final")
        self.assertEqual(_json_body(deleted), {"deleted": True, "id": "portraits/final"})

    def test_prompt_search_route(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            asyncio.run(api.post_prompt_catalog_prompt(_Request({"id": "scene/night", "text": "moonlit city"})))
            response = asyncio.run(api.get_prompt_catalog_prompt_search(_Request(query={"q": "moonlit"})))

        body = _json_body(response)
        self.assertEqual(response.status, 200)
        self.assertEqual(body["results"][0]["id"], "scene/night")

    def test_prompt_save_rejects_invalid_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(prompt_catalog, "PROMPTS_DIR", temp_dir):
            response = asyncio.run(api.post_prompt_catalog_prompt(_Request({"id": "bad!", "text": "text"})))
            empty = asyncio.run(api.post_prompt_catalog_prompt(_Request({"id": "ok", "text": "   "})))

        self.assertEqual(response.status, 400)
        self.assertEqual(empty.status, 400)


if __name__ == "__main__":
    unittest.main()
