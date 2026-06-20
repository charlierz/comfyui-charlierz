from __future__ import annotations


class PromptFreeze:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "live_text": ("STRING", {"multiline": True, "forceInput": True, "default": ""}),
                "frozen_text": ("STRING", {"multiline": True, "default": ""}),
                "frozen": ("BOOLEAN", {"default": False}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "freeze"
    CATEGORY = "charlierz/Prompt"

    def freeze(
        self,
        live_text: str,
        frozen_text: str,
        frozen: bool,
        unique_id: str | None = None,
    ):
        del unique_id
        live_text = str(live_text or "")
        frozen_text = str(frozen_text or "")

        if frozen:
            return (frozen_text,)

        return {
            "ui": {"captured_text": [live_text]},
            "result": (live_text,),
        }


NODE_CLASS_MAPPINGS = {"PromptFreeze": PromptFreeze}

NODE_DISPLAY_NAME_MAPPINGS = {"PromptFreeze": "Prompt Freeze"}
