from __future__ import annotations

import json
import math
import os
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_POOLS_DIR = os.path.join(DATA_DIR, "tag_pools")
TAG_ENTITIES_DIR = os.path.join(DATA_DIR, "tag_entities")
WILDCARDS_DIR = os.path.join(DATA_DIR, "wildcards")
CHARACTERS_ENTITIES_FILE = os.path.join(TAG_ENTITIES_DIR, "characters.tsv")
FRANCHISES_FILE = os.path.join(TAG_ENTITIES_DIR, "franchises.tsv")

# Map tag_pools top-level directories to prompt categories
POOL_CATEGORY_MAP = {
    "body": "appearance_anatomy",
    "camera": "scene_background",
    "clothes": "clothing_accessories",
    "face": "expressions",
    "pose": "actions_poses",
    "scene": "scene_background",
    "style": "style_quality",
    "visual": "style_quality",
}

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


@dataclass
class ExpansionDiagnostics:
    messages: list[str]

    def warn(self, message: str) -> None:
        self.messages.append(message)
        print(f"[charlierz wildcard] {message}")


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
                category = POOL_CATEGORY_MAP.get(top_dir)
                if category is None:
                    continue

                tag_rows = _read_tag_pool_tsv(path)
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
        franchise_entries = _read_tag_pool_tsv(FRANCHISES_FILE)
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
        character_entries = _read_tag_pool_tsv(CHARACTERS_ENTITIES_FILE)
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
def tag_lookup() -> dict[str, TagRecord]:
    return {record.normalized: record for record in read_tag_records()}


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
                            "promptCategory": POOL_CATEGORY_MAP.get(wildcard_id.split("/", 1)[0]),
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
                        "promptCategory": POOL_CATEGORY_MAP.get(directory_id.split("/", 1)[0]),
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
    read_tag_records.cache_clear()
    tag_lookup.cache_clear()
    scan_wildcards.cache_clear()
    wildcard_map.cache_clear()


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
        }
        if isinstance(existing, dict) and existing.get("type") == "directory":
            existing.update({k: v for k, v in wildcard_node.items() if k != "type"})
        else:
            children[parts[-1]] = wildcard_node

    return {"tree": _sort_tree(tree), "diagnostics": diagnostics}


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
    result = _expand_text(template_text, records, rng, diagnostics, [], max_depth, weight_mode)
    return (_unescape(result), diagnostics.messages)


def normalize_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_")


def _normalize_search_query(query: str) -> str:
    query = query.strip()
    if query.startswith("__"):
        query = query[2:]
    if query.endswith("__"):
        query = query[:-2]
    return query


def display_tag(tag: str) -> str:
    return tag.strip().replace("_", " ")


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


def _read_tag_pool_tsv(path: str) -> list[tuple[str, int]]:
    """Read a tag pool TSV file, returning (tag, count) tuples."""
    rows: list[tuple[str, int]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f):
            if line_number == 0 and line.startswith("tag\t"):
                continue  # skip header
            parts = line.rstrip("\n").split("\t", 1)
            if not parts or not parts[0].strip():
                continue
            tag = parts[0].strip()
            count = 0
            if len(parts) > 1:
                try:
                    count = int(parts[1].strip())
                except (ValueError, TypeError):
                    pass
            rows.append((tag, count))
    return rows


def _read_tsv_keys(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    keys: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f):
            key = line.partition("\t")[0].strip()
            if not key or (line_number == 0 and key == "tag"):
                continue
            keys.append(key)
    return keys


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
    for index, (tag, count) in enumerate(_read_tag_pool_tsv(path), start=2):
        weight = float(count) if count > 0 else 1.0
        tags.append(WildcardTag(text=display_tag(tag), weight=weight, line_number=index))
    return tags


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


def _tag_priority_class(tag: TagRecord, category: str | None) -> str | None:
    if category == "themes_roles" and tag.category == "characters":
        return "character-priority-match"
    if category == "themes_roles" and tag.category == "copyrights":
        return "copyright-priority-match"
    if category and tag.category == category:
        return "category-priority-match"
    return None


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
    if category == "themes_roles" and tag.category in {"characters", "copyrights"}:
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
                output.append(_expand_ref(ref, records, rng, diagnostics, stack, remaining_depth - 1, weight_mode))
                i = end + 2
                continue
        if text[i] == "{" and not _is_escaped(text, i):
            end = _find_matching_brace(text, i)
            if end != -1:
                output.append(_expand_variant(text[i + 1 : end], records, rng, diagnostics, stack, remaining_depth - 1, weight_mode))
                i = end + 1
                continue
        output.append(text[i])
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
) -> str:
    wildcard_id = normalize_wildcard_id(ref)
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
    next_stack = stack if "*" in wildcard_id else [*stack, source]
    return _expand_text(entry.text, records, rng, diagnostics, next_stack, remaining_depth, weight_mode)


def _expand_variant(
    body: str,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    stack: list[str],
    remaining_depth: int,
    weight_mode: WeightMode,
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
        selected.append(_expand_text(option.text, records, rng, diagnostics, stack, remaining_depth, weight_mode))
    return separator.join(selected)


def _variant_option(text: str) -> WildcardTag:
    weight, value = _parse_weighted_text(text.strip())
    return WildcardTag(text=value, weight=weight, line_number=0)


def _expansion_tags(record: WildcardRecord, weight_mode: WeightMode) -> list[WildcardTag]:
    if record.metadata.get("sourceType") != "tag_pool":
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
