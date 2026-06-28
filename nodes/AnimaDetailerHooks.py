import sys
from pathlib import Path

import folder_paths
import nodes

try:
    from impact.hooks import DetailerHook
except ImportError:
    impact_modules = Path(__file__).resolve().parents[2] / "comfyui-impact-pack" / "modules"
    sys.path.append(str(impact_modules))
    from impact.hooks import DetailerHook


class AnimaLLLiteDetailerHook(DetailerHook):
    """Apply Anima ControlNet-LLLite inside Impact detailer sampling.

    Impact's detailer owns the per-segment crop and mask. This hook captures that
    crop/mask in post_upscale(), then patches the MODEL in pre_ksample() so the
    LLLite guidance is aligned with the detailer's internal sampling region.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lllite_name": (folder_paths.get_filename_list("controlnet"),),
                "strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "start_percent": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "end_percent": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "preserve_wrapper": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("DETAILER_HOOK",)
    RETURN_NAMES = ("detailer_hook",)
    FUNCTION = "make_hook"
    CATEGORY = "charlierz/detailer"

    def make_hook(self, lllite_name, strength, start_percent, end_percent, preserve_wrapper=True):
        return (_AnimaLLLiteDetailerHook(lllite_name, strength, start_percent, end_percent, preserve_wrapper),)


class _AnimaLLLiteDetailerHook(DetailerHook):
    def __init__(self, lllite_name, strength, start_percent, end_percent, preserve_wrapper=True):
        super().__init__()
        self.lllite_name = lllite_name
        self.strength = strength
        self.start_percent = start_percent
        self.end_percent = end_percent
        self.preserve_wrapper = preserve_wrapper
        self._crop_image = None
        self._crop_mask = None

    def post_upscale(self, pixels, mask=None):
        self._crop_image = pixels
        self._crop_mask = mask
        return pixels

    def pre_ksample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, upscaled_latent, denoise):
        if self._crop_image is None:
            return model, seed, steps, cfg, sampler_name, scheduler, positive, negative, upscaled_latent, denoise

        apply_cls = nodes.NODE_CLASS_MAPPINGS.get("AnimaLLLiteApply")
        if apply_cls is None:
            raise RuntimeError("AnimaLLLiteApply is not registered. Is ComfyUI-Anima-LLLite enabled?")

        patched_model = apply_cls().apply(
            model=model,
            lllite_name=self.lllite_name,
            image=self._crop_image,
            strength=self.strength,
            start_percent=self.start_percent,
            end_percent=self.end_percent,
            preserve_wrapper=self.preserve_wrapper,
            mask=self._crop_mask,
        )[0]

        return patched_model, seed, steps, cfg, sampler_name, scheduler, positive, negative, upscaled_latent, denoise


NODE_CLASS_MAPPINGS = {
    "CharlierzAnimaLLLiteDetailerHook": AnimaLLLiteDetailerHook,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CharlierzAnimaLLLiteDetailerHook": "Anima LLLite Detailer Hook",
}
