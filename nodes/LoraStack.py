import folder_paths
from nodes import LoraLoader


class AnyType(str):
    def __ne__(self, value):
        return False


any_type = AnyType("*")


class FlexibleOptionalInputType(dict):
    def __init__(self, input_type, data=None):
        super().__init__()
        self.input_type = input_type
        self.data = data or {}
        self.update(self.data)

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        return (self.input_type,)

    def __contains__(self, key):
        return True


class PowerLoraStack:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": FlexibleOptionalInputType(
                any_type,
                {
                    "optional_lora_stack": ("LORA_STACK",),
                },
            ),
        }

    RETURN_TYPES = ("LORA_STACK",)
    RETURN_NAMES = ("lora_stack",)
    FUNCTION = "stack"
    CATEGORY = "charlierz/loaders"

    def stack(self, optional_lora_stack=None, **kwargs):
        loras = []

        if optional_lora_stack:
            loras.extend(lora for lora in optional_lora_stack if _is_valid_stack_entry(lora))

        for key in _sorted_lora_keys(kwargs):
            value = kwargs[key]
            if not isinstance(value, dict):
                continue

            if not value.get("on", True):
                continue

            lora_name = value.get("lora")
            if not lora_name or lora_name == "None":
                continue

            model_strength = float(value.get("strength", 1.0) or 0.0)
            clip_strength = value.get("strengthTwo")
            clip_strength = model_strength if clip_strength is None else float(clip_strength or 0.0)

            if model_strength == 0 and clip_strength == 0:
                continue

            loras.append((lora_name, model_strength, clip_strength))

        return (loras or None,)


class ApplyLoraStack:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_stack": ("LORA_STACK",),
                "model": ("MODEL",),
            },
            "optional": {
                "optional_clip": ("CLIP",),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("model", "clip")
    FUNCTION = "apply"
    CATEGORY = "charlierz/loaders"

    def apply(self, lora_stack, model, optional_clip=None):
        clip = optional_clip
        if not lora_stack:
            return (model, clip)

        for entry in lora_stack:
            parsed = _parse_stack_entry(entry)
            if parsed is None:
                continue

            lora_name, model_strength, clip_strength = parsed
            if model_strength == 0 and clip_strength == 0:
                continue

            resolved_lora = _resolve_lora_name(lora_name)
            if resolved_lora is None:
                print(f"[comfyui-charlierz] LoRA not found: {lora_name}")
                continue

            model, clip = LoraLoader().load_lora(
                model,
                clip,
                resolved_lora,
                model_strength,
                clip_strength if clip is not None else 0,
            )

        return (model, clip)


def _sorted_lora_keys(kwargs):
    def sort_key(key):
        suffix = str(key).split("_", 1)[-1]
        return int(suffix) if suffix.isdigit() else 10_000

    return sorted((key for key in kwargs if str(key).startswith("lora_")), key=sort_key)


def _is_valid_stack_entry(entry):
    parsed = _parse_stack_entry(entry)
    return parsed is not None and parsed[0] != "None"


def _parse_stack_entry(entry):
    if isinstance(entry, dict):
        lora_name = entry.get("lora_name") or entry.get("lora")
        model_strength = entry.get("model_strength", entry.get("strength", 1.0))
        clip_strength = entry.get("clip_strength", entry.get("strengthTwo", model_strength))
    elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
        lora_name, model_strength, clip_strength = entry[:3]
    else:
        return None

    if not lora_name or lora_name == "None":
        return None

    return (str(lora_name), float(model_strength or 0.0), float(clip_strength or 0.0))


def _resolve_lora_name(lora_name):
    if folder_paths.get_full_path("loras", lora_name) is not None:
        return lora_name

    basename = str(lora_name).split("/")[-1]
    for candidate in folder_paths.get_filename_list("loras"):
        if candidate == basename or candidate.split("/")[-1] == basename:
            return candidate

    return None


NODE_CLASS_MAPPINGS = {
    "CharlierzPowerLoraStack": PowerLoraStack,
    "CharlierzApplyLoraStack": ApplyLoraStack,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CharlierzPowerLoraStack": "Power Lora Stack",
    "CharlierzApplyLoraStack": "Apply Lora Stack",
}
