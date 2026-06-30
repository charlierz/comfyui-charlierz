import comfy.samplers


class MakeGenPipe:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
            }
        }

    RETURN_TYPES = ("GEN_PIPE",)
    RETURN_NAMES = ("gen_pipe",)
    FUNCTION = "make"
    CATEGORY = "charlierz/pipe"

    def make(self, model, clip, vae, positive, negative, steps, cfg, sampler_name, scheduler):
        return (
            {
                "model": model,
                "clip": clip,
                "vae": vae,
                "positive": positive,
                "negative": negative,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
            },
        )


class UnpackGenPipe:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"gen_pipe": ("GEN_PIPE",)}}

    RETURN_TYPES = (
        "MODEL",
        "CLIP",
        "VAE",
        "CONDITIONING",
        "CONDITIONING",
        "INT",
        "FLOAT",
        comfy.samplers.KSampler.SAMPLERS,
        comfy.samplers.KSampler.SCHEDULERS,
    )
    RETURN_NAMES = (
        "model",
        "clip",
        "vae",
        "positive",
        "negative",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
    )
    FUNCTION = "unpack"
    CATEGORY = "charlierz/pipe"

    def unpack(self, gen_pipe):
        return (
            gen_pipe["model"],
            gen_pipe["clip"],
            gen_pipe["vae"],
            gen_pipe["positive"],
            gen_pipe["negative"],
            gen_pipe["steps"],
            gen_pipe["cfg"],
            gen_pipe["sampler_name"],
            gen_pipe["scheduler"],
        )


LANPAINT_SAMPLERS = [
    "euler",
    "euler_ancestral",
    "heun",
    "heunpp2",
    "dpm_2",
    "dpm_2_ancestral",
    "dpm_fast",
    "dpmpp_sde",
    "dpmpp_sde_gpu",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu",
    "dpmpp_3m_sde",
    "dpmpp_3m_sde_gpu",
    "ddpm",
    "deis",
    "res_multistep",
    "res_multistep_ancestral",
    "gradient_estimation",
    "er_sde",
    "seeds_2",
    "seeds_3",
]


class UnpackGenPipeForLanPaint(UnpackGenPipe):
    RETURN_TYPES = (
        "MODEL",
        "CLIP",
        "VAE",
        "CONDITIONING",
        "CONDITIONING",
        "INT",
        "FLOAT",
        LANPAINT_SAMPLERS,
        comfy.samplers.KSampler.SCHEDULERS,
    )
    CATEGORY = "charlierz/pipe"


class EditGenPipe:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "gen_pipe": ("GEN_PIPE",),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
            }
        }

    RETURN_TYPES = ("GEN_PIPE",)
    RETURN_NAMES = ("gen_pipe",)
    FUNCTION = "edit"
    CATEGORY = "charlierz/pipe"

    def edit(self, gen_pipe, steps, cfg, sampler_name, scheduler):
        edited = dict(gen_pipe)
        edited.update(
            {
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
            }
        )
        return (edited,)


NODE_CLASS_MAPPINGS = {
    "CharlierzMakeGenPipe": MakeGenPipe,
    "CharlierzUnpackGenPipe": UnpackGenPipe,
    "CharlierzUnpackGenPipeForLanPaint": UnpackGenPipeForLanPaint,
    "CharlierzEditGenPipe": EditGenPipe,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CharlierzMakeGenPipe": "Make Gen Pipe",
    "CharlierzUnpackGenPipe": "Unpack Gen Pipe",
    "CharlierzUnpackGenPipeForLanPaint": "Unpack Gen Pipe for LanPaint",
    "CharlierzEditGenPipe": "Edit Gen Pipe",
}
