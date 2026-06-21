from __future__ import annotations

try:
    from ..modules.prompt_catalog import expand_wildcards
except ImportError:
    from modules.prompt_catalog import expand_wildcards


class WildcardProcessor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "wildcard_text": ("STRING", {"multiline": True, "default": ""}),
                "preview_text": ("STRING", {"multiline": True, "default": ""}),
                "weight_mode": (["count", "sqrt", "log", "random"], {"default": "sqrt"}),
                "frozen": ("BOOLEAN", {"default": False}),
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
    FUNCTION = "process"
    CATEGORY = "charlierz/Prompt"

    def process(self, wildcard_text: str, preview_text: str, weight_mode: str = "sqrt", frozen: bool = False, seed: int = 0):
        if frozen:
            if not preview_text:
                print("[charlierz wildcard] frozen selected with empty preview_text")
            return (preview_text,)

        if weight_mode not in {"count", "sqrt", "log", "random"}:
            weight_mode = "sqrt"
        seed = int(seed or 0)
        processed_text, _diagnostics = expand_wildcards(wildcard_text, seed=seed, weight_mode=weight_mode)
        return {
            "ui": {"last_seed": [seed]},
            "result": (processed_text,),
        }


NODE_CLASS_MAPPINGS = {"WildcardProcessor": WildcardProcessor}

NODE_DISPLAY_NAME_MAPPINGS = {"WildcardProcessor": "Wildcard Processor"}
