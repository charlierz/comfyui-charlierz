#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

GENERAL_TAGS = Path("general.txt")
CATEGORY_DIR = Path("tag_categories")


def load_general_tag_order() -> dict[str, int]:
    if not GENERAL_TAGS.exists():
        raise FileNotFoundError(f"Could not find general tag order file: {GENERAL_TAGS}")

    tags = [tag.strip() for tag in GENERAL_TAGS.read_text().replace("\n", ",").split(",")]
    return {tag: index for index, tag in enumerate(tags) if tag}


def sort_category_file(path: Path, general_tag_order: dict[str, int]) -> None:
    tags: list[str] = []
    seen: set[str] = set()

    for line in path.read_text().splitlines():
        tag = line.strip()
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)

    original_index = {tag: index for index, tag in enumerate(tags)}
    sorted_tags = sorted(
        tags,
        key=lambda tag: (
            general_tag_order.get(tag, len(general_tag_order) + original_index[tag]),
            original_index[tag],
        ),
    )

    path.write_text("\n".join(sorted_tags) + "\n")

    missing = sum(1 for tag in sorted_tags if tag not in general_tag_order)
    print(f"Sorted {path} ({len(sorted_tags)} tags, {missing} missing from {GENERAL_TAGS})")


def main() -> None:
    general_tag_order = load_general_tag_order()
    print(f"Loaded {len(general_tag_order)} general tags from {GENERAL_TAGS}")

    for path in sorted(CATEGORY_DIR.glob("*.txt")):
        sort_category_file(path, general_tag_order)


if __name__ == "__main__":
    main()
