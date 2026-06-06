#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

TOP_N = 100
CATEGORY_DIR = Path("tag_categories")
GENERAL_TAGS = Path("general.txt")
TAGS_CSV = Path("danbooru_tags.csv")
FALLBACK_TAGS_CSV = Path(
    "/home/charlierz/ComfyImage/custom_nodes/ComfyUI-Autocomplete-Plus/data/danbooru_tags.csv"
)
COOCCURRENCE_CSV = Path("danbooru_tags_cooccurrence.csv")
DOWNLOAD_SCRIPT = Path("scripts/download_danbooru_tag_csv.py")
OUTPUT_DIR = Path("tag_category_cooccurrence")
METRICS = (
    "cooccurrence",
    "jaccard",
    "lift",
    "cosine",
)


def load_general_tag_order() -> dict[str, int]:
    if not GENERAL_TAGS.exists():
        raise FileNotFoundError(f"Could not find general tag order file: {GENERAL_TAGS}")

    tags = [tag.strip() for tag in GENERAL_TAGS.read_text().replace("\n", ",").split(",")]
    order = {tag: index for index, tag in enumerate(tags) if tag}
    print(f"Loaded {len(order)} general tags from {GENERAL_TAGS}")
    return order


def load_tag_counts() -> dict[str, float]:
    tags_csv = TAGS_CSV if TAGS_CSV.exists() else FALLBACK_TAGS_CSV
    if not tags_csv.exists():
        raise FileNotFoundError(
            f"Could not find {TAGS_CSV} or fallback tag metadata CSV: {FALLBACK_TAGS_CSV}. "
            f"Run {DOWNLOAD_SCRIPT} to download local CSV inputs."
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

    print(f"Loaded {len(counts)} tag counts from {tags_csv}")
    return counts


def score_pair(
    metric: str,
    source_count: float,
    target_count: float,
    cooccurrence: float,
) -> float:
    match metric:
        case "cooccurrence":
            return cooccurrence
        case "jaccard":
            union = source_count + target_count - cooccurrence
            return cooccurrence / union if union > 0 else 0.0
        case "lift":
            # N is omitted because it is constant for ranking within this dataset.
            return cooccurrence / (source_count * target_count) if source_count > 0 and target_count > 0 else 0.0
        case "cosine":
            denominator = math.sqrt(source_count * target_count)
            return cooccurrence / denominator if denominator > 0 else 0.0
        case _:
            raise ValueError(f"Unknown metric: {metric}")


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    general_tag_order = load_general_tag_order()
    tag_counts = load_tag_counts()

    category_tags: dict[str, set[str]] = {}
    category_order: dict[str, list[str]] = {}
    tag_to_categories: dict[str, list[str]] = defaultdict(list)

    for path in sorted(CATEGORY_DIR.glob("*.txt")):
        name = path.stem
        ordered_tags: list[str] = []
        seen: set[str] = set()

        for line in path.read_text().splitlines():
            tag = line.strip()
            if not tag or tag in seen:
                continue
            ordered_tags.append(tag)
            seen.add(tag)

        original_index = {tag: index for index, tag in enumerate(ordered_tags)}
        ordered_tags.sort(
            key=lambda tag: (
                general_tag_order.get(tag, len(general_tag_order) + original_index[tag]),
                original_index[tag],
            )
        )

        category_order[name] = ordered_tags
        category_tags[name] = seen

        for tag in seen:
            tag_to_categories[tag].append(name)

    related: dict[str, dict[str, dict[str, list[tuple[float, str]]]]] = {
        metric: {name: defaultdict(list) for name in category_tags}
        for metric in METRICS
    }

    if not COOCCURRENCE_CSV.exists():
        raise FileNotFoundError(
            f"Could not find {COOCCURRENCE_CSV}. "
            f"Run {DOWNLOAD_SCRIPT} to download local CSV inputs."
        )

    with COOCCURRENCE_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag_a = row["tag_a"]
            tag_b = row["tag_b"]

            try:
                count = float(row["count"])
            except ValueError:
                continue

            # Match each category file against itself: both endpoints must appear
            # in the same tag_categories/*.txt file.
            common_categories = set(tag_to_categories.get(tag_a, ())).intersection(
                tag_to_categories.get(tag_b, ())
            )

            count_a = tag_counts.get(tag_a, 0.0)
            count_b = tag_counts.get(tag_b, 0.0)

            for category in common_categories:
                for metric in METRICS:
                    score_ab = score_pair(metric, count_a, count_b, count)
                    score_ba = score_pair(metric, count_b, count_a, count)

                    if score_ab > 0:
                        related[metric][category][tag_a].append((score_ab, tag_b))
                    if score_ba > 0:
                        related[metric][category][tag_b].append((score_ba, tag_a))

    for metric in METRICS:
        metric_output_dir = OUTPUT_DIR / metric
        metric_output_dir.mkdir(parents=True, exist_ok=True)

        for name, ordered_tags in category_order.items():
            output_path = metric_output_dir / f"{name}.tsv"

            with output_path.open("w", newline="") as f:
                for tag in ordered_tags:  # Preserve order from tag_categories/*.txt.
                    items = sorted(
                        related[metric][name].get(tag, ()),
                        key=lambda item: (-item[0], item[1]),
                    )[:TOP_N]
                    f.write(tag + "\t" + ",".join(other for _, other in items) + "\n")

            nonempty = sum(1 for tag in ordered_tags if related[metric][name].get(tag))
            print(
                f"Wrote {output_path} "
                f"({len(ordered_tags)} rows, {nonempty} with related tags)"
            )


if __name__ == "__main__":
    main()
