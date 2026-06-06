#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

GENERAL_CATEGORY = "0"


def usage() -> None:
    script = Path(sys.argv[0]).name
    print(f"Usage: {script} INPUT_CSV OUTPUT_TXT", file=sys.stderr)
    print(file=sys.stderr)
    print(
        "Extracts Danbooru general tags (category 0), sorts them by "
        "popularity/count descending, and writes a comma-delimited tag list.",
        file=sys.stderr,
    )


def main() -> None:
    if len(sys.argv) != 3 or "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        usage()
        raise SystemExit(0 if len(sys.argv) == 2 and sys.argv[1] in {"--help", "-h"} else 2)

    input_csv = Path(sys.argv[1])
    output_txt = Path(sys.argv[2])

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    tags: list[tuple[int, str]] = []
    with input_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["category"] != GENERAL_CATEGORY:
                continue

            try:
                count = int(row["count"])
            except ValueError:
                count = 0

            tags.append((count, row["tag"].strip()))

    tags.sort(key=lambda item: (-item[0], item[1]))

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(",".join(tag for _, tag in tags) + "\n", encoding="utf-8")
    print(f"Wrote {len(tags)} general tags to {output_txt}")


if __name__ == "__main__":
    main()
