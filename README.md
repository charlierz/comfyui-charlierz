# comfyui-charlierz

Personal ComfyUI custom nodes and browser extensions for image-prompt authoring, llama.cpp chat calls, matting helpers, scaling utilities, and token estimates.

## Features

### llama.cpp nodes

- `Llama.cpp Chat` calls an OpenAI-compatible llama.cpp server at `/v1/chat/completions`.
- `Llama.cpp Vision Chat` sends a ComfyUI image as a PNG data URL and validates image support using `/models` metadata.
- Frontend buttons reload model choices from `/models` metadata and unload the selected model.

### Prompt Helper

Adds a structured prompt node and frontend autocomplete for Danbooru-style tags. This node is intentionally Danbooru-focused: its bundled data, related-tag lookup, character-tag helper, and wiki links are built around Danbooru tag conventions.

- `Prompt Helper` combines prompt sections into:
  - `prompt`: plain text sections joined with blank lines
  - `structured_prompt`: JSON object keyed by prompt category
- `Prompt Helper Fill Request` builds an LLM instruction for filling selected prompt categories.
- `Prompt Helper Fill Apply` merges an LLM JSON response back into the structured prompt.
- Browser extension behavior:
  - autocomplete in text inputs using curated/generated tag data
  - category-prioritized suggestions inside `Prompt Helper`
  - related-tag popups from generated relationship TSVs
  - character-tag popups for known characters
  - Danbooru wiki quick links

The frontend extension wraps ComfyUI's `ComfyWidgets.STRING` factory so it can attach autocomplete to the actual textarea/input elements as ComfyUI creates them. `Prompt Helper` category fields get category-aware autocomplete and related-tag behavior; other editable string widgets get general Danbooru tag autocomplete.

### Wildcard Processor

`Wildcard Processor` expands curated wildcard references into prompt text. It is independent of Impact Pack and uses a small documented syntax inspired by Impact/Dynamic Prompts rather than exact third-party compatibility.

Inputs:

- `wildcard_text`: prompt template containing wildcard/variant syntax.
- `preview_text`: latest preview text; when frozen, this is the final output text.
- `frozen`: when off, expands `wildcard_text`; when on, outputs `preview_text` exactly.
- `seed`: deterministic random seed for generation.

Output:

- `processed_text`: generated or frozen prompt text.

Frontend buttons:

- `Browse Wildcards`: opens a nested wildcard tree plus search/preview/insert browser for wildcards, entries, and tags. Selecting a wildcard shows its literal entries; click an entry to insert it as prompt text, or use `Insert` to insert the selected wildcard reference/result. Browser insertions are comma-separated from existing `wildcard_text`.
- `Preview / Reroll`: randomizes `seed`, expands `wildcard_text` through the backend processor, and writes the result to `preview_text`.

Freeze workflow:

1. Keep `frozen` off while experimenting.
2. Click `Preview / Reroll` until `preview_text` contains a result to keep.
3. Turn `frozen` on. The node now outputs `preview_text` exactly.
4. Turn `frozen` off to resume generation from `wildcard_text`.

Wildcard files live under `data/wildcards`. The executable first-class format is plain `.txt`; each non-empty, non-comment line is one entry. Full-line `#` comments and blank lines are ignored. YAML/JSON wildcard files are not executed initially.

Wildcard IDs are path-based, case-insensitive, and normalize spaces to underscores. For example:

```text
data/wildcards/appearance/hair/color.txt -> __appearance/hair/color__
```

Supported syntax:

```text
__path/name__              # sample one entry from a wildcard file
__path/*__                 # sample from matching one-level files
__path/**__                # sample recursively from descendant files
{red|blue|green}           # inline variant
{0.2::rare|1.0::common}    # weighted variant options
{2$$red|blue|green}        # pick two options
{1-3$$red|blue|green}      # pick a ranged count
{2$$, $$red|blue|green}    # pick two with a custom separator
```

Entries and selected variant options are expanded recursively, so wildcards can contain variants and variants can contain wildcard references. Expansion has cycle and depth protection. Missing, cyclic, empty, or depth-limited wildcards insert visible markers into `processed_text` and log diagnostics.

Escaping uses backslashes for literal syntax characters where needed, such as `\{`, `\}`, `\|`, and `\_`.

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
- For normal Prompt Helper use, generated tag files are checked in.
- For regenerating tag files, local source CSVs are required; follow `data/TAG_GENERATION.md`.

## Data files

The prompt helper/catalog uses checked-in curated/generated data under `data/`:

- `tag_pools/**/*.tsv` — curated tag pools, source of truth for tag membership and counts
- `characters.tsv` — generated character relationship data during transition
- future `tag_relationships/*.tsv` — generated related-tag relationship data

Legacy/generated Danbooru files may still exist during migration, but are not the target source-of-truth model:

- `general.txt`, `copyrights.txt`
- `tag_categories/*.txt`
- `tag_category_cooccurrence/<metric>/*.tsv`

Large source CSVs are intentionally ignored by git:

- `data/danbooru_tags.csv`
- `data/danbooru_tags_cooccurrence.csv`

For tag-pool curation rules, see `data/TAG_POOLS.md`. For generation/import notes, see `data/TAG_GENERATION.md`.

Credit: source CSVs come from [`newtextdoc1111/danbooru-tag-csv`](https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv). Some checked-in/generated files are derived from that dataset plus this repository's curated pools.
