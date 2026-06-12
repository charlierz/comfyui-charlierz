import json
import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

import server
from aiohttp import web

from .prompt_catalog import WEIGHT_MODES, expand_wildcards, get_wildcard_detail, list_wildcards, search_catalog
from .tag_data import (
    POOL_CATEGORY_MAP,
    TAG_ENTITIES_DIR,
    TAG_POOLS_DIR,
    TAG_RELATIONSHIPS_DIR,
    normalize_tag,
    read_tag_pool_tsv,
    read_tsv_keys,
)

CHARACTERS_ENTITIES_FILE = os.path.join(TAG_ENTITIES_DIR, "characters.tsv")
FRANCHISES_FILE = os.path.join(TAG_ENTITIES_DIR, "franchises.tsv")
CHARACTER_TAGS_FILE = os.path.join(TAG_RELATIONSHIPS_DIR, "character_tags.tsv")

# Map method names to tag_relationships filenames
RELATED_METHOD_FILES = {
    "jaccard": "related_tags_cosine_jaccard.tsv",
    "lift": "related_tags_lift.tsv",
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


def _split_tags(text: str) -> list[str]:
    return [tag.strip() for tag in text.replace("\n", ",").split(",") if tag.strip()]


@lru_cache(maxsize=1)
def _read_character_tags() -> dict[str, list[str]]:
    characters: dict[str, list[str]] = {}
    path = CHARACTER_TAGS_FILE
    if not os.path.exists(path):
        return characters
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f):
            columns = line.rstrip("\n").split("\t")
            if not columns or (line_number == 0 and columns[0] == "tag"):
                continue

            if len(columns) >= 3:
                character, tags = columns[0].strip(), columns[2]
            elif len(columns) == 2:
                character, tags = columns[0].strip(), columns[1]
            else:
                continue

            if character:
                characters[normalize_tag(character)] = _split_tags(tags)
    return characters


@lru_cache(maxsize=1)
def _read_category_index() -> dict[str, str]:
    category_index: dict[str, str] = {}
    if not os.path.isdir(TAG_POOLS_DIR):
        return category_index
    for root, _dirs, files in os.walk(TAG_POOLS_DIR):
        for filename in sorted(files):
            if not filename.endswith(".tsv"):
                continue
            path = os.path.join(root, filename)
            rel_path = os.path.relpath(path, TAG_POOLS_DIR)
            top_dir = rel_path.split(os.sep)[0]
            category = POOL_CATEGORY_MAP.get(top_dir)
            if category is None:
                continue
            for tag, _count in read_tag_pool_tsv(path):
                normalized = normalize_tag(tag)
                category_index.setdefault(normalized, category)
    return category_index


@lru_cache(maxsize=None)
def _read_tags(category: str) -> list[str]:
    # Entity categories
    if category == "copyrights":
        if os.path.exists(FRANCHISES_FILE):
            return read_tsv_keys(FRANCHISES_FILE)
        return []
    if category == "characters":
        if os.path.exists(CHARACTERS_ENTITIES_FILE):
            return read_tsv_keys(CHARACTERS_ENTITIES_FILE)
        return []
    if category == "themes_roles":
        tags: list[str] = []
        if os.path.exists(FRANCHISES_FILE):
            tags.extend(read_tsv_keys(FRANCHISES_FILE))
        if os.path.exists(CHARACTERS_ENTITIES_FILE):
            tags.extend(read_tsv_keys(CHARACTERS_ENTITIES_FILE))
        return tags

    # "general" returns all tags from all tag_pools
    if category == "general":
        all_tags: list[str] = []
        if os.path.isdir(TAG_POOLS_DIR):
            for root, _dirs, files in os.walk(TAG_POOLS_DIR):
                for filename in sorted(files):
                    if not filename.endswith(".tsv"):
                        continue
                    path = os.path.join(root, filename)
                    for tag, _count in read_tag_pool_tsv(path):
                        all_tags.append(tag)
        return list(dict.fromkeys(all_tags))

    # Category-specific: map to tag_pools directories
    pool_dirs = [d for d, cat in POOL_CATEGORY_MAP.items() if cat == category]
    if not pool_dirs:
        raise ValueError(f"Unknown category: {category}")

    result: list[str] = []
    for pool_dir in pool_dirs:
        dir_path = os.path.join(TAG_POOLS_DIR, pool_dir)
        if not os.path.isdir(dir_path):
            continue
        for root, _dirs, files in os.walk(dir_path):
            for filename in sorted(files):
                if not filename.endswith(".tsv"):
                    continue
                path = os.path.join(root, filename)
                for tag, _count in read_tag_pool_tsv(path):
                    result.append(tag)
    return list(dict.fromkeys(result))


@lru_cache(maxsize=1)
def _get_related_methods() -> list[str]:
    if not os.path.isdir(TAG_RELATIONSHIPS_DIR):
        return []

    methods: list[str] = []
    for method, filename in RELATED_METHOD_FILES.items():
        if method in EXCLUDED_RELATED_METHODS:
            continue
        path = os.path.join(TAG_RELATIONSHIPS_DIR, filename)
        if os.path.exists(path):
            methods.append(method)
    return sorted(methods)


def _read_character_tag_groups(character: str) -> dict[str, object]:
    character = normalize_tag(character)
    character_tags = _read_character_tags().get(character)
    if character_tags is None:
        raise ValueError(f"Unknown character: {character}")

    category_index = _read_category_index()
    categories: dict[str, list[str]] = {category: [] for category in sorted(set(POOL_CATEGORY_MAP.values()))}
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


@lru_cache(maxsize=None)
def _read_related_index(method: str) -> dict[str, list[str]]:
    if method not in _get_related_methods():
        raise ValueError(f"Unknown related-tag method: {method}")

    filename = RELATED_METHOD_FILES.get(method)
    if not filename:
        raise ValueError(f"Unknown related-tag method: {method}")

    path = os.path.join(TAG_RELATIONSHIPS_DIR, filename)
    if not os.path.exists(path):
        return {}

    index: dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f):
            if line_number == 0 and line.startswith("tag\t"):
                continue  # skip header
            source_tag, separator, related_tags = line.partition("\t")
            if not separator:
                continue
            value = related_tags.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            index[normalize_tag(source_tag)] = [r.strip() for r in value.split(",") if r.strip()]
    return index


def _read_related(method: str, category: str, tag: str) -> list[str]:
    del category  # Route compatibility; related files are currently method-wide.
    return _read_related_index(method).get(normalize_tag(tag), [])


def clear_api_caches() -> None:
    _read_character_tags.cache_clear()
    _read_category_index.cache_clear()
    _read_tags.cache_clear()
    _get_related_methods.cache_clear()
    _read_related_index.cache_clear()


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
    return web.json_response(sorted(set(POOL_CATEGORY_MAP.values())))


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/wildcards")
async def get_prompt_catalog_wildcards(_request):
    return web.json_response(list_wildcards())


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/wildcard")
async def get_prompt_catalog_wildcard(request):
    wildcard_id = str(request.query.get("id", ""))
    if not wildcard_id.strip():
        return web.json_response({"error": "Missing wildcard id"}, status=400)
    try:
        return web.json_response(get_wildcard_detail(wildcard_id))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=404)


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/search")
async def get_prompt_catalog_search(request):
    query = str(request.query.get("q", ""))
    context = str(request.query.get("context", "prompt"))
    if context not in {"prompt", "wildcard"}:
        context = "prompt"

    category = request.query.get("category")
    raw_types = str(request.query.get("types", "")).strip()
    types = {item.strip() for item in raw_types.split(",") if item.strip()} or None

    try:
        limit = int(request.query.get("limit", 80))
    except (TypeError, ValueError):
        limit = 80
    limit = max(1, min(limit, 200))

    try:
        return web.json_response(
            search_catalog(
                query,
                context=context,  # type: ignore[arg-type]
                category=str(category) if category else None,
                types=types,
                limit=limit,
            )
        )
    except FileNotFoundError as e:
        return web.json_response({"error": str(e)}, status=404)


@server.PromptServer.instance.routes.post("/charlierz-prompt-catalog/preview")
async def post_prompt_catalog_preview(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    text = str(payload.get("text", ""))
    try:
        seed = int(payload.get("seed", 0))
    except (TypeError, ValueError):
        seed = 0
    weight_mode = str(payload.get("weightMode", "count"))
    if weight_mode not in WEIGHT_MODES:
        weight_mode = "count"

    processed_text, diagnostics = expand_wildcards(text, seed=seed, weight_mode=weight_mode)  # type: ignore[arg-type]
    return web.json_response({"processedText": processed_text, "diagnostics": diagnostics})


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
