from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "data" / "scripts" / "generate_characters.py"

spec = importlib.util.spec_from_file_location("generate_characters", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
generate_characters = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generate_characters
spec.loader.exec_module(generate_characters)


class GenerateCharactersTests(unittest.TestCase):
    def test_writes_ranked_franchise_relationships_to_character_entities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tags_csv = root / "tags.csv"
            cooccurrence_csv = root / "cooccurrence.csv"
            entities_output = root / "characters.tsv"
            relationships_output = root / "character_tags.tsv"

            self._write_csv(
                tags_csv,
                ["tag", "category", "count", "alias"],
                [
                    ["hatsune_miku", "4", "100", ""],
                    ["vocaloid", "3", "1000", ""],
                    ["project_voltage", "3", "50", ""],
                    ["kantai_collection", "3", "500", ""],
                    ["twintails", "0", "200", ""],
                ],
            )
            self._write_csv(
                cooccurrence_csv,
                ["tag_a", "tag_b", "count"],
                [
                    ["hatsune_miku", "vocaloid", "90"],
                    ["hatsune_miku", "project_voltage", "20"],
                    ["hatsune_miku", "kantai_collection", "3"],
                    ["hatsune_miku", "twintails", "80"],
                ],
            )

            with patch.object(
                sys,
                "argv",
                [
                    "generate_characters.py",
                    "--entities-output",
                    str(entities_output),
                    "--relationships-output",
                    str(relationships_output),
                    str(tags_csv),
                    str(cooccurrence_csv),
                ],
            ):
                generate_characters.main()

            with entities_output.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))

        self.assertEqual(rows[0]["tag"], "hatsune miku")
        self.assertEqual(rows[0]["count"], "100")
        self.assertEqual(rows[0]["franchises"], "vocaloid, project voltage")

    def _write_csv(self, path: Path, header: list[str], rows: list[list[str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
