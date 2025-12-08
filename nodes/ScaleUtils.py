import math


class ScaleDimensions:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 512, "min": 1, "max": 16384}),
                "height": ("INT", {"default": 512, "min": 1, "max": 16384}),
                "scale": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.01, "max": 10.0, "step": 0.01},
                ),
                "rounding": (["floor", "ceil", "nearest"], {"default": "nearest"}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("scaled_width", "scaled_height")
    FUNCTION = "scale"
    CATEGORY = "charlierz/Utils"

    def scale(self, width, height, scale, rounding):
        sw = width * scale
        sh = height * scale
        if rounding == "floor":
            sw = math.floor(sw)
            sh = math.floor(sh)
        elif rounding == "ceil":
            sw = math.ceil(sw)
            sh = math.ceil(sh)
        else:  # nearest
            sw = round(sw)
            sh = round(sh)
        return (int(sw), int(sh))


NODE_CLASS_MAPPINGS = {"ScaleDimensions": ScaleDimensions}

NODE_DISPLAY_NAME_MAPPINGS = {"ScaleDimensions": "Scale Dimensions"}
