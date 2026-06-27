from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_POOLS_DIR = os.path.join(DATA_DIR, "tag_pools")
TAG_ENTITIES_DIR = os.path.join(DATA_DIR, "tag_entities")
TAG_RELATIONSHIPS_DIR = os.path.join(DATA_DIR, "tag_relationships")
PROMPT_CATEGORIES_FILE = os.path.join(DATA_DIR, "prompt_categories.json")
CHARACTERS_ENTITIES_FILE = os.path.join(TAG_ENTITIES_DIR, "characters.tsv")
FRANCHISES_FILE = os.path.join(TAG_ENTITIES_DIR, "franchises.tsv")

PROMPT_CATEGORY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_WEIGHT_SUFFIX_PATTERN = re.compile(r":[0-9]+(?:\.[0-9]+)?$")
_PRESERVE_UNDERSCORE_TAG_PATTERN = re.compile(r"^score_\d+(?:_up)?$")
ENTITY_SOURCE_FILES = {
    "tag_entities/characters": CHARACTERS_ENTITIES_FILE,
    "tag_entities/franchises": FRANCHISES_FILE,
}


@dataclass(frozen=True)
class PromptCategory:
    id: str
    sources: tuple[str, ...]

    @property
    def tag_pool_sources(self) -> tuple[str, ...]:
        return tuple(source.removeprefix("tag_pools/") for source in self.sources if source.startswith("tag_pools/"))

    @property
    def entity_sources(self) -> tuple[str, ...]:
        return tuple(source for source in self.sources if source.startswith("tag_entities/"))


@lru_cache(maxsize=1)
def read_prompt_categories() -> tuple[PromptCategory, ...]:
    with open(PROMPT_CATEGORIES_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict) or not isinstance(raw.get("categories"), list):
        raise ValueError("prompt_categories.json must contain a categories array")

    categories: list[PromptCategory] = []
    seen_ids: set[str] = set()
    seen_tag_pools: dict[str, str] = {}
    for index, item in enumerate(raw["categories"]):
        if not isinstance(item, dict):
            raise ValueError(f"Category #{index + 1} must be an object")
        category_id = item.get("id")
        sources = item.get("sources")
        if not isinstance(category_id, str) or not PROMPT_CATEGORY_ID_PATTERN.fullmatch(category_id):
            raise ValueError(f"Category #{index + 1} has invalid id: {category_id!r}")
        if category_id in seen_ids:
            raise ValueError(f"Duplicate prompt category id: {category_id}")
        if not isinstance(sources, list) or not sources or not all(isinstance(source, str) and source for source in sources):
            raise ValueError(f"Category {category_id} must define a non-empty sources array")

        normalized_sources: list[str] = []
        for source in sources:
            source = source.strip().replace(os.sep, "/")
            if source.startswith("tag_pools/"):
                pool = source.removeprefix("tag_pools/").strip("/")
                if not pool or "/" in pool:
                    raise ValueError(f"Category {category_id} has invalid tag pool source: {source}")
                previous = seen_tag_pools.get(pool)
                if previous is not None:
                    raise ValueError(f"Tag pool source tag_pools/{pool} is used by both {previous} and {category_id}")
                seen_tag_pools[pool] = category_id
                path = os.path.join(TAG_POOLS_DIR, pool)
                if not os.path.isdir(path):
                    print(f"[comfyui-charlierz] Prompt category {category_id} source missing: {source}")
                normalized_sources.append(f"tag_pools/{pool}")
            elif source in ENTITY_SOURCE_FILES:
                if not os.path.exists(ENTITY_SOURCE_FILES[source]):
                    print(f"[comfyui-charlierz] Prompt category {category_id} source missing: {source}")
                normalized_sources.append(source)
            else:
                raise ValueError(f"Category {category_id} has unknown source: {source}")

        seen_ids.add(category_id)
        categories.append(PromptCategory(category_id, tuple(normalized_sources)))

    return tuple(categories)


def prompt_category_ids() -> tuple[str, ...]:
    return tuple(category.id for category in read_prompt_categories())


def prompt_category_source_map() -> dict[str, PromptCategory]:
    return {category.id: category for category in read_prompt_categories()}


def tag_pool_category_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for category in read_prompt_categories():
        for pool in category.tag_pool_sources:
            mapping[pool] = category.id
    return mapping


def prompt_categories_json() -> dict[str, Any]:
    return {"categories": [{"id": category.id, "sources": list(category.sources)} for category in read_prompt_categories()]}


def clear_prompt_category_cache() -> None:
    read_prompt_categories.cache_clear()


def _is_paren_enclosed(text: str) -> bool:
    """True when an outer ``(...)`` pair wraps the entire string.

    Canonical Danbooru tags never start with ``(``, so a balanced outer pair
    enclosing the whole tag reliably identifies prompt emphasis/weight syntax
    rather than a name such as ``pearl (gemstone)``.
    """
    if not text.startswith("(") or not text.endswith(")"):
        return False
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


def strip_prompt_weight(tag: str) -> str:
    """Remove prompt emphasis/weight syntax from ``tag``.

    Handles ``(tag)``, ``((tag))``, ``(tag:1.3)`` and nested combinations such
    as ``(((tag:1.2)))``. Name parens that are part of a canonical tag
    (``pearl (gemstone)``) are preserved because they do not enclose the whole
    string. The trailing ``:weight`` is only stripped inside a paren group, so
    emoticon tags like ``:3`` are left untouched.
    """
    text = tag.strip()
    while _is_paren_enclosed(text):
        inner = text[1:-1].strip()
        match = _WEIGHT_SUFFIX_PATTERN.search(inner)
        if match:
            inner = inner[: match.start()].rstrip()
        text = inner
    return text


def normalize_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_")


def display_tag(tag: str) -> str:
    stripped = tag.strip()
    if _PRESERVE_UNDERSCORE_TAG_PATTERN.fullmatch(stripped):
        return stripped
    return stripped.replace("_", " ")


def read_tag_pool_tsv(path: str) -> list[tuple[str, int]]:
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


def read_tsv_keys(path: str) -> list[str]:
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
