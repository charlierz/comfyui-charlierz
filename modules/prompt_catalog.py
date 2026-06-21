from __future__ import annotations

import csv
import json
import math
import os
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from .tag_data import (
    DATA_DIR,
    CHARACTERS_ENTITIES_FILE,
    FRANCHISES_FILE,
    TAG_POOLS_DIR,
    TAG_RELATIONSHIPS_DIR,
    clear_prompt_category_cache,
    display_tag,
    normalize_tag,
    prompt_category_ids,
    prompt_category_source_map,
    read_tag_pool_tsv,
    tag_pool_category_map,
)

WILDCARDS_DIR = os.path.join(DATA_DIR, "wildcards")
PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")
CHARACTER_TAGS_FILE = os.path.join(TAG_RELATIONSHIPS_DIR, "character_tags.tsv")
CHARACTER_RELATED_MAX_TAGS = 10

MAX_EXPANSION_DEPTH = 32
WeightMode = Literal["count", "sqrt", "log", "random"]
WEIGHT_MODES = ("count", "sqrt", "log", "random")


@dataclass(frozen=True)
class TagRecord:
    label: str
    normalized: str
    category: str
    rank: int
    count: int = 0


@dataclass(frozen=True)
class WildcardTag:
    text: str
    weight: float
    line_number: int


@dataclass(frozen=True)
class WildcardRecord:
    id: str
    path: str
    label: str
    tags: tuple[WildcardTag, ...]
    metadata: dict[str, Any]
    duplicate: bool = False


@dataclass(frozen=True)
class PromptRecord:
    id: str
    path: str
    label: str
    text: str
    categories: dict[str, str] | None = None


@dataclass
class ExpansionDiagnostics:
    messages: list[str]

    def warn(self, message: str) -> None:
        self.messages.append(message)
        print(f"[charlierz wildcard] {message}")


@dataclass
class ExpansionContext:
    character_tag: str | None = None
    emitted_text: str = ""


@lru_cache(maxsize=1)
def read_tag_records() -> list[TagRecord]:
    records: list[TagRecord] = []
    seen: set[str] = set()

    # Read from tag_pools/**/*.tsv
    if os.path.isdir(TAG_POOLS_DIR):
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

                tag_rows = read_tag_pool_tsv(path)
                # Sort by count descending, then alphabetically by tag
                tag_rows.sort(key=lambda x: (-x[1], x[0]))

                for rank, (tag, count) in enumerate(tag_rows):
                    normalized = normalize_tag(tag)
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    records.append(
                        TagRecord(label=display_tag(tag), normalized=normalized, category=category, rank=rank, count=count)
                    )

    # Read copyright/franchise entities
    if os.path.exists(FRANCHISES_FILE):
        franchise_entries = read_tag_pool_tsv(FRANCHISES_FILE)
        franchise_entries.sort(key=lambda x: (-x[1], x[0]))
        for rank, (tag, count) in enumerate(franchise_entries):
            normalized = normalize_tag(tag)
            if normalized in seen:
                continue
            seen.add(normalized)
            records.append(
                TagRecord(label=display_tag(tag), normalized=normalized, category="copyrights", rank=rank, count=count)
            )

    # Read character entities
    if os.path.exists(CHARACTERS_ENTITIES_FILE):
        character_entries = read_tag_pool_tsv(CHARACTERS_ENTITIES_FILE)
        character_entries.sort(key=lambda x: (-x[1], x[0]))
        character_rank = 0
        for tag, count in character_entries:
            normalized = normalize_tag(tag)
            if not tag or normalized in seen:
                continue
            seen.add(normalized)
            records.append(
                TagRecord(label=display_tag(tag), normalized=normalized, category="characters", rank=character_rank, count=count)
            )
            character_rank += 1

    return records


@lru_cache(maxsize=1)
def scan_wildcards() -> tuple[list[WildcardRecord], list[str]]:
    diagnostics: list[str] = []
    records: list[WildcardRecord] = []
    seen_paths_by_id: dict[str, str] = {}

    if os.path.isdir(WILDCARDS_DIR):
        for root, _dirs, files in os.walk(WILDCARDS_DIR):
            for filename in sorted(files):
                if not filename.endswith(".txt") or filename.endswith(".meta.json"):
                    continue

                path = os.path.join(root, filename)
                rel_path = os.path.relpath(path, WILDCARDS_DIR)
                wildcard_id = normalize_wildcard_id(os.path.splitext(rel_path)[0])
                if wildcard_id in seen_paths_by_id:
                    diagnostics.append(
                        f"Duplicate wildcard id {wildcard_id}: {seen_paths_by_id[wildcard_id]} wins over {rel_path}"
                    )
                    continue

                seen_paths_by_id[wildcard_id] = rel_path
                records.append(
                    WildcardRecord(
                        id=wildcard_id,
                        path=rel_path,
                        label=display_wildcard_label(wildcard_id),
                        tags=tuple(_read_wildcard_tags(path)),
                        metadata=_read_wildcard_metadata(path),
                    )
                )

    entity_wildcards = (
        (
            "characters",
            CHARACTERS_ENTITIES_FILE,
            _read_character_entity_wildcard_tags,
            "characters",
        ),
        (
            "franchises",
            FRANCHISES_FILE,
            _read_entity_wildcard_tags,
            "copyrights",
        ),
    )
    for wildcard_id, path, reader, prompt_category in entity_wildcards:
        if not os.path.exists(path):
            continue
        if wildcard_id in seen_paths_by_id:
            diagnostics.append(
                f"Duplicate wildcard id {wildcard_id}: {seen_paths_by_id[wildcard_id]} wins over entity file {os.path.relpath(path, DATA_DIR)}"
            )
            continue
        seen_paths_by_id[wildcard_id] = os.path.relpath(path, DATA_DIR)
        records.append(
            WildcardRecord(
                id=wildcard_id,
                path=os.path.relpath(path, DATA_DIR),
                label=display_wildcard_label(wildcard_id),
                tags=tuple(reader(path)),
                metadata={
                    "displayName": display_wildcard_label(wildcard_id),
                    "sourceType": "tag_entity",
                    "promptCategory": _category_for_source(f"tag_entities/{wildcard_id}") or prompt_category,
                },
            )
        )

    special_wildcards = (
        ("character_appearance", "Character appearance tags", "appearance"),
        ("character_clothes", "Character clothes tags", "clothes"),
    )
    for wildcard_id, display_name, prompt_category in special_wildcards:
        if wildcard_id in seen_paths_by_id:
            diagnostics.append(
                f"Duplicate wildcard id {wildcard_id}: {seen_paths_by_id[wildcard_id]} wins over special wildcard"
            )
            continue
        seen_paths_by_id[wildcard_id] = "special"
        records.append(
            WildcardRecord(
                id=wildcard_id,
                path="special",
                label=display_wildcard_label(wildcard_id),
                tags=(),
                metadata={
                    "displayName": display_name,
                    "sourceType": "special",
                    "promptCategory": prompt_category,
                    "description": "Uses the character selected by __characters__ or a literal character tag earlier in the same expansion.",
                },
            )
        )

    if os.path.isdir(TAG_POOLS_DIR):
        directory_tags: dict[str, list[WildcardTag]] = {}
        directory_sources: dict[str, list[str]] = {}

        for root, _dirs, files in os.walk(TAG_POOLS_DIR):
            for filename in sorted(files):
                if not filename.endswith(".tsv"):
                    continue

                path = os.path.join(root, filename)
                rel_path = os.path.relpath(path, TAG_POOLS_DIR)
                wildcard_id = normalize_wildcard_id(os.path.splitext(rel_path)[0])
                tags = tuple(_read_tag_pool_wildcard_tags(path))
                parts = wildcard_id.split("/")
                for depth in range(1, len(parts)):
                    directory_id = "/".join(parts[:depth])
                    directory_tags.setdefault(directory_id, []).extend(tags)
                    directory_sources.setdefault(directory_id, []).append(f"tag_pools/{rel_path}")

                if wildcard_id in seen_paths_by_id:
                    diagnostics.append(
                        f"Duplicate wildcard id {wildcard_id}: {seen_paths_by_id[wildcard_id]} wins over tag pool {rel_path}"
                    )
                    continue

                seen_paths_by_id[wildcard_id] = f"tag_pools/{rel_path}"
                records.append(
                    WildcardRecord(
                        id=wildcard_id,
                        path=f"tag_pools/{rel_path}",
                        label=display_wildcard_label(wildcard_id),
                        tags=tags,
                        metadata={
                            "displayName": display_wildcard_label(wildcard_id),
                            "sourceType": "tag_pool",
                            "promptCategory": tag_pool_category_map().get(wildcard_id.split("/", 1)[0]),
                        },
                    )
                )

        for directory_id in sorted(directory_tags):
            if directory_id in seen_paths_by_id:
                continue

            sources = directory_sources.get(directory_id, [])
            seen_paths_by_id[directory_id] = f"tag_pools/{directory_id}/"
            records.append(
                WildcardRecord(
                    id=directory_id,
                    path=f"tag_pools/{directory_id}/",
                    label=display_wildcard_label(directory_id),
                    tags=tuple(directory_tags[directory_id]),
                    metadata={
                        "displayName": display_wildcard_label(directory_id),
                        "sourceType": "tag_pool_directory",
                        "promptCategory": tag_pool_category_map().get(directory_id.split("/", 1)[0]),
                        "sourceCount": len(sources),
                    },
                )
            )

    return (records, diagnostics)


@lru_cache(maxsize=1)
def wildcard_map() -> tuple[dict[str, WildcardRecord], list[str]]:
    records, diagnostics = scan_wildcards()
    return ({record.id: record for record in records}, diagnostics)


def clear_prompt_catalog_caches() -> None:
    clear_prompt_category_cache()
    read_tag_records.cache_clear()
    scan_wildcards.cache_clear()
    wildcard_map.cache_clear()
    _read_character_related_tags.cache_clear()
    _read_character_tag_set.cache_clear()
    _read_related_tag_category_index.cache_clear()
    scan_prompts.cache_clear()
    prompt_map.cache_clear()


def get_wildcard_detail(wildcard_id: str) -> dict[str, Any]:
    records, diagnostics = wildcard_map()
    normalized_id = normalize_wildcard_id(_normalize_search_query(wildcard_id))
    record = records.get(normalized_id)
    if record is None:
        raise ValueError(f"Unknown wildcard: {normalized_id}")

    return {
        "type": "wildcard",
        "id": record.id,
        "label": record.metadata.get("displayName") or record.label,
        "insertText": f"__{record.id}__",
        "path": record.path,
        "tagCount": len(record.tags),
        "promptCategory": record.metadata.get("promptCategory"),
        "tags": [
            {"text": tag.text, "weight": tag.weight, "lineNumber": tag.line_number}
            for tag in record.tags
        ],
        "metadata": record.metadata,
        "diagnostics": diagnostics,
    }


def list_wildcards() -> dict[str, Any]:
    records, diagnostics = scan_wildcards()
    tree: dict[str, Any] = {"type": "directory", "label": "wildcards", "children": {}}

    for record in records:
        node = tree
        parts = record.id.split("/")
        for part in parts[:-1]:
            children = node.setdefault("children", {})
            node = children.setdefault(
                part,
                {"type": "directory", "label": part.replace("_", " "), "children": {}},
            )

        children = node.setdefault("children", {})
        existing = children.get(parts[-1])
        wildcard_node = {
            "type": "wildcard",
            "id": record.id,
            "label": record.metadata.get("displayName") or record.label,
            "insertText": f"__{record.id}__",
            "path": record.path,
            "tagCount": len(record.tags),
            "promptCategory": record.metadata.get("promptCategory"),
        }
        if isinstance(existing, dict) and existing.get("type") == "directory":
            existing.update({k: v for k, v in wildcard_node.items() if k != "type"})
        else:
            children[parts[-1]] = wildcard_node

    return {"tree": _sort_tree(tree), "diagnostics": diagnostics}


@lru_cache(maxsize=1)
def scan_prompts() -> tuple[list[PromptRecord], list[str]]:
    diagnostics: list[str] = []
    records: list[PromptRecord] = []
    seen_paths_by_id: dict[str, str] = {}

    if not os.path.isdir(PROMPTS_DIR):
        return (records, diagnostics)

    for root, _dirs, files in os.walk(PROMPTS_DIR):
        for filename in sorted(files):
            if not filename.endswith((".txt", ".json")):
                continue

            path = os.path.join(root, filename)
            rel_path = os.path.relpath(path, PROMPTS_DIR)
            try:
                prompt_id = normalize_prompt_id(os.path.splitext(rel_path)[0])
            except ValueError as e:
                diagnostics.append(f"Invalid prompt path {rel_path}: {e}")
                continue

            if prompt_id in seen_paths_by_id:
                diagnostics.append(f"Duplicate prompt id {prompt_id}: {seen_paths_by_id[prompt_id]} wins over {rel_path}")
                continue

            try:
                text, categories = _read_prompt_file(path)
            except (OSError, ValueError) as e:
                diagnostics.append(f"Failed to read prompt {rel_path}: {e}")
                continue

            seen_paths_by_id[prompt_id] = rel_path
            records.append(
                PromptRecord(
                    id=prompt_id,
                    path=rel_path.replace(os.sep, "/"),
                    label=display_wildcard_label(prompt_id),
                    text=text,
                    categories=categories,
                )
            )

    return (records, diagnostics)


@lru_cache(maxsize=1)
def prompt_map() -> tuple[dict[str, PromptRecord], list[str]]:
    records, diagnostics = scan_prompts()
    return ({record.id: record for record in records}, diagnostics)


def list_prompts() -> dict[str, Any]:
    records, diagnostics = scan_prompts()
    tree: dict[str, Any] = {"type": "directory", "label": "prompts", "children": {}}

    for record in records:
        node = tree
        parts = record.id.split("/")
        for part in parts[:-1]:
            children = node.setdefault("children", {})
            node = children.setdefault(
                part,
                {"type": "directory", "label": part.replace("_", " "), "children": {}},
            )

        children = node.setdefault("children", {})
        children[parts[-1]] = _prompt_summary(record)

    return {"tree": _sort_tree(tree), "diagnostics": diagnostics}


def get_prompt_detail(prompt_id: str) -> dict[str, Any]:
    records, diagnostics = prompt_map()
    normalized_id = normalize_prompt_id(prompt_id)
    record = records.get(normalized_id)
    if record is None:
        raise ValueError(f"Unknown prompt: {normalized_id}")
    return {**_prompt_summary(record), "text": record.text, "diagnostics": diagnostics}


def search_prompts(query: str, *, limit: int = 80) -> dict[str, Any]:
    query = query.strip()
    normalized_query = normalize_tag(query).lower()
    text_query = query.lower()
    if not normalized_query and not text_query:
        return {"results": [], "diagnostics": []}

    records, diagnostics = scan_prompts()
    results: list[dict[str, Any]] = []
    for prompt in records:
        match_tier = _prompt_match_tier(prompt, normalized_query, text_query)
        if match_tier is None:
            continue
        results.append({**_prompt_summary(prompt), "matchTier": match_tier})

    results.sort(key=lambda item: (int(item.get("matchTier", 99)), str(item.get("id", ""))))
    return {
        "results": [{k: v for k, v in item.items() if k != "matchTier"} for item in results[:limit]],
        "diagnostics": diagnostics,
    }


def save_prompt(
    prompt_id: str,
    text: str,
    *,
    overwrite: bool = False,
    categories: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_id = normalize_prompt_id(prompt_id)
    normalized_categories = _normalize_prompt_categories(categories) if categories is not None else None
    normalized_text = (
        _render_prompt_categories(normalized_categories)
        if normalized_categories is not None
        else _normalize_prompt_text(text)
    )
    path = _prompt_path(normalized_id, structured=normalized_categories is not None)
    existing_paths = _existing_prompt_paths(normalized_id)
    if existing_paths and not overwrite:
        raise FileExistsError(f"Prompt already exists: {normalized_id}")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    for existing_path in existing_paths:
        if existing_path != path:
            os.remove(existing_path)
    if normalized_categories is not None:
        _write_structured_prompt(path, normalized_categories)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(normalized_text)
    _clear_prompt_caches()
    return get_prompt_detail(normalized_id)


def rename_prompt(prompt_id: str, new_id: str, *, overwrite: bool = False) -> dict[str, Any]:
    old_id = normalize_prompt_id(prompt_id)
    normalized_new_id = normalize_prompt_id(new_id)
    old_path = _single_existing_prompt_path(old_id)
    if old_path is None:
        raise ValueError(f"Unknown prompt: {old_id}")
    new_path = _prompt_path(normalized_new_id, structured=old_path.endswith(".json"))
    existing_new_paths = _existing_prompt_paths(normalized_new_id)
    if existing_new_paths and old_path not in existing_new_paths and not overwrite:
        raise FileExistsError(f"Prompt already exists: {normalized_new_id}")
    if old_path == new_path:
        return get_prompt_detail(old_id)

    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    for existing_path in existing_new_paths:
        if existing_path != old_path:
            os.remove(existing_path)
    os.replace(old_path, new_path)
    _remove_empty_parent_dirs(os.path.dirname(old_path))
    _clear_prompt_caches()
    return get_prompt_detail(normalized_new_id)


def delete_prompt(prompt_id: str) -> dict[str, Any]:
    normalized_id = normalize_prompt_id(prompt_id)
    paths = _existing_prompt_paths(normalized_id)
    if not paths:
        raise ValueError(f"Unknown prompt: {normalized_id}")
    for path in paths:
        os.remove(path)
        _remove_empty_parent_dirs(os.path.dirname(path))
    _clear_prompt_caches()
    return {"deleted": True, "id": normalized_id}


def normalize_prompt_id(value: str) -> str:
    raw = value.replace(os.sep, "/").replace("\\", "/").strip()
    if not raw:
        raise ValueError("Prompt id is empty")
    if raw.startswith("/") or raw.endswith("/") or "//" in raw:
        raise ValueError("Prompt id has invalid separators")
    if any(part.strip() in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError("Prompt id contains an invalid segment")

    normalized = normalize_wildcard_id(raw)
    if not re.fullmatch(r"[a-z0-9_-]+(?:/[a-z0-9_-]+)*", normalized):
        raise ValueError("Prompt id contains unsafe characters")
    return normalized


def _prompt_summary(record: PromptRecord) -> dict[str, Any]:
    summary = {
        "type": "prompt",
        "id": record.id,
        "label": record.label,
        "insertText": record.text,
        "path": record.path,
        "preview": _prompt_preview(record.text),
        "structured": record.categories is not None,
    }
    if record.categories is not None:
        summary["categories"] = record.categories
    return summary


def _prompt_match_tier(prompt: PromptRecord, normalized_query: str, text_query: str) -> int | None:
    id_text = prompt.id
    id_space = id_text.replace("/", " ").replace("_", " ").replace("-", " ")
    label = prompt.label.lower().replace("_", " ").replace("-", " ")
    text = prompt.text.lower()
    query_path = ""
    if text_query and re.fullmatch(r"[a-z0-9_\-/ ]+", text_query):
        try:
            query_path = normalize_prompt_id(text_query.replace(" ", "/"))
        except ValueError:
            query_path = ""
    query_variants = [query for query in (query_path, normalized_query) if query]

    if any(id_text == query for query in query_variants):
        return 0
    if any(id_text.startswith(f"{query}/") or id_text.startswith(query) for query in query_variants):
        return 1
    if any(label.startswith(query.replace("_", " ")) for query in query_variants):
        return 2
    if any(query in haystack for query in query_variants for haystack in (id_text, id_space)):
        return 3
    if text_query and text_query in text:
        return 4
    if normalized_query and normalized_query.replace("_", " ") in text:
        return 5
    return None


def _prompt_preview(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) > 160:
        return f"{first_line[:157]}..."
    return first_line


def _normalize_prompt_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("Prompt text is empty")
    return f"{normalized}\n"


def _read_prompt_file(path: str) -> tuple[str, dict[str, str] | None]:
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("Structured prompt must be a JSON object")
        categories = _normalize_prompt_categories(payload.get("categories"))
        return (_render_prompt_categories(categories), categories)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return (f.read(), None)


def _normalize_prompt_categories(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Prompt categories must be an object")
    categories: dict[str, str] = {}
    for category_id in prompt_category_ids():
        text = str(value.get(category_id, "")).replace("\r\n", "\n").replace("\r", "\n").strip()
        categories[category_id] = text
    if not any(categories.values()):
        raise ValueError("Prompt categories are empty")
    return categories


def _render_prompt_categories(categories: dict[str, str]) -> str:
    rendered = "\n\n".join(text for text in categories.values() if text.strip()).strip()
    if not rendered:
        raise ValueError("Prompt text is empty")
    return f"{rendered}\n"


def _write_structured_prompt(path: str, categories: dict[str, str]) -> None:
    payload = {"type": "prompt_helper", "version": 1, "categories": categories}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _prompt_path(prompt_id: str, *, structured: bool = False) -> str:
    normalized_id = normalize_prompt_id(prompt_id)
    root = os.path.abspath(PROMPTS_DIR)
    suffix = ".json" if structured else ".txt"
    path = os.path.abspath(os.path.join(root, *normalized_id.split("/"))) + suffix
    if os.path.commonpath([root, path]) != root:
        raise ValueError("Prompt path escapes prompt directory")
    return path


def _existing_prompt_paths(prompt_id: str) -> list[str]:
    return [path for path in (_prompt_path(prompt_id), _prompt_path(prompt_id, structured=True)) if os.path.exists(path)]


def _single_existing_prompt_path(prompt_id: str) -> str | None:
    paths = _existing_prompt_paths(prompt_id)
    return paths[0] if paths else None


def _remove_empty_parent_dirs(path: str) -> None:
    root = os.path.abspath(PROMPTS_DIR)
    current = os.path.abspath(path)
    while current.startswith(root) and current != root:
        try:
            os.rmdir(current)
        except OSError:
            break
        current = os.path.dirname(current)


def _clear_prompt_caches() -> None:
    scan_prompts.cache_clear()
    prompt_map.cache_clear()


def search_catalog(
    query: str,
    *,
    context: Literal["prompt", "wildcard"] = "prompt",
    category: str | None = None,
    types: set[str] | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    query = _normalize_search_query(query)
    normalized_query = normalize_tag(query).lower()
    text_query = query.strip().lower()
    if not normalized_query and not text_query:
        return {"results": [], "diagnostics": []}

    requested = types or {"tag", "wildcard"}
    results: list[dict[str, Any]] = []

    if "tag" in requested:
        for tag in read_tag_records():
            score = _tag_score(tag, normalized_query, category)
            if score is None:
                continue
            results.append(
                {
                    "type": "tag",
                    "label": tag.label,
                    "insertText": tag.label,
                    "category": tag.category,
                    "promptCategory": _tag_prompt_category(tag),
                    "priorityClass": _tag_priority_class(tag, category),
                    "count": tag.count,
                    "matchTier": _tag_match_tier(tag, normalized_query),
                    "score": score + (1000 if context == "prompt" else 0),
                }
            )

    records, diagnostics = scan_wildcards()
    for wildcard in records:
        if "wildcard" in requested:
            match = _wildcard_match(wildcard, normalized_query, text_query, category)
            if match is not None:
                match_tier, segment_index = match
                results.append(
                    {
                        "type": "wildcard",
                        "id": wildcard.id,
                        "label": wildcard.metadata.get("displayName") or wildcard.label,
                        "insertText": f"__{wildcard.id}__",
                        "path": wildcard.path,
                        "tagCount": len(wildcard.tags),
                        "promptCategory": wildcard.metadata.get("promptCategory"),
                        "matchTier": match_tier,
                        "segmentIndex": segment_index,
                        "depth": wildcard.id.count("/"),
                    }
                )

    results.sort(key=lambda item: _catalog_result_sort_key(item, context))
    return {
        "results": [
            {k: v for k, v in item.items() if k not in {"score", "matchTier", "segmentIndex", "depth"}}
            for item in results[:limit]
        ],
        "diagnostics": diagnostics,
    }


def _catalog_result_sort_key(
    item: dict[str, Any], context: Literal["prompt", "wildcard"]
) -> tuple[int, int, int, int, int, str]:
    result_type = str(item.get("type", ""))
    label = str(item.get("label", ""))
    if context == "wildcard":
        type_group = {"wildcard": 0, "tag": 1}.get(result_type, 2)
    else:
        type_group = {"tag": 0, "wildcard": 1}.get(result_type, 2)

    if result_type == "tag":
        match_tier = int(item.get("matchTier", 99))
        priority_sort = 0 if item.get("priorityClass") else 1
        count_sort = -int(item.get("count", 0))
        return (type_group, priority_sort, match_tier, count_sort, len(label), label.lower())

    match_tier = int(item.get("matchTier", 99))
    segment_index = int(item.get("segmentIndex", 99))
    depth = int(item.get("depth", 99))
    return (type_group, match_tier, segment_index, depth, len(label), str(item.get("id", label)).lower())


def expand_wildcards(
    template_text: str,
    *,
    seed: int = 0,
    max_depth: int = MAX_EXPANSION_DEPTH,
    weight_mode: WeightMode = "count",
) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    records, scan_diagnostics = wildcard_map()
    diagnostics = ExpansionDiagnostics(scan_diagnostics.copy())
    context = ExpansionContext()
    result = _expand_text(template_text, records, rng, diagnostics, [], max_depth, weight_mode, context)
    return (_unescape(result), diagnostics.messages)


def expand_wildcards_preserving_json(
    template_text: str,
    *,
    seed: int = 0,
    max_depth: int = MAX_EXPANSION_DEPTH,
    weight_mode: WeightMode = "count",
) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    records, scan_diagnostics = wildcard_map()
    diagnostics = ExpansionDiagnostics(scan_diagnostics.copy())
    context = ExpansionContext()

    try:
        parsed = json.loads(template_text)
    except json.JSONDecodeError:
        result = _expand_text(template_text, records, rng, diagnostics, [], max_depth, weight_mode, context)
        return (_unescape(result), diagnostics.messages)

    expanded = _expand_json_value(parsed, records, rng, diagnostics, max_depth, weight_mode, context)
    return (json.dumps(expanded, ensure_ascii=False, indent=2), diagnostics.messages)


def _expand_json_value(
    value: Any,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    max_depth: int,
    weight_mode: WeightMode,
    context: ExpansionContext,
) -> Any:
    if isinstance(value, str):
        return _unescape(_expand_text(value, records, rng, diagnostics, [], max_depth, weight_mode, context))
    if isinstance(value, list):
        return [_expand_json_value(item, records, rng, diagnostics, max_depth, weight_mode, context) for item in value]
    if isinstance(value, dict):
        return {
            key: _expand_json_value(item, records, rng, diagnostics, max_depth, weight_mode, context)
            for key, item in value.items()
        }
    return value


def _normalize_search_query(query: str) -> str:
    query = query.strip()
    if query.startswith("__"):
        query = query[2:]
    if query.endswith("__"):
        query = query[:-2]
    return query


def normalize_wildcard_id(value: str) -> str:
    value = value.replace(os.sep, "/").replace("\\", "/")
    return "/".join(part.strip().replace(" ", "_").lower() for part in value.split("/") if part.strip())


def display_wildcard_label(wildcard_id: str) -> str:
    return wildcard_id.rsplit("/", 1)[-1].replace("_", " ")


def _sort_tree(node: dict[str, Any]) -> dict[str, Any]:
    children = node.get("children")
    if isinstance(children, dict):
        node["children"] = [
            _sort_tree(child)
            for _key, child in sorted(
                children.items(),
                key=lambda item: (item[1].get("type") != "directory", item[1].get("label", item[0])),
            )
        ]
    return node


def _read_wildcard_tags(path: str) -> list[WildcardTag]:
    tags: list[WildcardTag] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            weight, value = _parse_weighted_text(text)
            tags.append(WildcardTag(text=value, weight=weight, line_number=line_number))
    return tags


def _read_tag_pool_wildcard_tags(path: str) -> list[WildcardTag]:
    tags: list[WildcardTag] = []
    for index, (tag, count) in enumerate(read_tag_pool_tsv(path), start=2):
        weight = float(count) if count > 0 else 1.0
        tags.append(WildcardTag(text=display_tag(tag), weight=weight, line_number=index))
    return tags


def _read_entity_wildcard_tags(path: str) -> list[WildcardTag]:
    tags: list[WildcardTag] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for line_number, row in enumerate(csv.DictReader(f, delimiter="\t"), start=2):
            tag = (row.get("tag") or "").strip()
            if not tag:
                continue
            count = _parse_int(row.get("count"), default=0)
            weight = float(count) if count > 0 else 1.0
            tags.append(WildcardTag(text=display_tag(tag), weight=weight, line_number=line_number))
    return tags


def _read_character_entity_wildcard_tags(path: str) -> list[WildcardTag]:
    tags: list[WildcardTag] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for line_number, row in enumerate(csv.DictReader(f, delimiter="\t"), start=2):
            character = (row.get("tag") or "").strip()
            if not character:
                continue
            count = _parse_int(row.get("count"), default=0)
            weight = float(count) if count > 0 else 1.0
            franchise = _primary_franchise(row.get("franchises") or "")
            text = f"{display_tag(franchise)}, {display_tag(character)}" if franchise else display_tag(character)
            tags.append(WildcardTag(text=text, weight=weight, line_number=line_number))
    return tags


def _primary_franchise(franchises: str) -> str:
    return franchises.split(",", 1)[0].strip()


def _character_tag_from_expanded_text(text: str) -> str:
    # __characters__ expands to "franchise, character" when a franchise is known.
    return normalize_tag(text.rsplit(",", 1)[-1].strip())


@lru_cache(maxsize=1)
def _read_character_tag_set() -> set[str]:
    characters: set[str] = set()
    if not os.path.exists(CHARACTERS_ENTITIES_FILE):
        return characters

    with open(CHARACTERS_ENTITIES_FILE, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            character = (row.get("tag") or "").strip()
            if character:
                characters.add(normalize_tag(character))
    return characters


def _character_tag_from_context_text(text: str) -> str | None:
    characters = _read_character_tag_set()
    if not characters:
        return None

    for raw_tag in reversed(re.split(r"[,\n;]+", text)):
        normalized = normalize_tag(raw_tag.strip())
        if normalized in characters:
            return normalized
    return None


@lru_cache(maxsize=1)
def _read_character_related_tags() -> dict[str, list[str]]:
    characters: dict[str, list[str]] = {}
    if not os.path.exists(CHARACTER_TAGS_FILE):
        return characters

    with open(CHARACTER_TAGS_FILE, "r", encoding="utf-8", errors="replace") as f:
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
                characters[normalize_tag(character)] = _split_tag_list(tags)
    return characters


@lru_cache(maxsize=1)
def _read_related_tag_category_index() -> dict[str, tuple[str, int]]:
    category_index: dict[str, tuple[str, int]] = {}
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
            for tag, count in read_tag_pool_tsv(path):
                category_index.setdefault(normalize_tag(tag), (category, count))
    return category_index


def _split_tag_list(text: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for tag in text.replace("\n", ",").split(","):
        tag = tag.strip()
        normalized = normalize_tag(tag)
        if not tag or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(display_tag(tag))
    return tags


def _expand_character_related(
    category: str,
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    context: ExpansionContext,
    weight_mode: WeightMode,
) -> str:
    del rng, weight_mode
    character_tag = context.character_tag or _character_tag_from_context_text(context.emitted_text)
    if not character_tag:
        diagnostics.warn(
            f"Character-related wildcard __character_{category}__ used before __characters__ selected a character"
        )
        return ""
    context.character_tag = character_tag

    related = _read_character_related_tags().get(character_tag, [])
    category_index = _read_related_tag_category_index()
    candidates = [
        tag
        for tag in related
        for candidate_category, _count in [category_index.get(normalize_tag(tag), ("", 0))]
        if candidate_category == category
    ]
    if not candidates:
        diagnostics.warn(f"No {category} related tags found for character: {display_tag(character_tag)}")
        return ""

    return ", ".join(candidates[:CHARACTER_RELATED_MAX_TAGS])


def _parse_int(value: object, *, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _read_wildcard_metadata(path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    directory = os.path.dirname(path)
    dir_meta_path = os.path.join(directory, "_meta.json")
    file_meta_path = os.path.splitext(path)[0] + ".meta.json"
    for meta_path in (dir_meta_path, file_meta_path):
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                metadata.update(loaded)
        except (OSError, json.JSONDecodeError) as e:
            metadata.setdefault("_errors", []).append(f"{os.path.basename(meta_path)}: {e}")
    return metadata


def _parse_weighted_text(text: str) -> tuple[float, str]:
    weight_text, separator, value = text.partition("::")
    if not separator:
        return (1.0, text)
    try:
        weight = float(weight_text.strip())
    except ValueError:
        return (1.0, text)
    return (max(weight, 0.0), value.strip())


def _tag_prompt_category(tag: TagRecord) -> str | None:
    if tag.category == "characters":
        return _category_for_source("tag_entities/characters")
    if tag.category == "copyrights":
        return _category_for_source("tag_entities/franchises")
    if tag.category in prompt_category_source_map():
        return tag.category
    return None


def _category_for_source(source: str) -> str | None:
    for category_id, prompt_category in prompt_category_source_map().items():
        if source in prompt_category.sources:
            return category_id
    return None


def _tag_priority_class(tag: TagRecord, category: str | None) -> str | None:
    if category and tag.category == "characters" and _category_has_source(category, "tag_entities/characters"):
        return "character-priority-match"
    if category and tag.category == "copyrights" and _category_has_source(category, "tag_entities/franchises"):
        return "copyright-priority-match"
    if category and tag.category == category:
        return "category-priority-match"
    return None


def _category_has_source(category: str, source: str) -> bool:
    prompt_category = prompt_category_source_map().get(category)
    return prompt_category is not None and source in prompt_category.sources


def _tag_match_tier(tag: TagRecord, normalized_query: str) -> int | None:
    haystack = tag.normalized.lower()
    if haystack == normalized_query:
        return 0
    if haystack.startswith(normalized_query):
        return 1
    if any(token.startswith(normalized_query) for token in haystack.split("_")):
        return 2
    if normalized_query in haystack:
        return 3
    return None


def _tag_score(tag: TagRecord, normalized_query: str, category: str | None) -> int | None:
    haystack = tag.normalized.lower()
    if normalized_query not in haystack:
        return None
    score = 500
    if haystack == normalized_query:
        score += 800
    elif haystack.startswith(normalized_query):
        score += 400
    if category and tag.category == category:
        score += 300
    if category and tag.category == "characters" and _category_has_source(category, "tag_entities/characters"):
        score += 350
    if category and tag.category == "copyrights" and _category_has_source(category, "tag_entities/franchises"):
        score += 350
    score -= min(tag.rank, 2000) // 5
    return score


def _wildcard_match(
    wildcard: WildcardRecord,
    normalized_query: str,
    text_query: str,
    category: str | None,
) -> tuple[int, int] | None:
    id_text = wildcard.id
    id_underscore = id_text.replace("/", "_")
    id_space = id_text.replace("/", " ")
    parts = id_text.split("/")
    leaf = parts[-1]
    query_path = normalize_wildcard_id(text_query.replace(" ", "/")) if text_query else ""
    query_variants = [query for query in (query_path, normalized_query) if query]

    for query in query_variants:
        if id_text == query:
            return (0, 0)
        if id_text.startswith(f"{query}/") or id_text.startswith(query):
            return (1, 0)

    for index, part in enumerate(parts):
        if part in query_variants:
            return (2, index)

    for index, part in enumerate(parts):
        if any(part.startswith(query) for query in query_variants):
            return (3, index)

    if any(leaf.startswith(query) for query in query_variants):
        return (4, len(parts) - 1)

    if any(query in haystack for query in query_variants for haystack in (id_text, id_underscore, id_space)):
        return (5, 0)

    metadata_haystacks: list[str] = []
    for key in ("displayName", "description"):
        value = wildcard.metadata.get(key)
        if isinstance(value, str):
            metadata_haystacks.append(value.lower())
    aliases = wildcard.metadata.get("aliases")
    if isinstance(aliases, list):
        metadata_haystacks.extend(str(alias).lower() for alias in aliases)

    normalized_metadata = [normalize_tag(haystack).lower() for haystack in metadata_haystacks]
    if any(normalized_query in haystack for haystack in normalized_metadata) or any(
        text_query and text_query in haystack for haystack in metadata_haystacks
    ):
        return (6, 0)

    if category and _wildcard_matches_category(wildcard, category):
        return (7, 0)

    return None


def _wildcard_matches_category(wildcard: WildcardRecord, category: str) -> bool:
    prompt_category = wildcard.metadata.get("promptCategory")
    if isinstance(prompt_category, str) and prompt_category == category:
        return True
    path = wildcard.id.replace("_", " ")
    return any(part in path for part in category.split("_"))


def _expand_text(
    text: str,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    stack: list[str],
    remaining_depth: int,
    weight_mode: WeightMode,
    context: ExpansionContext,
) -> str:
    if remaining_depth <= 0:
        diagnostics.warn("Maximum wildcard expansion depth reached")
        return "[wildcard depth limit]"

    output: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("__", i) and not _is_escaped(text, i):
            end = _find_unescaped(text, "__", i + 2)
            if end != -1:
                ref = text[i + 2 : end].strip()
                output.append(_expand_ref(ref, records, rng, diagnostics, stack, remaining_depth - 1, weight_mode, context))
                i = end + 2
                continue
        if text[i] == "{" and not _is_escaped(text, i):
            end = _find_matching_brace(text, i)
            if end != -1:
                output.append(_expand_variant(text[i + 1 : end], records, rng, diagnostics, stack, remaining_depth - 1, weight_mode, context))
                i = end + 1
                continue
        output.append(text[i])
        context.emitted_text += text[i]
        i += 1
    return "".join(output)


def _expand_ref(
    ref: str,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    stack: list[str],
    remaining_depth: int,
    weight_mode: WeightMode,
    context: ExpansionContext,
) -> str:
    wildcard_id = normalize_wildcard_id(ref)
    if wildcard_id in {"character_appearance", "character_clothes"}:
        category = "appearance" if wildcard_id == "character_appearance" else "clothes"
        return _expand_character_related(category, rng, diagnostics, context, weight_mode)
    if "*" in wildcard_id:
        candidates = [
            entry
            for record_id, record in records.items()
            if _wildcard_glob_match(wildcard_id, record_id)
            for entry in _expansion_tags(record, weight_mode)
        ]
        source = wildcard_id
    else:
        record = records.get(wildcard_id)
        if record is None:
            diagnostics.warn(f"Missing wildcard: {wildcard_id}")
            return f"[missing wildcard: {wildcard_id}]"
        if wildcard_id in stack:
            diagnostics.warn(f"Cyclic wildcard reference: {' -> '.join([*stack, wildcard_id])}")
            return f"[cyclic wildcard: {wildcard_id}]"
        candidates = _expansion_tags(record, weight_mode)
        source = wildcard_id

    if not candidates:
        diagnostics.warn(f"Empty wildcard: {source}")
        return f"[empty wildcard: {source}]"

    entry = _weighted_choice(candidates, rng)
    if wildcard_id == "characters":
        context.character_tag = _character_tag_from_expanded_text(entry.text)
    next_stack = stack if "*" in wildcard_id else [*stack, source]
    return _expand_text(entry.text, records, rng, diagnostics, next_stack, remaining_depth, weight_mode, context)


def _expand_variant(
    body: str,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    stack: list[str],
    remaining_depth: int,
    weight_mode: WeightMode,
    context: ExpansionContext,
) -> str:
    parts = _split_top_level(body, "$$")
    count = 1
    separator = ", "
    options_text = body

    if len(parts) >= 2 and _looks_like_count(parts[0].strip()):
        count = _pick_count(parts[0].strip(), rng)
        if len(parts) >= 3:
            separator = parts[1]
            options_text = "$$".join(parts[2:])
        else:
            options_text = parts[1]

    options = [_variant_option(option) for option in _split_top_level(options_text, "|") if option.strip()]
    if not options:
        return ""

    selected: list[str] = []
    remaining = options.copy()
    for _ in range(min(count, len(remaining))):
        option = _weighted_choice(remaining, rng)
        remaining.remove(option)
        selected.append(_expand_text(option.text, records, rng, diagnostics, stack, remaining_depth, weight_mode, context))
    return separator.join(selected)


def _variant_option(text: str) -> WildcardTag:
    weight, value = _parse_weighted_text(text.strip())
    return WildcardTag(text=value, weight=weight, line_number=0)


def _expansion_tags(record: WildcardRecord, weight_mode: WeightMode) -> list[WildcardTag]:
    if record.metadata.get("sourceType") not in {"tag_pool", "tag_entity"}:
        return list(record.tags)
    return [
        WildcardTag(
            text=tag.text,
            weight=_transform_tag_pool_weight(tag.weight, weight_mode),
            line_number=tag.line_number,
        )
        for tag in record.tags
    ]


def _transform_tag_pool_weight(weight: float, weight_mode: WeightMode) -> float:
    if weight_mode == "random":
        return 1.0
    if weight <= 0:
        return 1.0
    if weight_mode == "log":
        return math.log1p(weight)
    if weight_mode == "sqrt":
        return math.sqrt(weight)
    return weight


def _weighted_choice(choices: list[WildcardTag], rng: random.Random) -> WildcardTag:
    weights = [choice.weight for choice in choices]
    if sum(weights) <= 0:
        return rng.choice(choices)
    return rng.choices(choices, weights=weights, k=1)[0]


def _looks_like_count(text: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:-\d+)?", text))


def _pick_count(text: str, rng: random.Random) -> int:
    if "-" not in text:
        return max(0, int(text))
    low_text, high_text = text.split("-", 1)
    low = max(0, int(low_text))
    high = max(low, int(high_text))
    return rng.randint(low, high)


def _wildcard_glob_match(pattern: str, wildcard_id: str) -> bool:
    regex = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            regex.append(".*")
            i += 2
            continue
        if char == "*":
            regex.append("[^/]*")
        else:
            regex.append(re.escape(char))
        i += 1
    return re.fullmatch("".join(regex), wildcard_id) is not None


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    i = 0
    while i < len(text):
        if _is_escaped(text, i):
            i += 1
        elif text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(separator, i):
            parts.append(text[start:i])
            i += len(separator)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return parts


def _find_unescaped(text: str, needle: str, start: int) -> int:
    i = start
    while True:
        i = text.find(needle, i)
        if i == -1 or not _is_escaped(text, i):
            return i
        i += len(needle)


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    i = start
    while i < len(text):
        if _is_escaped(text, i):
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    i = index - 1
    while i >= 0 and text[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1


def _unescape(text: str) -> str:
    return re.sub(r"\\([{}|_])", r"\1", text)
