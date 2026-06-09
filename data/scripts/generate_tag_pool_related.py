#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
TAG_POOLS_DIR = DATA_DIR / "tag_pools"
TAGS_CSV = DATA_DIR / "danbooru_tags.csv"
COOCCURRENCE_CSV = DATA_DIR / "danbooru_tags_cooccurrence.csv"
DOWNLOAD_SCRIPT = DATA_DIR / "scripts" / "download_danbooru_tag_csv.py"
CHARACTERS_TSV = DATA_DIR / "tag_entities" / "characters.tsv"
FRANCHISES_TSV = DATA_DIR / "tag_entities" / "franchises.tsv"
OUTPUT_DIR = DATA_DIR / "tag_relationships"
OUTPUT_COSINE_JACCARD = OUTPUT_DIR / "related_tags_cosine_jaccard.tsv"
OUTPUT_LIFT = OUTPUT_DIR / "related_tags_lift.tsv"


def canonical_tag(tag: str) -> str:
    """Convert tag-pool display tags to Danbooru CSV tag names."""
    return tag.strip().replace(" ", "_")


def display_tag(canonical: str) -> str:
    """Fallback display form for canonical tags."""
    return canonical.replace("_", " ")


def cosine_jaccard(
    source_count: float,
    target_count: float,
    cooccurrence: float,
) -> float:
    denominator = math.sqrt(source_count * target_count)
    cosine = cooccurrence / denominator if denominator > 0 else 0.0

    union = source_count + target_count - cooccurrence
    jaccard = cooccurrence / union if union > 0 else 0.0

    return cosine * jaccard


def lift(
    source_count: float,
    target_count: float,
    cooccurrence: float,
) -> float:
    """Calculate lift score: cooccurrence / (source_count * target_count).
    
    This is proportional to the statistical lift measure and useful for ranking.
    """
    denominator = source_count * target_count
    return cooccurrence / denominator if denominator > 0 else 0.0


def load_excluded_tags() -> set[str]:
    """Load canonical tags that should be excluded (characters and franchises)."""
    excluded = set()
    for tsv_path in [CHARACTERS_TSV, FRANCHISES_TSV]:
        if not tsv_path.exists():
            continue
        with tsv_path.open(newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                tag = (row.get("tag") or "").strip()
                if tag:
                    excluded.add(canonical_tag(tag))
    return excluded


def load_tag_pool_rows(
    tag_pools_dir: Path,
    excluded_tags: set[str],
) -> dict[str, str]:
    """Load all tags from pool TSVs, excluding specified canonical tags."""
    canonical_to_display: dict[str, str] = {}

    for path in sorted(tag_pools_dir.rglob("*.tsv")):
        with path.open(newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            fieldnames = list(reader.fieldnames or [])
            if "tag" not in fieldnames:
                raise ValueError(f"Missing tag column: {path}")

            for row in reader:
                tag = (row.get("tag") or "").strip()
                if not tag:
                    continue
                canonical = canonical_tag(tag)
                if canonical in excluded_tags:
                    continue
                existing = canonical_to_display.get(canonical)
                if existing is not None and existing != tag:
                    raise ValueError(
                        f"Duplicate canonical tag {canonical}: "
                        f"{existing!r} / {tag!r}"
                    )
                canonical_to_display[canonical] = tag

    return canonical_to_display


def load_tag_counts(tags_csv: Path) -> dict[str, float]:
    if not tags_csv.exists():
        raise FileNotFoundError(
            f"Could not find {tags_csv}. Run {DOWNLOAD_SCRIPT} first."
        )

    counts: dict[str, float] = {}
    with tags_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag = row["tag"].strip()
            try:
                counts[tag] = float(row["count"])
            except ValueError:
                continue

    return counts


def build_related_tags(
    cooccurrence_csv: Path,
    counts: dict[str, float],
    canonical_to_display: dict[str, str],
    similarity_fn,
    top_n: int | None,
) -> tuple[dict[str, str], int]:
    if not cooccurrence_csv.exists():
        raise FileNotFoundError(
            f"Could not find {cooccurrence_csv}. Run {DOWNLOAD_SCRIPT} first."
        )

    pool_tags = set(canonical_to_display)
    related: dict[str, list[tuple[float, str]]] = defaultdict(list)
    matched_pairs = 0

    with cooccurrence_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag_a = row["tag_a"]
            tag_b = row["tag_b"]
            if tag_a not in pool_tags or tag_b not in pool_tags:
                continue

            try:
                count = float(row["count"])
            except ValueError:
                continue

            score = similarity_fn(
                counts.get(tag_a, 0.0),
                counts.get(tag_b, 0.0),
                count,
            )
            if score <= 0:
                continue

            related[tag_a].append((score, tag_b))
            related[tag_b].append((score, tag_a))
            matched_pairs += 1

    related_strings: dict[str, str] = {}
    for tag, items in related.items():
        items.sort(
            key=lambda item: (
                -item[0],
                canonical_to_display.get(item[1], display_tag(item[1])),
            )
        )
        if top_n is not None:
            items = items[:top_n]
        related_strings[tag] = ",".join(
            canonical_to_display.get(other, display_tag(other)) for _, other in items
        )

    return related_strings, matched_pairs


def write_relationship_file(
    output_path: Path,
    related_strings: dict[str, str],
    canonical_to_display: dict[str, str],
    dry_run: bool,
) -> int:
    """Write relationship TSV file with tag and related columns."""
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="") as f:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            writer.writerow(["tag", "related"])
            for canonical, related in sorted(related_strings.items()):
                display = canonical_to_display.get(canonical, display_tag(canonical))
                writer.writerow([display, related])
    return len(related_strings)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate related tag files from data/tag_pools/**/*.tsv using "
            "cosine_jaccard and lift similarity metrics. Outputs two files in "
            "data/tag_relationships/. Excludes character and copyright tags."
        )
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Limit related tags per row. Default: no limit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate stats without writing output files.",
    )
    return parser.parse_args()


def main() -> None:
    # Existing related columns can exceed Python's default CSV field-size limit.
    csv.field_size_limit(sys.maxsize)

    args = parse_args()
    if args.top_n is not None and args.top_n < 1:
        raise ValueError("--top-n must be greater than 0")

    excluded_tags = load_excluded_tags()
    canonical_to_display = load_tag_pool_rows(TAG_POOLS_DIR, excluded_tags)
    counts = load_tag_counts(TAGS_CSV)

    print(f"Loaded {len(canonical_to_display)} pool tags")
    print(f"Excluded {len(excluded_tags)} character/copyright tags")
    print(
        "Pool tags present in danbooru_tags.csv: "
        f"{sum(tag in counts for tag in canonical_to_display)}"
    )

    # Generate cosine_jaccard relationships
    related_cosine_jaccard, matched_pairs_cj = build_related_tags(
        COOCCURRENCE_CSV,
        counts,
        canonical_to_display,
        cosine_jaccard,
        args.top_n,
    )
    write_relationship_file(
        OUTPUT_COSINE_JACCARD,
        related_cosine_jaccard,
        canonical_to_display,
        args.dry_run,
    )

    # Generate lift relationships
    related_lift, matched_pairs_lift = build_related_tags(
        COOCCURRENCE_CSV,
        counts,
        canonical_to_display,
        lift,
        args.top_n,
    )
    write_relationship_file(
        OUTPUT_LIFT,
        related_lift,
        canonical_to_display,
        args.dry_run,
    )

    print(f"\n{'Would write' if args.dry_run else 'Wrote'} {OUTPUT_COSINE_JACCARD}")
    print(f"  Matched cooccurrence pairs: {matched_pairs_cj}")
    print(f"  Tags with relationships: {len(related_cosine_jaccard)}")
    print(
        f"  Directed entries: "
        f"{sum(len(value.split(',')) for value in related_cosine_jaccard.values() if value)}"
    )

    print(f"\n{'Would write' if args.dry_run else 'Wrote'} {OUTPUT_LIFT}")
    print(f"  Matched cooccurrence pairs: {matched_pairs_lift}")
    print(f"  Tags with relationships: {len(related_lift)}")
    print(
        f"  Directed entries: "
        f"{sum(len(value.split(',')) for value in related_lift.values() if value)}"
    )


if __name__ == "__main__":
    main()
