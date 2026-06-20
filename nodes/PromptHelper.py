import json
import os
from typing import Any

try:
    from ..modules.tag_data import (
        ENTITY_SOURCE_FILES,
        TAG_POOLS_DIR,
        display_tag,
        prompt_category_ids,
        prompt_category_source_map,
        read_tag_pool_tsv,
        read_tsv_keys,
    )
except ImportError:
    from modules.tag_data import (
        ENTITY_SOURCE_FILES,
        TAG_POOLS_DIR,
        display_tag,
        prompt_category_ids,
        prompt_category_source_map,
        read_tag_pool_tsv,
        read_tsv_keys,
    )


def _category_inputs() -> tuple[str, ...]:
    return prompt_category_ids()


class PromptHelper:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                name: ("STRING", {"multiline": True, "default": ""})
                for name in _category_inputs()
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "structured_prompt")
    FUNCTION = "combine"
    CATEGORY = "charlierz/Prompt"

    def combine(self, **kwargs):
        structured_prompt = {category: str(kwargs.get(category, "")) for category in _category_inputs()}
        return (
            _combine_structured_prompt(structured_prompt),
            json.dumps(structured_prompt, ensure_ascii=False, indent=2),
        )


class PromptHelperFillRequest:
    @classmethod
    def INPUT_TYPES(cls):
        fill_flags = {
            f"fill_{category}": ("BOOLEAN", {"default": False})
            for category in _category_inputs()
        }
        return {
            "required": {
                "structured_prompt": ("STRING", {"multiline": True, "default": "{}"}),
                **fill_flags,
                "clear_selected_categories": ("BOOLEAN", {"default": False}),
                "include_category_tags": ("BOOLEAN", {"default": False}),
                "max_tags_per_category": ("INT", {"default": 500, "min": 0, "max": 10000}),
                "user_prompt": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("llm_prompt",)
    FUNCTION = "build"
    CATEGORY = "charlierz/Prompt"

    def build(self, structured_prompt, clear_selected_categories, include_category_tags, max_tags_per_category, user_prompt, **kwargs):
        selected_categories = _selected_categories(kwargs)
        if not selected_categories:
            raise ValueError("Select at least one category to fill")

        original = _parse_structured_prompt(structured_prompt)
        normalized = _normalize_structured_prompt(original)
        if clear_selected_categories:
            for category in selected_categories:
                normalized[category] = ""
        category_list = "\n".join(f"- {category}" for category in selected_categories)
        user_prompt = user_prompt.strip()

        prompt = f"""You are completing a structured image prompt.

User request:
{user_prompt or "Fill the selected categories in a way that fits the existing prompt."}

Current structured prompt JSON:
{json.dumps(normalized, ensure_ascii=False, indent=2)}

Fill only these categories:
{category_list}

Rules:
- Return JSON only. Do not use markdown fences.
- Return only the selected category keys, not the full schema.
- Do not include unselected categories in the response.
- For selected categories, fill empty values or improve weak values.
- Keep values concise, comma-separated, and suitable for an image generation prompt."""

        if include_category_tags:
            prompt += (
                "\n\nPopular Danbooru-style reference tags for selected categories:"
                "\nThese reference tags are examples and inspiration, not a closed list."
                " You may use other suitable Danbooru-style tags or natural descriptions when they fit better."
            )
            for category in selected_categories:
                tags = _read_category_tags(category, max_tags_per_category)
                prompt += f"\n\n{category}:\n{', '.join(tags)}"

        return (prompt,)


class PromptHelperFillApply:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_structured_prompt": ("STRING", {"multiline": True, "default": "{}"}),
            },
            "optional": {
                "fill_response": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "structured_prompt")
    FUNCTION = "apply"
    CATEGORY = "charlierz/Prompt"

    def apply(self, original_structured_prompt, fill_response=""):
        original = _normalize_structured_prompt(_parse_structured_prompt(original_structured_prompt))

        if not fill_response.strip():
            result = original
        else:
            response = _normalize_structured_prompt(
                _parse_structured_prompt(fill_response),
                include_missing=False,
            )
            result = {**original, **response}

        return (_combine_structured_prompt(result), json.dumps(result, ensure_ascii=False, indent=2))


def _selected_categories(values: dict[str, Any]) -> list[str]:
    return [category for category in _category_inputs() if values.get(f"fill_{category}")]


def _read_category_tags(category: str, max_tags: int) -> list[str]:
    categories = prompt_category_source_map()
    prompt_category = categories.get(category)
    if prompt_category is None:
        raise ValueError(f"Unknown category: {category}")

    tags: list[str] = []
    for source in prompt_category.sources:
        if source.startswith("tag_pools/"):
            pool = source.removeprefix("tag_pools/")
            dir_path = os.path.join(TAG_POOLS_DIR, pool)
            if not os.path.isdir(dir_path):
                continue
            for root, _dirs, files in os.walk(dir_path):
                for filename in sorted(files):
                    if not filename.endswith(".tsv"):
                        continue
                    for tag, _count in read_tag_pool_tsv(os.path.join(root, filename)):
                        tags.append(display_tag(tag))
        elif source in ENTITY_SOURCE_FILES:
            tags.extend(display_tag(tag) for tag in read_tsv_keys(ENTITY_SOURCE_FILES[source]))

    return _limit_tags(list(dict.fromkeys(tags)), max_tags)


def _limit_tags(tags: list[str], max_tags: int) -> list[str]:
    if max_tags > 0:
        return tags[:max_tags]
    return tags


def _parse_structured_prompt(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_json_object(text))

    if not isinstance(parsed, dict):
        raise ValueError("Structured prompt must be a JSON object")
    return parsed


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Could not find a JSON object in fill response")
    return text[start : end + 1]


def _normalize_structured_prompt(
    structured_prompt: dict[str, Any],
    include_missing: bool = True,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for category in _category_inputs():
        if category in structured_prompt:
            value = structured_prompt[category]
            normalized[category] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        elif include_missing:
            normalized[category] = ""
    return normalized


def _combine_structured_prompt(structured_prompt: dict[str, str]) -> str:
    return "\n\n".join(structured_prompt.get(category, "") for category in _category_inputs())


NODE_CLASS_MAPPINGS = {
    "PromptHelper": PromptHelper,
    "PromptHelperFillRequest": PromptHelperFillRequest,
    "PromptHelperFillApply": PromptHelperFillApply,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptHelper": "Prompt Helper",
    "PromptHelperFillRequest": "Prompt Helper Fill Request",
    "PromptHelperFillApply": "Prompt Helper Fill Apply",
}
