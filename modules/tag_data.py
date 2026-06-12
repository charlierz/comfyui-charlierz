from __future__ import annotations

import os

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_POOLS_DIR = os.path.join(DATA_DIR, "tag_pools")
TAG_ENTITIES_DIR = os.path.join(DATA_DIR, "tag_entities")
TAG_RELATIONSHIPS_DIR = os.path.join(DATA_DIR, "tag_relationships")

# Map tag_pools top-level directories to prompt categories.
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


def normalize_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_")


def display_tag(tag: str) -> str:
    return tag.strip().replace("_", " ")


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
