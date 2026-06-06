import math


class EstimateTextTokens:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = ("INT", "INT", "INT", "STRING")
    RETURN_NAMES = (
        "chars_div_4_tokens",
        "danbooru_tags_x4_tokens",
        "words_x1_3_tokens",
        "summary",
    )
    FUNCTION = "estimate"
    CATEGORY = "charlierz/Utils"
    OUTPUT_NODE = True

    def estimate(self, text):
        chars_div_4 = math.ceil(len(text) / 4)
        danbooru_tags_x4 = len(_split_tags(text)) * 4
        words_x1_3 = math.ceil(len(text.split()) * 1.3)

        summary = (
            f"chars_div_4: {chars_div_4} tokens ({len(text)} chars)\n"
            f"danbooru_tags_x4: {danbooru_tags_x4} tokens ({len(_split_tags(text))} tags)\n"
            f"words_x1_3: {words_x1_3} tokens ({len(text.split())} words)"
        )
        return {
            "ui": {"text": [summary]},
            "result": (chars_div_4, danbooru_tags_x4, words_x1_3, summary),
        }


def _split_tags(text: str) -> list[str]:
    return [tag.strip() for tag in text.replace("\n", ",").split(",") if tag.strip()]


NODE_CLASS_MAPPINGS = {"EstimateTextTokens": EstimateTextTokens}

NODE_DISPLAY_NAME_MAPPINGS = {"EstimateTextTokens": "Estimate Text Tokens"}
