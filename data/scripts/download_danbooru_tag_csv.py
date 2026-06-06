#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

DATASET_BASE_URL = "https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv/resolve/main"
FILES = (
    "danbooru_tags.csv",
    "danbooru_tags_cooccurrence.csv",
)


def download_file(filename: str, force: bool) -> None:
    destination = Path(filename)
    if destination.exists() and not force:
        print(f"Skipping {destination} (already exists; use --force to replace)")
        return

    url = f"{DATASET_BASE_URL}/{filename}?download=true"
    temporary = destination.with_suffix(destination.suffix + ".tmp")

    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if total:
                    percent = downloaded * 100 / total
                    print(f"  {downloaded / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MiB ({percent:.1f}%)", end="\r")
        if total:
            print()
        temporary.replace(destination)
        print(f"Wrote {destination}")
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    force = "--force" in sys.argv[1:]
    unknown_args = [arg for arg in sys.argv[1:] if arg != "--force"]
    if unknown_args:
        print(f"Unknown arguments: {', '.join(unknown_args)}", file=sys.stderr)
        print("Usage: scripts/download_danbooru_tag_csv.py [--force]", file=sys.stderr)
        raise SystemExit(2)

    for filename in FILES:
        download_file(filename, force)


if __name__ == "__main__":
    main()
