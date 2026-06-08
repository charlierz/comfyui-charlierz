# Tag data generation notes

## Current target model

`data/tag_pools/**/*.tsv` is the curated prompt-pool source of truth. Generated entity registries and relationship overlays live outside tag pools so they can power autocomplete/popups without being treated as curated sampling or same-pool relationship data.

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

Target data split:

```text
data/tag_pools/          # curated prompt pools; sampling and same-pool sibling relatedness
  **/*.tsv              # tag<TAB>count

data/tag_entities/       # generated entity registries; autocomplete/ranking only
  characters.tsv        # tag<TAB>count
  franchises.tsv        # tag<TAB>count

data/tag_relationships/  # generated relationship overlays; no counts
  character_tags.tsv    # tag<TAB>related
  related_tags.tsv      # tag<TAB>related
```

Relationship files should not duplicate `count`; counts belong in tag pool/entity rows unless a separate global tag registry is intentionally introduced.

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
- `scripts/generate_characters.py` — generates lean `tag_entities/characters.tsv` and `tag_relationships/character_tags.tsv` by default.
- `scripts/generate_tag_pool_related.py` — intended generator for non-character tag relationships. It should target separate relationship files, not `related` columns in tag pools.
- `scripts/generate_copyrights.py` — legacy generator for `copyrights.txt`; prefer `data/tag_entities/franchises.tsv` in the current model.

One-off migration scripts are archived under `.ai/archive/` for provenance.

## Character generation

Generate character relationships from the repo root:

```bash
data/scripts/generate_characters.py data/danbooru_tags.csv data/danbooru_tags_cooccurrence.csv
```

Or from `data/`:

```bash
./scripts/generate_characters.py danbooru_tags.csv danbooru_tags_cooccurrence.csv
```

By default this writes a lean entity registry:

```text
data/tag_entities/characters.tsv
```

```tsv
tag	count
hatsune miku	75449
```

and a generated relationship overlay:

```text
data/tag_relationships/character_tags.tsv
```

```tsv
tag	related
hatsune miku	long hair, twintails, aqua hair
```

Keeping character counts out of the relationship file allows autocomplete to load the lean entity registry without parsing every character's related tags.

## Franchise/copyright tags

`data/tag_entities/franchises.tsv` is the generated entity-registry replacement for `copyrights.txt`.

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
