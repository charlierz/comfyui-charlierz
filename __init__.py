from .modules.tag_bootstrap import ensure_generated_tag_data

try:
    ensure_generated_tag_data()
except Exception as e:
    print(f"[comfyui-charlierz] Tag data bootstrap failed: {e}")

from .modules import api
from .nodes.MattingUtils import NODE_CLASS_MAPPINGS as MATTING_NCM
from .nodes.MattingUtils import NODE_DISPLAY_NAME_MAPPINGS as MATTING_NDNM
from .nodes.ScaleUtils import NODE_CLASS_MAPPINGS as SCALE_NCM
from .nodes.ScaleUtils import NODE_DISPLAY_NAME_MAPPINGS as SCALE_NDNM
from .nodes.PromptHelper import NODE_CLASS_MAPPINGS as PROMPT_HELPER_NCM
from .nodes.PromptHelper import NODE_DISPLAY_NAME_MAPPINGS as PROMPT_HELPER_NDNM
from .nodes.LlamaCpp import NODE_CLASS_MAPPINGS as LLAMA_CPP_NCM
from .nodes.LlamaCpp import NODE_DISPLAY_NAME_MAPPINGS as LLAMA_CPP_NDNM
from .nodes.TextUtils import NODE_CLASS_MAPPINGS as TEXT_UTILS_NCM
from .nodes.TextUtils import NODE_DISPLAY_NAME_MAPPINGS as TEXT_UTILS_NDNM
from .nodes.WildcardProcessor import NODE_CLASS_MAPPINGS as WILDCARD_NCM
from .nodes.WildcardProcessor import NODE_DISPLAY_NAME_MAPPINGS as WILDCARD_NDNM
from .nodes.WildcardExpander import NODE_CLASS_MAPPINGS as WILDCARD_EXPANDER_NCM
from .nodes.WildcardExpander import NODE_DISPLAY_NAME_MAPPINGS as WILDCARD_EXPANDER_NDNM
from .nodes.PromptFreeze import NODE_CLASS_MAPPINGS as PROMPT_FREEZE_NCM
from .nodes.PromptFreeze import NODE_DISPLAY_NAME_MAPPINGS as PROMPT_FREEZE_NDNM
from .nodes.AnimaDetailerHooks import NODE_CLASS_MAPPINGS as ANIMA_DETAILER_HOOKS_NCM
from .nodes.AnimaDetailerHooks import (
    NODE_DISPLAY_NAME_MAPPINGS as ANIMA_DETAILER_HOOKS_NDNM,
)
from .nodes.GenPipe import NODE_CLASS_MAPPINGS as GEN_PIPE_NCM
from .nodes.GenPipe import NODE_DISPLAY_NAME_MAPPINGS as GEN_PIPE_NDNM
from .nodes.LoraStack import NODE_CLASS_MAPPINGS as LORA_STACK_NCM
from .nodes.LoraStack import NODE_DISPLAY_NAME_MAPPINGS as LORA_STACK_NDNM

NODE_CLASS_MAPPINGS = {
    **MATTING_NCM,
    **SCALE_NCM,
    **PROMPT_HELPER_NCM,
    **LLAMA_CPP_NCM,
    **TEXT_UTILS_NCM,
    **WILDCARD_NCM,
    **WILDCARD_EXPANDER_NCM,
    **PROMPT_FREEZE_NCM,
    **ANIMA_DETAILER_HOOKS_NCM,
    **GEN_PIPE_NCM,
    **LORA_STACK_NCM,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **MATTING_NDNM,
    **SCALE_NDNM,
    **PROMPT_HELPER_NDNM,
    **LLAMA_CPP_NDNM,
    **TEXT_UTILS_NDNM,
    **WILDCARD_NDNM,
    **WILDCARD_EXPANDER_NDNM,
    **PROMPT_FREEZE_NDNM,
    **ANIMA_DETAILER_HOOKS_NDNM,
    **GEN_PIPE_NDNM,
    **LORA_STACK_NDNM,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
