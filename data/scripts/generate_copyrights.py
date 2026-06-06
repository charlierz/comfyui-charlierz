#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

COPYRIGHT_CATEGORY = "3"
DEFAULT_INPUT = Path("danbooru_tags.csv")
DEFAULT_OUTPUT = Path("copyrights.txt")


def usage() -> None:
    script = Path(sys.argv[0]).name
    print(f"Usage: {script} [INPUT_CSV] [OUTPUT_TXT]", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Extracts Danbooru copyright tags (category 3), sorts them by "
        "popularity/count descending, and writes a comma-delimited tag list.",
        file=sys.stderr,
    )


def main() -> None:
    if len(sys.argv) > 3 or "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        usage()
        raise SystemExit(0 if len(sys.argv) <= 3 else 2)

    input_csv = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_INPUT
    output_txt = Path(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_OUTPUT

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    tags: list[tuple[int, str]] = []
    with input_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["category"] != COPYRIGHT_CATEGORY:
                continue

            try:
                count = int(row["count"])
            except ValueError:
                count = 0

            tags.append((count, row["tag"].strip()))

    tags.sort(key=lambda item: (-item[0], item[1]))

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(",".join(tag for _, tag in tags) + "\n", encoding="utf-8")
    print(f"Wrote {len(tags)} copyright tags to {output_txt}")


if __name__ == "__main__":
    main()
