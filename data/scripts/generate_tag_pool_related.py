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


def load_tag_pool_rows(
    tag_pools_dir: Path,
) -> tuple[
    list[Path],
    dict[Path, list[dict[str, str]]],
    dict[Path, list[str]],
    dict[str, str],
]:
    paths = sorted(tag_pools_dir.rglob("*.tsv"))
    if not paths:
        raise FileNotFoundError(f"No tag pool TSV files found in {tag_pools_dir}")

    file_rows: dict[Path, list[dict[str, str]]] = {}
    file_fieldnames: dict[Path, list[str]] = {}
    canonical_to_display: dict[str, str] = {}

    for path in paths:
        rows: list[dict[str, str]] = []
        with path.open(newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            fieldnames = list(reader.fieldnames or [])
            if "tag" not in fieldnames:
                raise ValueError(f"Missing tag column: {path}")
            if "related" not in fieldnames:
                fieldnames.append("related")

            for row in reader:
                tag = (row.get("tag") or "").strip()
                if tag:
                    canonical = canonical_tag(tag)
                    existing = canonical_to_display.get(canonical)
                    if existing is not None and existing != tag:
                        raise ValueError(
                            f"Duplicate canonical tag {canonical}: "
                            f"{existing!r} / {tag!r}"
                        )
                    canonical_to_display[canonical] = tag
                rows.append(row)

        file_rows[path] = rows
        file_fieldnames[path] = fieldnames

    return paths, file_rows, file_fieldnames, canonical_to_display


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

            score = cosine_jaccard(
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


def write_tag_pools(
    file_rows: dict[Path, list[dict[str, str]]],
    file_fieldnames: dict[Path, list[str]],
    related_strings: dict[str, str],
    dry_run: bool,
) -> tuple[int, int]:
    updated_files = 0
    updated_rows = 0

    for path, rows in file_rows.items():
        fieldnames = file_fieldnames[path]
        for row in rows:
            tag = (row.get("tag") or "").strip()
            row["related"] = related_strings.get(canonical_tag(tag), "") if tag else ""

        if not dry_run:
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames,
                    delimiter="\t",
                    lineterminator="\n",
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(rows)

        updated_files += 1
        updated_rows += len(rows)

    return updated_files, updated_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate data/tag_pools/**/*.tsv related columns using cosine_jaccard "
            "against only tags that are also in the tag pools."
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
        help="Calculate stats without writing TSV files.",
    )
    return parser.parse_args()


def main() -> None:
    # Existing related columns can exceed Python's default CSV field-size limit.
    csv.field_size_limit(sys.maxsize)

    args = parse_args()
    if args.top_n is not None and args.top_n < 1:
        raise ValueError("--top-n must be greater than 0")

    paths, file_rows, file_fieldnames, canonical_to_display = load_tag_pool_rows(
        TAG_POOLS_DIR
    )
    counts = load_tag_counts(TAGS_CSV)
    related_strings, matched_pairs = build_related_tags(
        COOCCURRENCE_CSV,
        counts,
        canonical_to_display,
        args.top_n,
    )
    updated_files, updated_rows = write_tag_pools(
        file_rows,
        file_fieldnames,
        related_strings,
        args.dry_run,
    )

    total_bytes = sum(path.stat().st_size for path in paths)
    print(f"{'Would update' if args.dry_run else 'Updated'} {updated_files} files / {updated_rows} rows")
    print(f"Pool canonical tags: {len(canonical_to_display)}")
    print(
        "Pool tags present in danbooru_tags.csv: "
        f"{sum(tag in counts for tag in canonical_to_display)}"
    )
    print(f"Matched undirected cooccurrence pairs: {matched_pairs}")
    print(f"Tags with related tags: {len(related_strings)}")
    print(f"Directed related entries: {sum(len(value.split(',')) for value in related_strings.values() if value)}")
    print(f"Total tag pool bytes: {total_bytes}")


if __name__ == "__main__":
    main()
