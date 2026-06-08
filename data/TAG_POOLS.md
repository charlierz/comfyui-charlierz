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

Important invariants:

- Every tag from `data/tag_categories/actions_poses.txt` should exist in exactly one `tag_pools/**/*.tsv` file after underscore-to-space normalization.
- `data/tag_categories/appearance_anatomy.txt` should be represented where tags describe visible character appearance/anatomy. Obvious source-category leakage such as scene props may remain unpooled.

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

Use `body/` for anatomy, body traits, visible body states, and character-level appearance traits.

- Keep anatomy in body files: `pussy`, `clitoris`, `penis`, `labia`.
- `body/pussy/` splits vulva/pubic-area tags into anatomy, pubic hair, state, and piercing pools.
- `body/anatomy.tsv` is for general body parts and body-region traits that do not have a more specific file: `navel`, `collarbone`, `feet`, `back`.
- `body/skin.tsv` is for complexion, skin/fur color, tan, and skin surface traits: `dark skin`, `tanlines`, `blue skin`, `shiny skin`.
- `body/marks.tsv` is for tattoos, scars, bruises, markings, and piercings: `tattoo`, `scar on face`, `tramp stamp`, `lip ring`.
- `body/nails.tsv` is for fingernails/toenails and nail styling: `black nails`, `long fingernails`, `nail art`.
- `body/character.tsv` is the single body-owned bucket for character-level visual identity/archetype/species/age/gender-presentation tags: `loli`, `otoko no ko`, `cat girl`, `robot`.
- `body/mechanical.tsv` is for mechanical/prosthetic body traits: `robot joints`, `mechanical arms`, `prosthetic leg`.
- `body/fantasy/` is for non-human anatomy traits split by visible part: ears, tails, horns/halos, wings, and other traits.
- Keep passive body states in body files: `gaping`, `sweat`, `steaming body`.
- Use `body/moisture.tsv` for wetness/sweat states: `wet`, `sweat`, `very sweaty`, `steaming body`.
- Move active manipulation/actions out of body: `spreading own pussy` → `pose/sexual.tsv`; `wiping sweat` → `pose/action.tsv`.
- Use `body/exposure.tsv` for body visibility/nudity states: `nude`, `bare shoulders`, `cleavage`, `covering breasts`, `naked shirt`.

### Face pools

Use `face/` for facial expression, eye/mouth appearance, gaze, and static face features.

- `face/eye_appearance.tsv` — static eye traits: `blue eyes`, `heterochromia`, `white pupils`, `black sclera`.
- `face/features.tsv` — static face features and facial hair: `mole under eye`, `freckles`, `beard`, `sunken cheeks`.
- `face/cosmetics.tsv` — makeup and cosmetics: `makeup`, `lipstick`, `eyeshadow`, `eyeliner`.
- `face/eyes.tsv` — eye actions/expressions: `closed eyes`, `one eye closed`, `raised eyebrows`.
- `face/mouth.tsv` — mouth expressions/actions.
- `face/gaze.tsv` — gaze direction.
- `face/emoticons.tsv` — literal drawn face/emoticon tags only: `:3`, `;d`, `@ @`, `w`.
- `face/symbols.tsv` — expression punctuation and spoken-symbol tags: `?`, `!`, `spoken heart`, `spoken question mark`, `zzz`.

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

Scene/background buckets:

- `scene/background.tsv` — broad background setting states: `simple background`, `outdoors`, `indoors`, `day`, `night`.
- `scene/bg/color.tsv`, `scene/bg/pattern.tsv` — background color/pattern variants.
- `scene/bg/places.tsv` — outdoor/public places and architectural locations.
- `scene/bg/indoors.tsv` — interiors, rooms, furniture, and interior surfaces.
- `scene/bg/nature.tsv` — general terrain/natural-location tags not covered by the narrower files.
- `scene/bg/sky_weather.tsv` — sky, weather, celestial, and lighting-from-nature tags.
- `scene/bg/plants.tsv` — plants, flowers, trees, leaves, petals, and gardens.
- `scene/bg/water.tsv` — water, beaches, oceans, boats, and water-adjacent props.
- `scene/objects.tsv` — general props and object subject matter.
- `scene/food_drink.tsv` — food, drink, tableware, and food packaging.
- `scene/animals.tsv` — animals and animal subjects.
- `scene/vehicles.tsv` — vehicles and vehicle interiors/parts.
- `scene/effects.tsv` — scene effects: fire, smoke, sparkles, bubbles, explosions, blood splatter.
- `visual/symbols.tsv` — non-face graphic symbols: `heart`, `star (symbol)`, `musical note`, `arrow (symbol)`.
- Visual materials/colors/patterns belong under `visual/`.

Style buckets:

- `style/censoring.tsv` — censorship state and methods: `censored`, `mosaic censoring`, `bar censor`.
- `style/text.tsv` — visible text, names, usernames, subtitles, lyrics, dialogue, and language tags.
- `style/branding.tsv` — logos, watermarks, copyright notices, platform/company branding, and publication marks.
- `style/color_palette.tsv` — palette/theme tags: `blue theme`, `muted color`, `pastel colors`, `rainbow gradient`.
- `style/meta.tsv` — crossovers, references, connections, cameos, fourth-wall/meta tags, and source-category leakage that is about metadata rather than visible scene contents.
- `style/meme_event.tsv` — memes, drawing challenges, holidays, greetings, and commemorative day tags.
- Official/adapted/borrowed/alternate design variant tags belong in the most visible semantic domain: outfit variants under clothes, hair variants under body/hair, eye variants under face, palette variants under `style/color_palette.tsv`, and broad redesign/prototype metadata under `style/meta.tsv`.
- `style/genre_theme.tsv` — genre, setting, era, and thematic labels: `fantasy`, `cyberpunk`, `steampunk`, `post-apocalypse`.
- `style/format.tsv` — comic/page/publication/format tags.
- `style/styles.tsv` — art styles and rendering idioms.
- `style/techniques.tsv` — rendering techniques and visual effects: `motion blur`, `chromatic aberration`.
- `style/shading.tsv` — shading, hatching, screentones, and painterly texture.
- `style/errors.tsv` — malformed/low-quality/error tags.

## Duplicate policy

Duplicates are not allowed globally. If a tag seems to belong in multiple places, choose the bucket that best controls image generation intent.

Examples:

- `ass focus`, `leg focus` → `camera/focus.tsv`, not body anatomy files.
- `head only` → `camera/framing.tsv`, not `body/anatomy.tsv`.
- `object on head`, `pokemon on head`, `cat on head` → `scene/subject_matter.tsv`, not `body/anatomy.tsv`.
- `covering breasts` → `body/exposure.tsv`, not `pose/breast_touch.tsv`.
- `clothes lift` → `clothes/exposure.tsv`, not `pose/action.tsv`.
- `framed breasts` → `clothes/exposure.tsv`, because clothing frames/reveals the breasts.
- `blindfold` → `clothes/sexual/bdsm.tsv`, not generic accessories or scene objects.
- `red light` → `style/techniques.tsv`, because it is lighting, not a color swatch.

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

Verify source-category coverage:

```bash
python - <<'PY'
from pathlib import Path
pool = set()
for p in Path('data/tag_pools').rglob('*.tsv'):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if i == 1 and line.startswith('tag\t'):
            continue
        if line.strip():
            pool.add(line.split('\t')[0])

for category in ['actions_poses', 'appearance_anatomy', 'expressions', 'scene_background', 'style_quality']:
    tags = [
        line.strip().replace('_', ' ')
        for line in Path(f'data/tag_categories/{category}.txt').read_text().splitlines()
        if line.strip()
    ]
    missing = [tag for tag in tags if tag not in pool]
    print(category, 'missing', len(missing))
    for tag in missing[:50]:
        print(' ', tag)
PY
```
