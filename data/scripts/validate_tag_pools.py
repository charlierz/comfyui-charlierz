#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
DANBOORU_TAGS_CSV = DATA_DIR / "danbooru_tags.csv"
TAG_POOLS_DIR = DATA_DIR / "tag_pools"
TAG_ENTITIES_DIR = DATA_DIR / "tag_entities"
CHARACTERS_TSV = TAG_ENTITIES_DIR / "characters.tsv"
FRANCHISES_TSV = TAG_ENTITIES_DIR / "franchises.tsv"


@dataclass(frozen=True)
class SourceTag:
    count: int
    category: str


def canonical_tag(tag: str) -> str:
    return tag.strip().replace(" ", "_")


def display_tag(canonical: str) -> str:
    return canonical.replace("_", " ")


def read_danbooru_tags(path: Path) -> dict[str, SourceTag]:
    tags: dict[str, SourceTag] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            tag = canonical_tag(row.get("tag") or "")
            if not tag:
                continue
            try:
                count = int(row.get("count") or 0)
            except ValueError:
                count = 0
            tags[tag] = SourceTag(count=count, category=row.get("category") or "")
    return tags


def read_tsv_tags(path: Path) -> list[str]:
    tags: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f):
            tag = line.rstrip("\n").split("\t", 1)[0].strip()
            if not tag or (line_number == 0 and tag == "tag"):
                continue
            tags.append(tag)
    return tags


def collect_accounted_tags(data_dir: Path) -> tuple[dict[str, list[Path]], list[tuple[Path, str]]]:
    locations: dict[str, list[Path]] = defaultdict(list)
    suspicious: list[tuple[Path, str]] = []

    for path in sorted((data_dir / "tag_pools").rglob("*.tsv")):
        for tag in read_tsv_tags(path):
            if _looks_suspicious_tsv_tag(tag):
                suspicious.append((path, tag))
            locations[canonical_tag(tag)].append(path.relative_to(data_dir))

    for path in (data_dir / "tag_entities" / "characters.tsv", data_dir / "tag_entities" / "franchises.tsv"):
        if not path.exists():
            continue
        for tag in read_tsv_tags(path):
            if _looks_suspicious_tsv_tag(tag):
                suspicious.append((path, tag))
            locations[canonical_tag(tag)].append(path.relative_to(data_dir))

    return dict(locations), suspicious


def _looks_suspicious_tsv_tag(tag: str) -> bool:
    # TSV files are not CSV-quoted. Leading/trailing quotes usually indicate a
    # CSV-escaped Danbooru tag was pasted without unescaping quotes first.
    return len(tag) >= 2 and tag.startswith('"') and tag.endswith('"')


def print_top_missing(missing: list[str], danbooru_tags: dict[str, SourceTag], limit: int) -> None:
    for tag in sorted(missing, key=lambda item: (-danbooru_tags[item].count, item))[:limit]:
        source = danbooru_tags[tag]
        print(f"  {display_tag(tag)}\tcount={source.count}\tcategory={source.category}")


def print_extra(extra: list[str], locations: dict[str, list[Path]], limit: int) -> None:
    for tag in sorted(extra)[:limit]:
        paths = ", ".join(str(path) for path in locations[tag][:3])
        suffix = " ..." if len(locations[tag]) > 3 else ""
        print(f"  {display_tag(tag)}\t{paths}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated tag pools/entities against data/danbooru_tags.csv.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Data directory containing tag_pools/ and danbooru_tags.csv")
    parser.add_argument("--top", type=int, default=50, help="Number of missing/extra examples to print")
    parser.add_argument(
        "--strict-extra",
        action="store_true",
        help="Fail when curated tags are not present in danbooru_tags.csv. By default extras are reported only.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    danbooru_tags_csv = data_dir / "danbooru_tags.csv"
    if not danbooru_tags_csv.exists():
        print(f"Missing source CSV: {danbooru_tags_csv}", file=sys.stderr)
        return 2

    danbooru_tags = read_danbooru_tags(danbooru_tags_csv)
    locations, suspicious = collect_accounted_tags(data_dir)

    missing = [tag for tag in danbooru_tags if tag not in locations]
    extra = [tag for tag in locations if tag not in danbooru_tags]
    duplicates = {tag: paths for tag, paths in locations.items() if len(paths) > 1}

    print(f"Danbooru tags: {len(danbooru_tags)}")
    print(f"Accounted tags: {len(locations)}")
    print(f"Missing from pools/entities: {len(missing)}")
    print(f"Extra not in Danbooru CSV: {len(extra)}")
    print(f"Duplicate accounted tags: {len(duplicates)}")
    print(f"Suspicious quoted TSV tags: {len(suspicious)}")

    if missing:
        print(f"\nTop {min(args.top, len(missing))} missing by count:")
        print_top_missing(missing, danbooru_tags, args.top)

    if duplicates:
        print(f"\nTop {min(args.top, len(duplicates))} duplicate accounted tags:")
        for tag, paths in sorted(duplicates.items())[: args.top]:
            print(f"  {display_tag(tag)}\t" + ", ".join(str(path) for path in paths))

    if suspicious:
        print(f"\nTop {min(args.top, len(suspicious))} suspicious quoted TSV tags:")
        for path, tag in suspicious[: args.top]:
            print(f"  {path.relative_to(data_dir)}\t{tag}")

    if extra:
        print(f"\nTop {min(args.top, len(extra))} extra curated tags not in Danbooru CSV:")
        print_extra(extra, locations, args.top)

    failed = bool(missing or duplicates or suspicious or (args.strict_extra and extra))
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
