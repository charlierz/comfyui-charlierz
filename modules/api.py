import json
import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

import server
from aiohttp import web

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_CATEGORIES_DIR = os.path.join(DATA_DIR, "tag_categories")
TAG_COOCCURRENCE_DIR = os.path.join(DATA_DIR, "tag_category_cooccurrence")
GENERAL_TAGS_FILE = os.path.join(DATA_DIR, "general.txt")
COPYRIGHT_TAGS_FILE = os.path.join(DATA_DIR, "copyrights.txt")
CHARACTERS_FILE = os.path.join(DATA_DIR, "characters.tsv")

CATEGORY_FILES = {
    "style_quality": "style_quality.txt",
    "themes_roles": "themes_roles.txt",
    "appearance_anatomy": "appearance_anatomy.txt",
    "clothing_accessories": "clothing_accessories.txt",
    "actions_poses": "actions_poses.txt",
    "expressions": "expressions.txt",
    "scene_background": "scene_background.txt",
}

CATEGORY_EXTRA_TAG_FILES = {
    "themes_roles": [COPYRIGHT_TAGS_FILE],
}

CATEGORY_EXTRA_TSV_KEY_FILES = {
    "themes_roles": [CHARACTERS_FILE],
}

EXCLUDED_RELATED_METHODS = {"conditional", "dice"}


def _normalize_server_url(server_url: str) -> str:
    server_url = server_url.strip().rstrip("/")
    if not server_url:
        raise ValueError("Missing server_url")
    return server_url


def _llama_get_json(url: str, timeout_seconds: int = 10) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llama.cpp server returned HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach llama.cpp server: {e.reason}") from e

    if not text:
        return {}
    return json.loads(text)


def _llama_post_json(url: str, payload: dict[str, Any], timeout_seconds: int = 60) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llama.cpp server returned HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach llama.cpp server: {e.reason}") from e

    if not text:
        return {}
    return json.loads(text)


def _normalize_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_")


def _split_tags(text: str) -> list[str]:
    return [tag.strip() for tag in text.replace("\n", ",").split(",") if tag.strip()]


def _read_tsv_keys(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.partition("\t")[0].strip() for line in f if line.partition("\t")[0].strip()]


@lru_cache(maxsize=1)
def _read_character_tags() -> dict[str, list[str]]:
    characters: dict[str, list[str]] = {}
    with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            character, separator, tags = line.strip().partition("\t")
            if character and separator:
                characters[character] = _split_tags(tags)
    return characters


@lru_cache(maxsize=1)
def _read_category_index() -> dict[str, str]:
    category_index: dict[str, str] = {}
    for category, filename in CATEGORY_FILES.items():
        path = os.path.join(TAG_CATEGORIES_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            for tag in _split_tags(f.read()):
                category_index.setdefault(tag, category)
    return category_index


def _read_tags(category: str) -> list[str]:
    if category == "general":
        with open(GENERAL_TAGS_FILE, "r", encoding="utf-8") as f:
            return _split_tags(f.read())
    if category == "copyrights":
        with open(COPYRIGHT_TAGS_FILE, "r", encoding="utf-8") as f:
            return _split_tags(f.read())
    if category == "characters":
        return _read_tsv_keys(CHARACTERS_FILE)

    filename = CATEGORY_FILES.get(category)
    if filename is None:
        raise ValueError(f"Unknown category: {category}")

    tags: list[str] = []
    path = os.path.join(TAG_CATEGORIES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        tags.extend(_split_tags(f.read()))

    for extra_path in CATEGORY_EXTRA_TAG_FILES.get(category, []):
        with open(extra_path, "r", encoding="utf-8") as f:
            tags.extend(_split_tags(f.read()))

    for extra_path in CATEGORY_EXTRA_TSV_KEY_FILES.get(category, []):
        tags.extend(_read_tsv_keys(extra_path))

    return list(dict.fromkeys(tags))


def _get_related_methods() -> list[str]:
    if not os.path.isdir(TAG_COOCCURRENCE_DIR):
        return []

    return sorted(
        name
        for name in os.listdir(TAG_COOCCURRENCE_DIR)
        if os.path.isdir(os.path.join(TAG_COOCCURRENCE_DIR, name))
        and name not in EXCLUDED_RELATED_METHODS
    )


def _read_character_tag_groups(character: str) -> dict[str, object]:
    character = _normalize_tag(character)
    character_tags = _read_character_tags().get(character)
    if character_tags is None:
        raise ValueError(f"Unknown character: {character}")

    category_index = _read_category_index()
    categories: dict[str, list[str]] = {category: [] for category in CATEGORY_FILES}
    uncategorized: list[str] = []

    for tag in character_tags:
        category = category_index.get(tag)
        if category is None:
            uncategorized.append(tag)
        else:
            categories[category].append(tag)

    return {
        "character": character,
        "categories": {category: tags for category, tags in categories.items() if tags},
        "uncategorized": uncategorized,
    }


def _read_related(method: str, category: str, tag: str) -> list[str]:
    if method not in _get_related_methods():
        raise ValueError(f"Unknown related-tag method: {method}")

    filename = CATEGORY_FILES.get(category)
    if filename is None:
        raise ValueError(f"Unknown category: {category}")

    tag = _normalize_tag(tag)
    cooccurrence_filename = os.path.splitext(filename)[0] + ".tsv"
    path = os.path.join(TAG_COOCCURRENCE_DIR, method, cooccurrence_filename)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            source_tag, separator, related_tags = line.partition("\t")
            if not separator:
                continue

            if source_tag == tag:
                return [related.strip() for related in related_tags.split(",") if related.strip()]

    return []


@server.PromptServer.instance.routes.get("/charlierz-llama-cpp/models")
async def get_llama_cpp_models(request):
    server_url = str(request.query.get("server_url", "http://127.0.0.1:8080"))
    try:
        models = _llama_get_json(f"{_normalize_server_url(server_url)}/models")
        return web.json_response(models)
    except (RuntimeError, ValueError) as e:
        return web.json_response({"error": str(e)}, status=400)


@server.PromptServer.instance.routes.post("/charlierz-llama-cpp/unload")
async def unload_llama_cpp_model(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    server_url = str(payload.get("server_url", "http://127.0.0.1:8080"))
    model = str(payload.get("model", "")).strip()
    if not model:
        return web.json_response({"error": "Missing model"}, status=400)

    try:
        result = _llama_post_json(
            f"{_normalize_server_url(server_url)}/models/unload",
            {"model": model},
        )
        return web.json_response(result)
    except (RuntimeError, ValueError) as e:
        return web.json_response({"error": str(e)}, status=400)


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/categories")
async def get_categories(_request):
    return web.json_response(list(CATEGORY_FILES.keys()))


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/related-methods")
async def get_related_methods(_request):
    return web.json_response(_get_related_methods())


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/tags/{category}")
async def get_tags(request):
    category = str(request.match_info["category"])
    try:
        return web.json_response(_read_tags(category))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except FileNotFoundError:
        return web.json_response({"error": "Tag category file not found"}, status=404)


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/character-tags")
async def get_character_tags(request):
    character = str(request.query.get("character", ""))
    if not character.strip():
        return web.json_response({"error": "Missing character"}, status=400)

    try:
        return web.json_response(_read_character_tag_groups(character))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=404)
    except FileNotFoundError:
        return web.json_response({"error": "Character tag file not found"}, status=404)


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/related/{method}/{category}")
async def get_related(request):
    method = str(request.match_info["method"])
    category = str(request.match_info["category"])
    tag = str(request.query.get("tag", ""))
    if not tag.strip():
        return web.json_response([])

    try:
        return web.json_response(_read_related(method, category, tag))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except FileNotFoundError:
        return web.json_response({"error": "Tag cooccurrence file not found"}, status=404)
