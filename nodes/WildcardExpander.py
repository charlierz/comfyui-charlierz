from __future__ import annotations

try:
    from ..modules.prompt_catalog import WEIGHT_MODES, expand_wildcards_preserving_json
except ImportError:
    from modules.prompt_catalog import WEIGHT_MODES, expand_wildcards_preserving_json


class WildcardExpander:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "wildcard_text": ("STRING", {"multiline": True, "forceInput": True, "default": ""}),
                "weight_mode": (list(WEIGHT_MODES), {"default": "sqrt"}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("processed_text",)
    FUNCTION = "expand"
    CATEGORY = "charlierz/Prompt"

    def expand(self, wildcard_text: str, seed: int, weight_mode: str = "sqrt"):
        if weight_mode not in WEIGHT_MODES:
            weight_mode = "sqrt"
        seed = int(seed or 0)
        processed_text, _diagnostics = expand_wildcards_preserving_json(
            str(wildcard_text or ""),
            seed=seed,
            weight_mode=weight_mode,  # type: ignore[arg-type]
        )
        return {
            "ui": {"last_seed": [seed]},
            "result": (processed_text,),
        }


NODE_CLASS_MAPPINGS = {"WildcardExpander": WildcardExpander}

NODE_DISPLAY_NAME_MAPPINGS = {"WildcardExpander": "Wildcard Expander"}
