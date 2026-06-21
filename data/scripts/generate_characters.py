#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

CHARACTER_CATEGORY = "4"
COPYRIGHT_CATEGORY = "3"
GENERAL_CATEGORY = "0"
DEFAULT_TOP_N: int | None = None
DEFAULT_MAX_FRANCHISES = 3
DEFAULT_MIN_FRANCHISE_COUNT = 10.0
DEFAULT_MIN_FRANCHISE_RATIO = 0.1
DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENTITIES_OUTPUT_TSV = DATA_DIR / "tag_entities" / "characters.tsv"
DEFAULT_RELATIONSHIPS_OUTPUT_TSV = DATA_DIR / "tag_relationships" / "character_tags.tsv"


def display_tag(tag: str) -> str:
    return tag.strip().replace("_", " ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Writes lean character entity rows and generated character-tag "
            "relationship rows."
        )
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help="Maximum related tags per character. Defaults to no clipping.",
    )
    parser.add_argument(
        "--max-franchises",
        type=int,
        default=DEFAULT_MAX_FRANCHISES,
        help=(
            "Maximum franchise/copyright relationships written per character. "
            f"Defaults to {DEFAULT_MAX_FRANCHISES}."
        ),
    )
    parser.add_argument(
        "--min-franchise-count",
        type=float,
        default=DEFAULT_MIN_FRANCHISE_COUNT,
        help=(
            "Minimum raw character/franchise cooccurrence count to keep. "
            f"Defaults to {DEFAULT_MIN_FRANCHISE_COUNT:g}."
        ),
    )
    parser.add_argument(
        "--min-franchise-ratio",
        type=float,
        default=DEFAULT_MIN_FRANCHISE_RATIO,
        help=(
            "Minimum fraction of a character's total count that must cooccur with a franchise. "
            f"Defaults to {DEFAULT_MIN_FRANCHISE_RATIO:g}."
        ),
    )
    parser.add_argument(
        "--entities-output",
        type=Path,
        default=DEFAULT_ENTITIES_OUTPUT_TSV,
        help=f"Character entity TSV path. Defaults to {DEFAULT_ENTITIES_OUTPUT_TSV}.",
    )
    parser.add_argument(
        "--relationships-output",
        type=Path,
        default=DEFAULT_RELATIONSHIPS_OUTPUT_TSV,
        help=(
            "Character related-tags TSV path. "
            f"Defaults to {DEFAULT_RELATIONSHIPS_OUTPUT_TSV}."
        ),
    )
    parser.add_argument("tags_csv", type=Path)
    parser.add_argument("cooccurrence_csv", type=Path)
    return parser.parse_args()


def load_tags(tags_csv: Path) -> tuple[dict[str, int], set[str], set[str]]:
    character_counts: dict[str, int] = {}
    franchise_tags: set[str] = set()
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
            elif category == COPYRIGHT_CATEGORY:
                franchise_tags.add(tag)
            elif category == GENERAL_CATEGORY:
                general_tags.add(tag)

    return character_counts, franchise_tags, general_tags


def _is_character_franchise_pair(
    character: str,
    franchise: str,
    cooccurrence_count: float,
    character_counts: dict[str, int],
    franchise_tags: set[str],
    args: argparse.Namespace,
) -> bool:
    if character not in character_counts or franchise not in franchise_tags:
        return False
    if cooccurrence_count < args.min_franchise_count:
        return False
    character_count = character_counts[character]
    if character_count > 0 and cooccurrence_count / character_count < args.min_franchise_ratio:
        return False
    return True


def main() -> None:
    args = parse_args()

    if args.top_n is not None and args.top_n < 1:
        raise ValueError("--top-n must be a positive integer")
    if args.max_franchises < 1:
        raise ValueError("--max-franchises must be a positive integer")
    if args.min_franchise_count < 0:
        raise ValueError("--min-franchise-count must be non-negative")
    if args.min_franchise_ratio < 0:
        raise ValueError("--min-franchise-ratio must be non-negative")
    if not args.tags_csv.exists():
        raise FileNotFoundError(f"Tags CSV not found: {args.tags_csv}")
    if not args.cooccurrence_csv.exists():
        raise FileNotFoundError(f"Cooccurrence CSV not found: {args.cooccurrence_csv}")

    character_counts, franchise_tags, general_tags = load_tags(args.tags_csv)
    related: dict[str, list[tuple[float, str]]] = defaultdict(list)
    franchises: dict[str, list[tuple[float, str]]] = defaultdict(list)

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
            if _is_character_franchise_pair(tag_a, tag_b, count, character_counts, franchise_tags, args):
                franchises[tag_a].append((count, tag_b))
            if _is_character_franchise_pair(tag_b, tag_a, count, character_counts, franchise_tags, args):
                franchises[tag_b].append((count, tag_a))

    characters = sorted(
        character_counts,
        key=lambda tag: (-character_counts[tag], tag),
    )
    characters_with_relationships = [tag for tag in characters if tag in related]

    args.entities_output.parent.mkdir(parents=True, exist_ok=True)
    with args.entities_output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(("tag", "count", "franchises"))
        for character in characters:
            character_franchises = sorted(franchises.get(character, []), key=lambda item: (-item[0], item[1]))[
                : args.max_franchises
            ]
            writer.writerow(
                (
                    display_tag(character),
                    character_counts[character],
                    ", ".join(display_tag(tag) for _, tag in character_franchises),
                )
            )

    args.relationships_output.parent.mkdir(parents=True, exist_ok=True)
    with args.relationships_output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(("tag", "related"))
        for character in characters_with_relationships:
            tags = sorted(related[character], key=lambda item: (-item[0], item[1]))
            if args.top_n is not None:
                tags = tags[: args.top_n]
            writer.writerow(
                (
                    display_tag(character),
                    ", ".join(display_tag(tag) for _, tag in tags),
                )
            )

    print(f"Wrote {len(characters)} character entity rows to {args.entities_output}")
    print(
        f"Wrote {len(characters_with_relationships)} character relationship rows "
        f"to {args.relationships_output}"
    )


if __name__ == "__main__":
    main()
