#!/usr/bin/env python3
"""Generate curated TSV tag pools from the local wildcard seed files.

This is a migration/bootstrapping helper. It preserves the current source wildcard
shape under data/tag_pools/danbooru/ and writes one TSV per leaf pool.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

REPO_DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_DATA_DIR / "wildcards"
DEFAULT_OUTPUT = REPO_DATA_DIR / "tag_pools"
DEFAULT_DANBOORU_TAGS = REPO_DATA_DIR / "danbooru_tags.csv"

TSV_HEADER = ("tag", "count", "related")
SKIP_FILES = {"prompts.txt"}
BAD_TAG_CHARS = re.compile(r"[,{}|$]")
BAD_TAG_TOKENS = ("__", "\t")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--danbooru-tags", type=Path, default=DEFAULT_DANBOORU_TAGS)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove the output directory before generating files.",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    counts = read_danbooru_counts(args.danbooru_tags)

    if args.force and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    stats = Stats()
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if path.name in SKIP_FILES:
            stats.skipped_files += 1
            continue
        if path.suffix.lower() in {".yaml", ".yml"}:
            convert_yaml(path, output, counts, stats)
        elif path.suffix.lower() == ".txt":
            convert_txt(path, output, counts, stats)
        else:
            stats.skipped_files += 1

    print(f"Wrote {stats.files_written} TSV files to {output}")
    print(f"Rows written: {stats.rows_written}")
    print(f"Rows skipped as non-simple: {stats.rows_skipped}")
    print(f"Files skipped: {stats.skipped_files}")
    print(f"Rows with Danbooru counts: {stats.rows_with_count}")


class Stats:
    files_written = 0
    rows_written = 0
    rows_skipped = 0
    skipped_files = 0
    rows_with_count = 0


def read_danbooru_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}

    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tag = (row.get("tag") or "").strip()
            count_text = (row.get("count") or "").strip()
            if not tag or not count_text:
                continue
            try:
                counts[normalize_tag_id(tag)] = int(count_text)
            except ValueError:
                continue
    return counts


def convert_txt(path: Path, output: Path, counts: dict[str, int], stats: Stats) -> None:
    tags = read_simple_lines(path, stats)
    if not tags:
        return
    write_pool(output / f"{safe_path_part(path.stem)}.tsv", tags, counts, stats)


def convert_yaml(path: Path, output: Path, counts: dict[str, int], stats: Stats) -> None:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        loaded = yaml.safe_load(f)

    if loaded is None:
        return

    base = [safe_path_part(path.stem)]
    # Source YAML files are usually shaped as {file_stem: {...}}. Avoid
    # duplicating that root in the output path.
    if isinstance(loaded, dict) and len(loaded) == 1:
        key, value = next(iter(loaded.items()))
        if safe_path_part(str(key)) == safe_path_part(path.stem):
            loaded = value

    write_yaml_node(loaded, output, base, counts, stats)


def write_yaml_node(
    node: Any,
    output: Path,
    parts: list[str],
    counts: dict[str, int],
    stats: Stats,
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            write_yaml_node(value, output, [*parts, safe_path_part(str(key))], counts, stats)
        return

    if isinstance(node, list):
        tags: list[str] = []
        for item in node:
            if isinstance(item, str):
                tag = clean_tag(item)
                if is_simple_tag(tag):
                    tags.append(tag)
                else:
                    stats.rows_skipped += 1
            else:
                stats.rows_skipped += 1
        if tags:
            write_pool(output.joinpath(*parts).with_suffix(".tsv"), tags, counts, stats)
        return

    stats.rows_skipped += 1


def read_simple_lines(path: Path, stats: Stats) -> list[str]:
    tags: list[str] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = clean_tag(raw_line)
            if not line or line.startswith("#"):
                continue
            if is_simple_tag(line):
                tags.append(line)
            else:
                stats.rows_skipped += 1
    return tags


def write_pool(path: Path, tags: list[str], counts: dict[str, int], stats: Stats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_tags = sort_tags_by_count(list(dict.fromkeys(tags)), counts)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(TSV_HEADER)
        for tag in sorted_tags:
            count = counts.get(normalize_tag_id(tag))
            if count is not None:
                stats.rows_with_count += 1
            writer.writerow((tag, "" if count is None else str(count), ""))
            stats.rows_written += 1
    stats.files_written += 1


def sort_tags_by_count(tags: list[str], counts: dict[str, int]) -> list[str]:
    indexed_tags = list(enumerate(tags))
    indexed_tags.sort(
        key=lambda item: (
            counts.get(normalize_tag_id(item[1])) is None,
            -(counts.get(normalize_tag_id(item[1])) or 0),
            item[0],
        )
    )
    return [tag for _index, tag in indexed_tags]


def clean_tag(value: str) -> str:
    return " ".join(value.strip().split())


def is_simple_tag(tag: str) -> bool:
    if not tag:
        return False
    if BAD_TAG_CHARS.search(tag):
        return False
    return not any(token in tag for token in BAD_TAG_TOKENS)


def normalize_tag_id(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_")


def safe_path_part(value: str) -> str:
    return clean_tag(value).replace("_", " ").lower().strip("./")


if __name__ == "__main__":
    main()
