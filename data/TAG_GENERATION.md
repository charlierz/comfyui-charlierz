# Danbooru tag relatedness files

This folder contains Danbooru tag lists and generated TSVs for finding related tags within curated tag categories.

## Credits

Source CSVs are downloaded from [`newtextdoc1111/danbooru-tag-csv`](https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv). The generated files in this folder are derived from that dataset plus this repository's curated category files.

## Source data

- `danbooru_tags.csv` — tag metadata: `tag,category,count,alias`. Used for tag post counts in relatedness scoring. Large local input; ignored by git.
- `danbooru_tags_cooccurrence.csv` — raw tag-pair cooccurrence data: `tag_a,tag_b,count`. Large local input; ignored by git.
- `general.txt` — extracted general tag list.
- `copyrights.txt` — extracted copyright/franchise tag list.
- `characters.tsv` — character tags mapped to all related general tags with Danbooru character counts, sorted by character popularity/count descending.

## Scripts

- `scripts/generate_general_tags.py` — extracts general tags.
- `scripts/generate_copyrights.py` — extracts copyright/franchise tags.
- `scripts/generate_characters.py` — generates `characters.tsv`.
- `scripts/download_danbooru_tag_csv.py` — downloads large local CSV inputs from Hugging Face.
- `scripts/generate_tag_category_cooccurrence.py` — generates per-category related-tag TSVs.
- `scripts/sort_tag_categories_by_general.py` — sorts `tag_categories/*.txt` by `general.txt` popularity order.

Download large CSV inputs:

```bash
./scripts/download_danbooru_tag_csv.py
```

The download source is:

```text
https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv/tree/main
```

Extract general tags:

```bash
./scripts/generate_general_tags.py danbooru_tags.csv general.txt
```

Extract copyright/franchise tags:

```bash
./scripts/generate_copyrights.py
```

Generate character tags:

```bash
./scripts/generate_characters.py danbooru_tags.csv danbooru_tags_cooccurrence.csv characters.tsv
```

This writes `tag<TAB>count<TAB>related` and does not clip related tags by default. Use `--top-n` only for analysis or alternate clipped outputs.

After editing `tag_categories/*.txt`, re-sort the category files, then regenerate related-tag TSVs:

```bash
./scripts/sort_tag_categories_by_general.py
./scripts/generate_tag_category_cooccurrence.py
```

The Python generation script reads tag counts from `./danbooru_tags.csv`.
If that file is absent, run `./scripts/download_danbooru_tag_csv.py` first.

## Tag categories

`tag_categories/*.txt` contains curated tag groups. The current groups are:

- `actions_poses.txt`
- `appearance_anatomy.txt`
- `clothing_accessories.txt`
- `expressions.txt`
- `scene_background.txt`
- `style_quality.txt`
- `themes_roles.txt`

The files define category membership. Generated TSV rows are ordered by `general.txt` popularity order, not by the category file order. Tags missing from `general.txt` are placed after ranked tags, preserving their category-file order.

### Reclassification policy

Reclassifying tags between category files is a semantic curation task. Future reclassifications should be done by an AI/human reading and judging each tag's meaning in context, not by broad pattern matching such as suffixes, prefixes, or substring rules. Pattern searches may be used only to find candidates for review; the final move list must be explicitly curated.

## Generated outputs

Generated files are under `tag_category_cooccurrence/`, split by scoring method:

- `cooccurrence/` — raw cooccurrence count. Good for common pairs, but popular tags dominate.
- `jaccard/` — `cooccurrence / (count_a + count_b - cooccurrence)`. Same method used by ComfyUI-Autocomplete-Plus.
- `lift/` — `cooccurrence / (count_a * count_b)`, with the dataset-size constant omitted for ranking. Highlights unusually specific associations, but can over-rank rare tags.
- `cosine/` — `cooccurrence / sqrt(count_a * count_b)`. Often a useful middle ground.

Each scoring directory contains one TSV per tag category:

```text
tag_category_cooccurrence/<score>/<category>.tsv
```

Each TSV row has this format:

```tsv
tag	related_tag_1,related_tag_2,...
```

Related tags are limited to the top 100 for each row.

## Notes

- Matching is done within each category file only: both tags in a pair must appear in the same `tag_categories/*.txt` file.
- Row order follows `general.txt`, which is ordered by popularity.
- Tags missing from `general.txt` are placed after ranked tags, preserving their category-file order.
- Related tags within each row are sorted by the selected scoring method.
