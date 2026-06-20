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
