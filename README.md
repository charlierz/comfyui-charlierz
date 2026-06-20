# comfyui-charlierz

Personal ComfyUI custom nodes and browser extensions for image-prompt authoring, llama.cpp chat calls, matting helpers, scaling utilities, and token estimates.

## Features

### llama.cpp nodes

- `Llama.cpp Chat` calls an OpenAI-compatible llama.cpp server at `/v1/chat/completions`.
- `Llama.cpp Vision Chat` sends a ComfyUI image as a PNG data URL and validates image support using `/models` metadata.
- Frontend buttons reload model choices from `/models` metadata and unload the selected model.

### Prompt Helper

Adds a structured prompt node and frontend autocomplete for Danbooru-style tags. This node is intentionally Danbooru-focused: its bundled data, related-tag lookup, character-tag helper, and wiki links are built around Danbooru tag conventions.

- `Prompt Helper` combines configured prompt sections into:
  - `prompt`: plain text sections joined with blank lines
  - `structured_prompt`: JSON object keyed by prompt category
- Prompt Helper categories, order, and autocomplete sources are configured in `data/prompt_categories.json`.
- `Prompt Helper Fill Request` builds an LLM instruction for filling selected prompt categories.
- `Prompt Helper Fill Apply` merges an LLM JSON response back into the structured prompt.
- Browser extension behavior:
  - autocomplete in text inputs using curated/generated tag and wildcard data
  - category-prioritized suggestions inside `Prompt Helper`
  - related-tag popups from generated relationship TSVs, with category/mismatch hints
  - character-tag popups for known characters
  - Danbooru wiki quick links
  - `Prompt Catalog` access from Prompt Helper for category-aware tag/wildcard insertion

The frontend extension wraps ComfyUI's `ComfyWidgets.STRING` factory so it can attach autocomplete to the actual textarea/input elements as ComfyUI creates them. `Prompt Helper` fields from `data/prompt_categories.json` get category-aware autocomplete, wildcard search, wildcard reference previews, related-tag behavior, and Prompt Catalog insertion; other editable string widgets get general Danbooru tag autocomplete.

Prompt Catalog insertions in `Prompt Helper` route known tags/wildcards to their configured category textarea and fall back to the focused textarea when unknown. Saved `.txt` prompts normally insert as plain text into the focused category; the Prompts tab has a `Decompose into categories` toggle that splits comma/newline-delimited known tags and wildcards into matching category fields while skipping entries already present.

### Wildcards, expansion, and freezing

Wildcard nodes expand curated wildcard references into prompt text. They are independent of Impact Pack and use a small documented syntax inspired by Impact/Dynamic Prompts rather than exact third-party compatibility.

`Wildcard Expander` is the lean expansion node:

- `wildcard_text`: prompt template containing wildcard/variant syntax. If this input is valid JSON, string values are expanded and JSON structure is preserved.
- `weight_mode`: tag-pool sampling weight transform: `sqrt` (default), `count`, `log`, or `random`.
- `seed`: deterministic random seed for generation, with ComfyUI `control_after_generate` support.
- output `processed_text`: expanded text or expanded JSON text.

`Prompt Freeze` is a generic text freeze node:

- `live_text`: connected live text input
- `frozen_text`: last captured live text
- `frozen`: when off, outputs `live_text` and updates `frozen_text`; when on, outputs `frozen_text` without updating it

Typical structured wildcard workflow:

```text
Prompt Helper.prompt or structured_prompt
  -> Wildcard Expander.processed_text
  -> Prompt Freeze.text
  -> sampler positive prompt
```

`Wildcard Processor` is the older all-in-one node that keeps preview/freeze UI inline:

- `wildcard_text`: prompt template containing wildcard/variant syntax.
- `preview_text`: latest preview text; when frozen, this is the final output text.
- `weight_mode`: `sqrt` (default), `count`, `log`, or `random`.
- `frozen`: when off, expands `wildcard_text`; when on, outputs `preview_text` exactly.
- `seed`: deterministic random seed for generation, with ComfyUI `control_after_generate` support.
- output `processed_text`: generated or frozen prompt text.

Frontend buttons on wildcard nodes:

- `Use Last Queued Seed`: sets `seed` to the previously executed seed and sets `control_after_generate` to `fixed`.
- `Prompt Catalog` on `Wildcard Processor`: opens the catalog dialog.
- `Preview / Reroll` on `Wildcard Processor`: randomizes `seed`, expands local `wildcard_text`, and writes the result to `preview_text`. This preview uses the node widget text, so prefer `Wildcard Expander` for connected Prompt Helper inputs.

Saved prompts are editable through the Prompt Catalog `Prompts` tab and stored as plain text files under `data/prompts/**/*.txt`. Prompt IDs are path-based, case-insensitive, normalize spaces to underscores, and use the file path without `.txt`:

```text
data/prompts/portraits/soft_lighting.txt -> portraits/soft_lighting
```

The prompt editor supports tag/wildcard autocomplete, click-to-preview for wildcard references, create/save/save-as/rename/delete actions, `New From Current`, and direct expansion preview. Saved prompts are inserted as text snippets; they are not referenced at processing time.

Wildcard pools are backed by curated tag-pool TSVs under `data/tag_pools/**/*.tsv`. Each pool row is a prompt tag; the optional `count` column powers weighted sampling. Wildcard IDs are path-based, case-insensitive, and normalize spaces to underscores. For example:

```text
data/tag_pools/body/hair/color.tsv -> __body/hair/color__
```

Supported syntax:

```text
__path/name__              # sample one tag from a wildcard pool
__path/*__                 # sample from matching one-level files
__path/**__                # sample recursively from descendant files
{red|blue|green}           # inline variant
{0.2::rare|1.0::common}    # weighted variant options
{2$$red|blue|green}        # pick two options
{1-3$$red|blue|green}      # pick a ranged count
{2$$, $$red|blue|green}    # pick two with a custom separator
```

Tags and selected variant options are expanded recursively, so wildcards can contain variants and variants can contain wildcard references. Expansion has cycle and depth protection. Missing, cyclic, empty, or depth-limited wildcards insert visible markers into `processed_text` and log diagnostics.

Escaping uses backslashes for literal syntax characters where needed, such as `\{`, `\}`, `\|`, and `\_`.

Future prompt-catalog enhancements may add prompt-reference syntax in `wildcard_text` and saved-prompt autocomplete results. Both are intentionally out of scope for the current snippet-based prompt workflow.

Curated prompt tag pools live under `data/tag_pools/**/*.tsv`. Each pool uses space-form tags and source counts:

```tsv
tag	count
blue eyes	1265728
mysterious aura	
```

Pool files do not store related tags. Generated relationship data, including character relationships, lives separately.

### Utility nodes

- `Background Color (Matting)` composites images over an RGB background using a mask.
- `Scale Dimensions` scales width/height with floor, ceil, or nearest rounding.
- `Estimate Text Tokens` returns rough token estimates using character, tag, and word heuristics.

## Installation

Clone this repository into `ComfyUI/custom_nodes` and restart ComfyUI:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/charlierz/comfyui-charlierz.git
```

No separate Python package installation is currently defined.

## Requirements

- ComfyUI custom node environment.
  - Tested with ComfyUI `v0.22.0-62-g4af9a472`.
- No extra Python dependencies beyond ComfyUI's requirements (`torch`, `Pillow`, and `aiohttp`).
- ComfyUI frontend APIs: `/scripts/app.js`, `/scripts/api.js`, `/scripts/widgets.js`.
- For llama.cpp nodes: a running llama.cpp server with OpenAI-compatible chat completions.
  - Tested with `llama-server` version `657 (0253fb2)`.
  - Uses `/v1/chat/completions`, `/models`, and `/models/unload`.
  - Sends `reasoning` and `chat_template_kwargs.enable_thinking` in chat payloads.
- On startup, the plugin checks for generated tag files. If any are missing, it downloads the ignored Danbooru source CSVs and regenerates the missing runtime files.
- To skip automatic tag-data bootstrap, set `COMFYUI_CHARLIERZ_SKIP_TAG_BOOTSTRAP=1` before starting ComfyUI.
- For manual regeneration details, follow `data/TAG_GENERATION.md`.

## Data files

The prompt helper/catalog uses checked-in curated/generated data under `data/`:

- `tag_pools/**/*.tsv` — curated prompt pools for tag membership, counts, sampling, and same-pool relatedness
- `tag_entities/characters.tsv`, `tag_entities/franchises.tsv` — generated entity registries for autocomplete/ranking
- `tag_relationships/character_tags.tsv` — generated character related-tag overlay
- future `tag_relationships/related_tags.tsv` — generated non-character related-tag overlay

Legacy/generated Danbooru files may still exist during migration, but are not the target source-of-truth model:

- `general.txt`, `copyrights.txt`
- `tag_categories/*.txt`
- `tag_category_cooccurrence/<metric>/*.tsv`

Large source CSVs are intentionally ignored by git and downloaded on demand when generated runtime files are missing:

- `data/danbooru_tags.csv`
- `data/danbooru_tags_cooccurrence.csv`

For tag-pool curation rules, see `data/TAG_POOLS.md`. For generation/import notes, see `data/TAG_GENERATION.md`.

Credit: source CSVs come from [`newtextdoc1111/danbooru-tag-csv`](https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv). Some checked-in/generated files are derived from that dataset plus this repository's curated pools.
