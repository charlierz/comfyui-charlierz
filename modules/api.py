import json
import os
from functools import lru_cache
from typing import Any

import server
from aiohttp import web

from .llama_cpp_client import get_json as llama_get_json
from .llama_cpp_client import normalize_server_url as normalize_llama_url
from .llama_cpp_client import post_json as llama_post_json
from .prompt_catalog import (
    WEIGHT_MODES,
    delete_prompt,
    expand_wildcards,
    get_prompt_detail,
    get_wildcard_detail,
    list_prompts,
    list_wildcards,
    rename_prompt,
    save_prompt,
    search_catalog,
    search_prompts,
)
from .tag_data import (
    ENTITY_SOURCE_FILES,
    TAG_POOLS_DIR,
    TAG_RELATIONSHIPS_DIR,
    clear_prompt_category_cache,
    normalize_tag,
    prompt_categories_json,
    prompt_category_ids,
    prompt_category_source_map,
    read_tag_pool_tsv,
    read_tsv_keys,
    tag_pool_category_map,
)

CHARACTER_TAGS_FILE = os.path.join(TAG_RELATIONSHIPS_DIR, "character_tags.tsv")

# Map method names to tag_relationships filenames
RELATED_METHOD_FILES = {
    "jaccard": "related_tags_cosine_jaccard.tsv",
    "lift": "related_tags_lift.tsv",
}

EXCLUDED_RELATED_METHODS = {"conditional", "dice"}


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
            category = tag_pool_category_map().get(top_dir)
            if category is None:
                continue
            for tag, _count in read_tag_pool_tsv(path):
                normalized = normalize_tag(tag)
                category_index.setdefault(normalized, category)
    return category_index


@lru_cache(maxsize=1)
def _read_tag_categories_index() -> dict[str, list[str]]:
    category_index: dict[str, list[str]] = {}
    for category_id, category in prompt_category_source_map().items():
        for source in category.sources:
            if source.startswith("tag_pools/"):
                pool = source.removeprefix("tag_pools/")
                dir_path = os.path.join(TAG_POOLS_DIR, pool)
                if not os.path.isdir(dir_path):
                    continue
                for root, _dirs, files in os.walk(dir_path):
                    for filename in sorted(files):
                        if not filename.endswith(".tsv"):
                            continue
                        for tag, _count in read_tag_pool_tsv(os.path.join(root, filename)):
                            categories = category_index.setdefault(normalize_tag(tag), [])
                            if category_id not in categories:
                                categories.append(category_id)
            elif source in ENTITY_SOURCE_FILES:
                for tag in read_tsv_keys(ENTITY_SOURCE_FILES[source]):
                    categories = category_index.setdefault(normalize_tag(tag), [])
                    if category_id not in categories:
                        categories.append(category_id)
    return category_index


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
    categories: dict[str, list[str]] = {category: [] for category in prompt_category_ids()}
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


def _read_related_detail(method: str, category: str, tag: str) -> dict[str, object]:
    normalized_tag = normalize_tag(tag)
    category_index = _read_tag_categories_index()
    return {
        "tag": normalized_tag,
        "clickedCategory": category,
        "categories": category_index.get(normalized_tag, []),
        "related": [
            {
                "tag": related_tag,
                "label": related_tag.replace("_", " "),
                "insertText": related_tag.replace("_", " "),
                "category": (category_index.get(normalize_tag(related_tag)) or [None])[0],
                "categories": category_index.get(normalize_tag(related_tag), []),
            }
            for related_tag in _read_related(method, category, tag)
        ],
    }


def _category_for_wildcard_token(token: str) -> str | None:
    stripped = token.strip()
    if not (stripped.startswith("__") and stripped.endswith("__")):
        return None
    wildcard_id = stripped[2:-2].strip().split("/", 1)[0]
    if not wildcard_id or "*" in wildcard_id:
        return None
    return tag_pool_category_map().get(wildcard_id)


def _decompose_prompt_text(text: str) -> dict[str, object]:
    category_index = _read_tag_categories_index()
    categories: dict[str, list[str]] = {category: [] for category in prompt_category_ids()}
    uncategorized: list[str] = []

    for tag in _split_tags(text):
        category = _category_for_wildcard_token(tag)
        if category is None:
            category = (category_index.get(normalize_tag(tag)) or [None])[0]

        if category is None:
            uncategorized.append(tag)
        else:
            categories.setdefault(category, []).append(tag)

    return {
        "categories": {category: tags for category, tags in categories.items() if tags},
        "uncategorized": uncategorized,
    }


def clear_api_caches() -> None:
    clear_prompt_category_cache()
    _read_character_tags.cache_clear()
    _read_category_index.cache_clear()
    _read_tag_categories_index.cache_clear()
    _get_related_methods.cache_clear()
    _read_related_index.cache_clear()


@server.PromptServer.instance.routes.get("/charlierz-llama-cpp/models")
async def get_llama_cpp_models(request):
    server_url = str(request.query.get("server_url", "http://127.0.0.1:8080"))
    try:
        models = llama_get_json(f"{normalize_llama_url(server_url)}/models")
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
        result = llama_post_json(
            f"{normalize_llama_url(server_url)}/models/unload",
            {"model": model},
        )
        return web.json_response(result)
    except (RuntimeError, ValueError) as e:
        return web.json_response({"error": str(e)}, status=400)


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/categories")
async def get_prompt_helper_categories(_request):
    try:
        return web.json_response(prompt_categories_json())
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=500)


@server.PromptServer.instance.routes.post("/charlierz-prompt-helper/decompose")
async def post_prompt_helper_decompose(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    return web.json_response(_decompose_prompt_text(str(payload.get("text", ""))))


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


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/prompts")
async def get_prompt_catalog_prompts(_request):
    return web.json_response(list_prompts())


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/prompt")
async def get_prompt_catalog_prompt(request):
    prompt_id = str(request.query.get("id", ""))
    if not prompt_id.strip():
        return web.json_response({"error": "Missing prompt id"}, status=400)
    try:
        return web.json_response(get_prompt_detail(prompt_id))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=404)


@server.PromptServer.instance.routes.get("/charlierz-prompt-catalog/prompt-search")
async def get_prompt_catalog_prompt_search(request):
    query = str(request.query.get("q", ""))
    try:
        limit = int(request.query.get("limit", 80))
    except (TypeError, ValueError):
        limit = 80
    limit = max(1, min(limit, 200))
    return web.json_response(search_prompts(query, limit=limit))


@server.PromptServer.instance.routes.post("/charlierz-prompt-catalog/prompt")
async def post_prompt_catalog_prompt(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    prompt_id = str(payload.get("id", ""))
    text = str(payload.get("text", ""))
    overwrite = bool(payload.get("overwrite", False))
    try:
        return web.json_response(save_prompt(prompt_id, text, overwrite=overwrite))
    except FileExistsError as e:
        return web.json_response({"error": str(e)}, status=409)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)


@server.PromptServer.instance.routes.post("/charlierz-prompt-catalog/prompt/rename")
async def post_prompt_catalog_prompt_rename(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    prompt_id = str(payload.get("id", ""))
    new_id = str(payload.get("newId", ""))
    overwrite = bool(payload.get("overwrite", False))
    try:
        return web.json_response(rename_prompt(prompt_id, new_id, overwrite=overwrite))
    except FileExistsError as e:
        return web.json_response({"error": str(e)}, status=409)
    except ValueError as e:
        message = str(e)
        status = 404 if message.startswith("Unknown prompt:") else 400
        return web.json_response({"error": message}, status=status)


@server.PromptServer.instance.routes.post("/charlierz-prompt-catalog/prompt/delete")
async def post_prompt_catalog_prompt_delete(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    prompt_id = str(payload.get("id", ""))
    try:
        return web.json_response(delete_prompt(prompt_id))
    except ValueError as e:
        message = str(e)
        status = 404 if message.startswith("Unknown prompt:") else 400
        return web.json_response({"error": message}, status=status)


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
    weight_mode = str(payload.get("weightMode", "sqrt"))
    if weight_mode not in WEIGHT_MODES:
        weight_mode = "sqrt"

    processed_text, diagnostics = expand_wildcards(text, seed=seed, weight_mode=weight_mode)  # type: ignore[arg-type]
    return web.json_response({"processedText": processed_text, "diagnostics": diagnostics})


@server.PromptServer.instance.routes.get("/charlierz-prompt-helper/related-methods")
async def get_related_methods(_request):
    return web.json_response(_get_related_methods())


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
        return web.json_response(_read_related_detail(method, category, tag))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except FileNotFoundError:
        return web.json_response({"error": "Tag cooccurrence file not found"}, status=404)
