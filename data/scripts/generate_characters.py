#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

CHARACTER_CATEGORY = "4"
GENERAL_CATEGORY = "0"
DEFAULT_TOP_N = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Writes one TSV line per Danbooru character tag as "
            "character<TAB>general_tag_1,general_tag_2,..."
        )
    )
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("tags_csv", type=Path)
    parser.add_argument("cooccurrence_csv", type=Path)
    parser.add_argument("output_tsv", type=Path)
    return parser.parse_args()


def load_tags(tags_csv: Path) -> tuple[dict[str, int], set[str]]:
    character_counts: dict[str, int] = {}
    general_tags: set[str] = set()

    with tags_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag = row["tag"].strip()
            category = row["category"]

            if category == CHARACTER_CATEGORY:
                try:
                    character_counts[tag] = int(row["count"])
                except ValueError:
                    character_counts[tag] = 0
            elif category == GENERAL_CATEGORY:
                general_tags.add(tag)

    return character_counts, general_tags


def main() -> None:
    args = parse_args()

    if args.top_n < 1:
        raise ValueError("--top-n must be a positive integer")
    if not args.tags_csv.exists():
        raise FileNotFoundError(f"Tags CSV not found: {args.tags_csv}")
    if not args.cooccurrence_csv.exists():
        raise FileNotFoundError(f"Cooccurrence CSV not found: {args.cooccurrence_csv}")

    character_counts, general_tags = load_tags(args.tags_csv)
    related: dict[str, list[tuple[float, str]]] = defaultdict(list)

    with args.cooccurrence_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag_a = row["tag_a"]
            tag_b = row["tag_b"]

            try:
                count = float(row["count"])
            except ValueError:
                continue

            if tag_a in character_counts and tag_b in general_tags:
                related[tag_a].append((count, tag_b))
            if tag_b in character_counts and tag_a in general_tags:
                related[tag_b].append((count, tag_a))

    characters = sorted(
        related,
        key=lambda tag: (-character_counts[tag], tag),
    )

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", newline="", encoding="utf-8") as f:
        for character in characters:
            tags = sorted(related[character], key=lambda item: (-item[0], item[1]))[: args.top_n]
            f.write(character + "\t" + ",".join(tag for _, tag in tags) + "\n")

    print(f"Wrote {len(characters)} character rows to {args.output_tsv}")


if __name__ == "__main__":
    main()
