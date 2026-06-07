from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_CATEGORIES_DIR = os.path.join(DATA_DIR, "tag_categories")
WILDCARDS_DIR = os.path.join(DATA_DIR, "wildcards")
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

MAX_EXPANSION_DEPTH = 32


@dataclass(frozen=True)
class TagRecord:
    label: str
    normalized: str
    category: str
    rank: int


@dataclass(frozen=True)
class WildcardEntry:
    text: str
    weight: float
    line_number: int


@dataclass(frozen=True)
class WildcardRecord:
    id: str
    path: str
    label: str
    entries: tuple[WildcardEntry, ...]
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

    for category, filename in CATEGORY_FILES.items():
        path = os.path.join(TAG_CATEGORIES_DIR, filename)
        for rank, tag in enumerate(_read_tag_file(path)):
            normalized = normalize_tag(tag)
            if normalized in seen:
                continue
            seen.add(normalized)
            records.append(TagRecord(label=display_tag(tag), normalized=normalized, category=category, rank=rank))

    for category, path in (("general", GENERAL_TAGS_FILE), ("copyrights", COPYRIGHT_TAGS_FILE)):
        for rank, tag in enumerate(_read_tag_file(path)):
            normalized = normalize_tag(tag)
            if normalized in seen:
                continue
            seen.add(normalized)
            records.append(TagRecord(label=display_tag(tag), normalized=normalized, category=category, rank=rank))

    if os.path.exists(CHARACTERS_FILE):
        with open(CHARACTERS_FILE, "r", encoding="utf-8") as f:
            for rank, line in enumerate(f):
                tag = line.partition("\t")[0].strip()
                normalized = normalize_tag(tag)
                if not tag or normalized in seen:
                    continue
                seen.add(normalized)
                records.append(TagRecord(label=display_tag(tag), normalized=normalized, category="characters", rank=rank))

    return records


@lru_cache(maxsize=1)
def tag_lookup() -> dict[str, TagRecord]:
    return {record.normalized: record for record in read_tag_records()}


def scan_wildcards() -> tuple[list[WildcardRecord], list[str]]:
    if not os.path.isdir(WILDCARDS_DIR):
        return ([], [])

    diagnostics: list[str] = []
    records: list[WildcardRecord] = []
    seen_paths_by_id: dict[str, str] = {}

    for root, _dirs, files in os.walk(WILDCARDS_DIR):
        for filename in sorted(files):
            if not filename.endswith(".txt") or filename.endswith(".meta.json"):
                continue

            path = os.path.join(root, filename)
            rel_path = os.path.relpath(path, WILDCARDS_DIR)
            wildcard_id = normalize_wildcard_id(os.path.splitext(rel_path)[0])
            duplicate = wildcard_id in seen_paths_by_id
            if duplicate:
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
                    entries=tuple(_read_wildcard_entries(path)),
                    metadata=_read_wildcard_metadata(path),
                    duplicate=duplicate,
                )
            )

    return (records, diagnostics)


def wildcard_map() -> tuple[dict[str, WildcardRecord], list[str]]:
    records, diagnostics = scan_wildcards()
    return ({record.id: record for record in records}, diagnostics)


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
        "entryCount": len(record.entries),
        "entries": [
            {"text": entry.text, "weight": entry.weight, "lineNumber": entry.line_number}
            for entry in record.entries
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
        children[parts[-1]] = {
            "type": "wildcard",
            "id": record.id,
            "label": record.metadata.get("displayName") or record.label,
            "insertText": f"__{record.id}__",
            "path": record.path,
            "entryCount": len(record.entries),
        }

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

    requested = types or {"tag", "wildcard", "wildcard_entry"}
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
                    "score": score + (1000 if context == "prompt" else 0),
                }
            )

    records, diagnostics = scan_wildcards()
    for wildcard in records:
        if "wildcard" in requested:
            score = _wildcard_score(wildcard, normalized_query, text_query, category)
            if score is not None:
                results.append(
                    {
                        "type": "wildcard",
                        "id": wildcard.id,
                        "label": wildcard.metadata.get("displayName") or wildcard.label,
                        "insertText": f"__{wildcard.id}__",
                        "path": wildcard.path,
                        "score": score + (1500 if context == "wildcard" else 0),
                    }
                )

        if "wildcard_entry" in requested and len(normalized_query) >= 2:
            for entry in wildcard.entries:
                if normalized_query not in normalize_tag(entry.text).lower():
                    continue
                results.append(
                    {
                        "type": "wildcard_entry",
                        "label": entry.text,
                        "insertText": entry.text,
                        "wildcardId": wildcard.id,
                        "wildcardLabel": wildcard.metadata.get("displayName") or wildcard.label,
                        "score": 200 + (200 if normalize_tag(entry.text).lower().startswith(normalized_query) else 0),
                    }
                )

    results.sort(key=lambda item: (-int(item["score"]), str(item.get("label", "")).lower()))
    return {"results": [{k: v for k, v in item.items() if k != "score"} for item in results[:limit]], "diagnostics": diagnostics}


def expand_wildcards(template_text: str, *, seed: int = 0, max_depth: int = MAX_EXPANSION_DEPTH) -> tuple[str, list[str]]:
    rng = random.Random(seed)
    records, scan_diagnostics = wildcard_map()
    diagnostics = ExpansionDiagnostics(scan_diagnostics.copy())
    result = _expand_text(template_text, records, rng, diagnostics, [], max_depth)
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


def _read_tag_file(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [tag.strip() for tag in f.read().replace("\n", ",").split(",") if tag.strip()]


def _read_wildcard_entries(path: str) -> list[WildcardEntry]:
    entries: list[WildcardEntry] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            weight, value = _parse_weighted_text(text)
            entries.append(WildcardEntry(text=value, weight=weight, line_number=line_number))
    return entries


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
    score -= min(tag.rank, 1000) // 10
    return score


def _wildcard_score(
    wildcard: WildcardRecord,
    normalized_query: str,
    text_query: str,
    category: str | None,
) -> int | None:
    haystacks = [
        wildcard.id,
        wildcard.id.replace("/", "_"),
        wildcard.id.replace("/", " "),
        wildcard.label.lower(),
        wildcard.path.lower(),
    ]
    for key in ("displayName", "description"):
        value = wildcard.metadata.get(key)
        if isinstance(value, str):
            haystacks.append(value.lower())
    aliases = wildcard.metadata.get("aliases")
    if isinstance(aliases, list):
        haystacks.extend(str(alias).lower() for alias in aliases)

    normalized_haystacks = [normalize_tag(haystack).lower() for haystack in haystacks]
    if not any(normalized_query in haystack for haystack in normalized_haystacks) and not any(
        text_query and text_query in haystack for haystack in haystacks
    ):
        return None

    score = 300
    if wildcard.id == normalized_query:
        score += 800
    elif wildcard.id.startswith(normalized_query):
        score += 400
    if category and _wildcard_matches_category(wildcard, category):
        score += 150
    return score


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
                output.append(_expand_ref(ref, records, rng, diagnostics, stack, remaining_depth - 1))
                i = end + 2
                continue
        if text[i] == "{" and not _is_escaped(text, i):
            end = _find_matching_brace(text, i)
            if end != -1:
                output.append(_expand_variant(text[i + 1 : end], records, rng, diagnostics, stack, remaining_depth - 1))
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
) -> str:
    wildcard_id = normalize_wildcard_id(ref)
    if "*" in wildcard_id:
        candidates = [entry for record_id, record in records.items() if _wildcard_glob_match(wildcard_id, record_id) for entry in record.entries]
        source = wildcard_id
    else:
        record = records.get(wildcard_id)
        if record is None:
            diagnostics.warn(f"Missing wildcard: {wildcard_id}")
            return f"[missing wildcard: {wildcard_id}]"
        if wildcard_id in stack:
            diagnostics.warn(f"Cyclic wildcard reference: {' -> '.join([*stack, wildcard_id])}")
            return f"[cyclic wildcard: {wildcard_id}]"
        candidates = list(record.entries)
        source = wildcard_id

    if not candidates:
        diagnostics.warn(f"Empty wildcard: {source}")
        return f"[empty wildcard: {source}]"

    entry = _weighted_choice(candidates, rng)
    next_stack = stack if "*" in wildcard_id else [*stack, wildcard_id]
    return _expand_text(entry.text, records, rng, diagnostics, next_stack, remaining_depth)


def _expand_variant(
    body: str,
    records: dict[str, WildcardRecord],
    rng: random.Random,
    diagnostics: ExpansionDiagnostics,
    stack: list[str],
    remaining_depth: int,
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
        selected.append(_expand_text(option.text, records, rng, diagnostics, stack, remaining_depth))
    return separator.join(selected)


def _variant_option(text: str) -> WildcardEntry:
    weight, value = _parse_weighted_text(text.strip())
    return WildcardEntry(text=value, weight=weight, line_number=0)


def _weighted_choice(entries: list[WildcardEntry], rng: random.Random) -> WildcardEntry:
    weights = [entry.weight for entry in entries]
    if sum(weights) <= 0:
        return rng.choice(entries)
    return rng.choices(entries, weights=weights, k=1)[0]


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
