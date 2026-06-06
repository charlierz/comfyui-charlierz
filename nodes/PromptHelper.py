import json
import os
from typing import Any


DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
TAG_CATEGORIES_DIR = os.path.join(DATA_DIR, "tag_categories")

CATEGORY_TAG_FILES = {
    "style_quality": "style_quality.txt",
    "themes_roles": "themes_roles.txt",
    "appearance_anatomy": "appearance_anatomy.txt",
    "clothing_accessories": "clothing_accessories.txt",
    "actions_poses": "actions_poses.txt",
    "expressions": "expressions.txt",
    "scene_background": "scene_background.txt",
}


CATEGORY_INPUTS = (
    "style_quality",
    "themes_roles",
    "appearance_anatomy",
    "clothing_accessories",
    "actions_poses",
    "expressions",
    "scene_background",
)


class PromptHelper:
    CATEGORY_INPUTS = CATEGORY_INPUTS

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                name: ("STRING", {"multiline": True, "default": ""})
                for name in cls.CATEGORY_INPUTS
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "structured_prompt")
    FUNCTION = "combine"
    CATEGORY = "charlierz/Prompt"

    def combine(
        self,
        style_quality,
        themes_roles,
        appearance_anatomy,
        clothing_accessories,
        actions_poses,
        expressions,
        scene_background,
    ):
        structured_prompt = {
            "style_quality": style_quality,
            "themes_roles": themes_roles,
            "appearance_anatomy": appearance_anatomy,
            "clothing_accessories": clothing_accessories,
            "actions_poses": actions_poses,
            "expressions": expressions,
            "scene_background": scene_background,
        }
        parts = tuple(structured_prompt.values())
        return (
            "\n\n".join(parts),
            json.dumps(structured_prompt, ensure_ascii=False, indent=2),
        )


class PromptHelperFillRequest:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "structured_prompt": ("STRING", {"multiline": True, "default": "{}"}),
                "fill_style_quality": ("BOOLEAN", {"default": False}),
                "fill_themes_roles": ("BOOLEAN", {"default": False}),
                "fill_appearance_anatomy": ("BOOLEAN", {"default": False}),
                "fill_clothing_accessories": ("BOOLEAN", {"default": False}),
                "fill_actions_poses": ("BOOLEAN", {"default": False}),
                "fill_expressions": ("BOOLEAN", {"default": False}),
                "fill_scene_background": ("BOOLEAN", {"default": False}),
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

    def build(
        self,
        structured_prompt,
        fill_style_quality,
        fill_themes_roles,
        fill_appearance_anatomy,
        fill_clothing_accessories,
        fill_actions_poses,
        fill_expressions,
        fill_scene_background,
        clear_selected_categories,
        include_category_tags,
        max_tags_per_category,
        user_prompt,
    ):
        selected_categories = _selected_categories(
            fill_style_quality,
            fill_themes_roles,
            fill_appearance_anatomy,
            fill_clothing_accessories,
            fill_actions_poses,
            fill_expressions,
            fill_scene_background,
        )
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


def _selected_categories(*flags: bool) -> list[str]:
    return [category for category, enabled in zip(CATEGORY_INPUTS, flags, strict=True) if enabled]


def _read_category_tags(category: str, max_tags: int) -> list[str]:
    filename = CATEGORY_TAG_FILES.get(category)
    if filename is None:
        raise ValueError(f"Unknown category: {category}")

    path = os.path.join(TAG_CATEGORIES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        tags = [
            tag.strip().replace("_", " ")
            for tag in f.read().replace("\n", ",").split(",")
            if tag.strip()
        ]

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
    for category in CATEGORY_INPUTS:
        if category in structured_prompt:
            value = structured_prompt[category]
            normalized[category] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        elif include_missing:
            normalized[category] = ""
    return normalized


def _combine_structured_prompt(structured_prompt: dict[str, str]) -> str:
    return "\n\n".join(structured_prompt.get(category, "") for category in CATEGORY_INPUTS)


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
