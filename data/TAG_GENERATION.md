# Tag data generation notes

## Current target model

`data/tag_pools/**/*.tsv` is the curated tag source of truth.

Each tag pool TSV stores pool membership and source frequency only:

```tsv
tag	count
blue eyes	1265728
mysterious aura	
```

Rules:

- tag text is authored in space form;
- `count` is optional source frequency, usually seeded from Danbooru;
- tag pools do not contain related-tag columns;
- generated relationship data lives outside `tag_pools/`.

Target relationship area:

```text
data/tag_relationships/
  characters.tsv
  related_tags.tsv
```

During transition, `data/characters.tsv` may still live at the data root. It is conceptually a generated relationship file.

Relationship files should not duplicate `count`; counts belong in tag pool rows unless a separate global tag registry is intentionally introduced.

## Source data

Large local inputs are downloaded from [`newtextdoc1111/danbooru-tag-csv`](https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv):

- `danbooru_tags.csv` — tag metadata: `tag,category,count,alias`; used to seed tag-pool counts and character/franchise data.
- `danbooru_tags_cooccurrence.csv` — raw tag-pair cooccurrence data: `tag_a,tag_b,count`; used to generate relationship files.

These CSVs are local/ignored inputs, not runtime source-of-truth data.

Download them from `data/`:

```bash
./scripts/download_danbooru_tag_csv.py
```

## Active scripts

- `scripts/download_danbooru_tag_csv.py` — downloads large local CSV inputs from Hugging Face.
- `scripts/generate_characters.py` — generates character relationship TSVs.
- `scripts/generate_tag_pool_related.py` — intended generator for non-character tag relationships. It should target separate relationship files, not `related` columns in tag pools.
- `scripts/generate_copyrights.py` — legacy generator for `copyrights.txt`; prefer `data/tag_pools/theme/franchise.tsv` in the tag-pool model.

One-off migration scripts are archived under `.ai/archive/` for provenance.

## Legacy files during migration

The following files may still exist because runtime migration is incomplete or because they are useful import/reference artifacts:

- `general.txt` — legacy generated general-tag list.
- `copyrights.txt` — legacy generated copyright/franchise list; current tag-pool equivalent is `tag_pools/theme/franchise.tsv`.
- `characters.tsv` — generated character relationship file; target location may become `tag_relationships/characters.tsv`.
- `tag_categories/*.txt` — legacy broad category sources used during migration/coverage checks.
- `tag_category_cooccurrence/<metric>/*.tsv` — legacy related-tag outputs for old category files.
- `tag_pools_cooccurrence/**/*.tsv` — transitional generated relationship-like data for tag pools; should be replaced by the final relationship-file shape.

Do not treat the legacy files as the long-term runtime source of truth.

## Character generation

Generate character relationships from `data/`:

```bash
./scripts/generate_characters.py danbooru_tags.csv danbooru_tags_cooccurrence.csv characters.tsv
```

This writes:

```tsv
tag	count	related
```

Character relationship files include `count` because the source row is the character tag itself. This is different from non-character related-tag overlays, which should not duplicate tag-pool counts.

## Franchise/copyright tags

`data/tag_pools/theme/franchise.tsv` is the tag-pool replacement for `copyrights.txt`.

Current desired shape:

```tsv
tag	count
original	891679
touhou	651387
```

If regenerated, source it from Danbooru category `3` in `danbooru_tags.csv` and write space-form tags sorted by count descending.

## Related tag generation

Non-character related tags should be generated from curated tag pools plus cooccurrence data.

Desired output should live outside `data/tag_pools/`, likely:

```text
data/tag_relationships/related_tags.tsv
```

Candidate compact shape:

```tsv
tag	related
blue eyes	green eyes, aqua eyes, heterochromia
```

Potential richer edge-table shape if context/scores need to be surfaced:

```tsv
source	target	method	score	context
blue eyes	green eyes	cosine_jaccard	0.82	face/eye_appearance
```

Open design choice: compact list rows vs normalized edge rows.
