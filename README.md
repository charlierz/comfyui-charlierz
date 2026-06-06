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
  - autocomplete in text inputs using `data/general.txt`
  - category-prioritized suggestions inside `Prompt Helper`
  - related-tag popups from generated cooccurrence TSVs
  - character-tag popups for known characters
  - Danbooru wiki quick links

The frontend extension wraps ComfyUI's `ComfyWidgets.STRING` factory so it can attach autocomplete to the actual textarea/input elements as ComfyUI creates them. `Prompt Helper` category fields get category-aware autocomplete and related-tag behavior; other editable string widgets get general Danbooru tag autocomplete.

Prompt categories are curated in `data/tag_categories/*.txt`:

- `style_quality`
- `themes_roles`
- `appearance_anatomy`
- `clothing_accessories`
- `actions_poses`
- `expressions`
- `scene_background`

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

The prompt helper uses checked-in generated/curated data under `data/`:

- `general.txt`, `copyrights.txt`, `characters.tsv`
- `tag_categories/*.txt`
- `tag_category_cooccurrence/<metric>/*.tsv`

Large source CSVs are intentionally ignored by git:

- `data/danbooru_tags.csv`
- `data/danbooru_tags_cooccurrence.csv`

If you want to recreate or update tag files, follow `data/TAG_GENERATION.md` for the download and generation workflow.

Credit: source CSVs come from [`newtextdoc1111/danbooru-tag-csv`](https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv). The checked-in tag files are derived from that dataset plus this repository's curated categories.
