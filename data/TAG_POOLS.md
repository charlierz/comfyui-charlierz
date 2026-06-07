# Tag pool curation guidelines

`data/tag_pools/` contains manually curated prompt tag pools. These files are semantic buckets for image generation, not raw Danbooru category mirrors.

## File format

Each pool is a TSV with this header:

```tsv
tag	count	related
```

Rules:

- Tag text uses spaces, not underscores: `open mouth`, not `open_mouth`.
- Preserve meaningful hyphens: `upside-down`, `side-tie panties`, `ass-to-ass penetration`.
- Keep Danbooru punctuation when it is part of the tag: `oyakodon (sex)`, `jack-o' challenge`.
- `count` is the Danbooru post count when known; leave blank when unknown.
- `related` may be blank.
- A tag must appear in exactly one pool globally.
- Rows are sorted by numeric `count` descending. Rows without counts come after counted rows and are sorted alphabetically by tag.
- For equal numeric counts, sort alphabetically by tag.

## Relationship to `tag_categories/`

`data/tag_categories/*.txt` are broad source categories. Tags there may use underscores. In tag pools, normalize underscores to spaces.

When checking coverage, compare category tags after replacing `_` with spaces.

Important invariant:

- Every tag from `data/tag_categories/actions_poses.txt` should exist in exactly one `tag_pools/**/*.tsv` file after underscore-to-space normalization.

## Semantic bucket principles

Choose the most specific useful bucket for image generation. Avoid broad junk-drawer files when a better bucket exists.

### Pose pools

Use `pose/` for visible body arrangement, interaction, or frozen action.

- `pose/position.tsv` — static body arrangement: `sitting`, `on back`, `partially submerged`.
- `pose/movement.tsv` — implied motion: `running`, `hair flip`, `bouncing ass`.
- `pose/gesture.tsv` — communicative/recognizable gestures: `peace sign`, `facepalm`, `rabbit pose`.
- `pose/hands.tsv` — hand placement/contact: `hand between legs`, `stroking own chin`.
- `pose/breast_touch.tsv` — breast-specific touch/contact.
- `pose/sexual.tsv` — sexual acts and sex positions.
- `pose/bondage.tsv` — bondage/restraint states and setups.
- `pose/action.tsv` — residual visible actions that do not fit a more specific pose pool.

### Body pools

Use `body/` for anatomy, body traits, and visible body states.

- Keep anatomy in body files: `pussy`, `clitoris`, `penis`, `labia`.
- Keep passive body states in body files: `gaping`, `sweat`, `steaming body`.
- Use `body/moisture.tsv` for wetness/sweat states: `wet`, `sweat`, `very sweaty`, `steaming body`.
- Move active manipulation/actions out of body: `spreading own pussy` → `pose/sexual.tsv`; `wiping sweat` → `pose/action.tsv`.
- Use `body/exposure.tsv` for body visibility/nudity states: `nude`, `bare shoulders`, `cleavage`, `covering breasts`, `naked shirt`.

### Clothes pools

Use `clothes/` for garments, accessories, garment construction, and clothing manipulation.

- `clothes/exposure.tsv` — underwear visibility, reveal, clothing-aside, and exposure-oriented clothing manipulation: `pantyshot`, `upskirt`, `clothes lift`, `skirt lift`, `see-through clothes`.
- `clothes/descriptor/` — garment descriptors such as cutouts, details, condition, and fit: `skin tight`, `fur trim`, `cleavage cutout`, `torn`.
- `clothes/garment/` — primary garment types: tops, bottoms, dresses, footwear, legwear, armor, coverings.
- `clothes/outfit/` — full outfit categories and style families: uniforms, swimsuits, traditional clothing, bodysuits, outfit styles.
- `clothes/state/` — clothing states and non-exposure manipulation: `open kimono`, `swimsuit aside`, `apron pull`.
- Generic colors/materials/patterns belong in `visual/`, not clothes descriptors.

### Camera, scene, style, visual

Camera pools separate viewpoint, framing, composition, and focus:

- `camera/viewpoint.tsv` — angle, POV, perspective, lens/view direction: `from above`, `pov`, `fisheye`, `isometric`.
- `camera/framing.tsv` — shot size, crop, and out-of-frame tags: `full body`, `close-up`, `out of frame`, `cropped legs`.
- `camera/composition.tsv` — layout/compositional devices: `border`, `multiple views`, `reference sheet`, `projected inset`, `symmetry`.
- `camera/focus.tsv` — explicit focus targets: `solo focus`, `ass focus`, `foot focus`.

Other visual buckets:

- Background colors and patterns belong under `scene/bg/color.tsv` and `scene/bg/pattern.tsv`.
- Specific places belong under `scene/bg/places.tsv`.
- Visual materials/colors/patterns belong under `visual/`.
- Rendering/shading/media format belong under `style/`.

## Duplicate policy

Duplicates are not allowed globally. If a tag seems to belong in multiple places, choose the bucket that best controls image generation intent.

Examples:

- `ass focus` → `camera/focus.tsv`, not `body/ass.tsv`.
- `covering breasts` → `body/exposure.tsv`, not `pose/breast_touch.tsv`.
- `clothes lift` → `clothes/exposure.tsv`, not `pose/action.tsv`.
- `blindfold` → `clothes/sexual/bdsm.tsv`, not generic accessories or scene objects.

## Validation snippets

Find duplicate tags globally:

```bash
python - <<'PY'
from pathlib import Path
from collections import defaultdict
locs = defaultdict(list)
for p in Path('data/tag_pools').rglob('*.tsv'):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if i == 1 and line.startswith('tag\t'):
            continue
        if line.strip():
            locs[line.split('\t')[0]].append(f'{p}:{i}')
for tag, places in sorted(locs.items()):
    if len(places) > 1:
        print(tag, places)
PY
```

Verify `actions_poses.txt` coverage:

```bash
python - <<'PY'
from pathlib import Path
actions = [
    line.strip().replace('_', ' ')
    for line in Path('data/tag_categories/actions_poses.txt').read_text().splitlines()
    if line.strip()
]
pool = set()
for p in Path('data/tag_pools').rglob('*.tsv'):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if i == 1 and line.startswith('tag\t'):
            continue
        if line.strip():
            pool.add(line.split('\t')[0])
missing = [tag for tag in actions if tag not in pool]
print('actions_poses missing', len(missing))
for tag in missing:
    print(tag)
PY
```
