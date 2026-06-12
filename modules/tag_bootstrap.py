from __future__ import annotations

import csv
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCRIPTS_DIR = DATA_DIR / "scripts"
TAGS_CSV = DATA_DIR / "danbooru_tags.csv"
COOCCURRENCE_CSV = DATA_DIR / "danbooru_tags_cooccurrence.csv"
CHARACTERS_TSV = DATA_DIR / "tag_entities" / "characters.tsv"
FRANCHISES_TSV = DATA_DIR / "tag_entities" / "franchises.tsv"
CHARACTER_TAGS_TSV = DATA_DIR / "tag_relationships" / "character_tags.tsv"
RELATED_COSINE_JACCARD_TSV = (
    DATA_DIR / "tag_relationships" / "related_tags_cosine_jaccard.tsv"
)
RELATED_LIFT_TSV = DATA_DIR / "tag_relationships" / "related_tags_lift.tsv"

DATASET_BASE_URL = (
    "https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv/resolve/main"
)
COPYRIGHT_CATEGORY = "3"

SOURCE_FILES = (TAGS_CSV, COOCCURRENCE_CSV)
GENERATED_FILES = (
    CHARACTERS_TSV,
    FRANCHISES_TSV,
    CHARACTER_TAGS_TSV,
    RELATED_COSINE_JACCARD_TSV,
    RELATED_LIFT_TSV,
)


def ensure_generated_tag_data() -> None:
    """Download source CSVs and generate missing runtime tag data files."""
    if _env_flag("COMFYUI_CHARLIERZ_SKIP_TAG_BOOTSTRAP"):
        print(
            "[comfyui-charlierz] Skipping tag data bootstrap due to "
            "COMFYUI_CHARLIERZ_SKIP_TAG_BOOTSTRAP"
        )
        return

    missing_generated = [path for path in GENERATED_FILES if not _has_content(path)]
    if not missing_generated:
        return

    print(
        "[comfyui-charlierz] Missing generated tag data files: "
        + ", ".join(str(path.relative_to(DATA_DIR)) for path in missing_generated)
    )
    print(
        "[comfyui-charlierz] Preparing Danbooru tag data. "
        "This can take several minutes."
    )

    for source_file in SOURCE_FILES:
        if not _has_content(source_file):
            _download_source_file(source_file.name)

    if not _has_content(FRANCHISES_TSV):
        _generate_franchises()

    if not _has_content(CHARACTERS_TSV) or not _has_content(CHARACTER_TAGS_TSV):
        _run_script(
            "generate_characters.py",
            str(TAGS_CSV),
            str(COOCCURRENCE_CSV),
        )

    if not _has_content(RELATED_COSINE_JACCARD_TSV) or not _has_content(
        RELATED_LIFT_TSV
    ):
        _run_script("generate_tag_pool_related.py")

    still_missing = [path for path in GENERATED_FILES if not _has_content(path)]
    if still_missing:
        raise RuntimeError(
            "Tag data bootstrap finished but files are still missing: "
            + ", ".join(str(path) for path in still_missing)
        )

    print("[comfyui-charlierz] Tag data bootstrap complete")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _has_content(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _download_source_file(filename: str) -> None:
    destination = DATA_DIR / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    url = f"{DATASET_BASE_URL}/{filename}?download=true"

    print(f"[comfyui-charlierz] Downloading {url}")
    try:
        with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        temporary.replace(destination)
        print(f"[comfyui-charlierz] Wrote {destination}")
    finally:
        if temporary.exists():
            temporary.unlink()


def _generate_franchises() -> None:
    if not _has_content(TAGS_CSV):
        raise FileNotFoundError(f"Tags CSV not found: {TAGS_CSV}")

    rows: list[tuple[int, str]] = []
    with TAGS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["category"] != COPYRIGHT_CATEGORY:
                continue
            try:
                count = int(row["count"])
            except ValueError:
                count = 0
            rows.append((count, row["tag"].strip().replace("_", " ")))

    rows.sort(key=lambda item: (-item[0], item[1]))
    FRANCHISES_TSV.parent.mkdir(parents=True, exist_ok=True)
    with FRANCHISES_TSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(("tag", "count"))
        for count, tag in rows:
            writer.writerow((tag, count))

    print(f"[comfyui-charlierz] Wrote {len(rows)} franchise rows to {FRANCHISES_TSV}")


def _run_script(script_name: str, *args: str) -> None:
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    command = [sys.executable, str(script_path), *args]
    print("[comfyui-charlierz] Running " + " ".join(command))
    subprocess.run(command, cwd=DATA_DIR.parent, check=True)
