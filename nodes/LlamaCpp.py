import base64
import io
import json
import os
import urllib.error
import urllib.request
from typing import Any

from PIL import Image

MODELS_INI_PATH = os.environ.get("CHARLIERZ_LLAMA_CPP_MODELS_INI", "/mnt/workspace/llm/models.ini")


class LlamaCppChat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_url": (
                    "STRING",
                    {"default": "http://127.0.0.1:8080"},
                ),
                "models_ini_path": (
                    "STRING",
                    {"default": MODELS_INI_PATH},
                ),
                "model": (_get_model_choices(MODELS_INI_PATH),),
                "system_prompt": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "user_prompt": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "reasoning": (
                    "BOOLEAN",
                    {"default": False},
                ),
                "seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 0xFFFFFFFF},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 120, "min": 1, "max": 3600},
                ),
                "unload_after_run": (
                    "BOOLEAN",
                    {"default": False},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("response", "usage_json")
    FUNCTION = "chat"
    CATEGORY = "charlierz/LLM"

    def chat(
        self,
        server_url,
        models_ini_path,
        model,
        system_prompt,
        user_prompt,
        reasoning,
        seed,
        timeout_seconds,
        unload_after_run,
    ):
        server_url = _normalize_server_url(server_url)
        model = model.strip()
        if not model:
            raise ValueError("model is required")

        messages: list[dict[str, Any]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = _build_chat_payload(
            model=model,
            messages=messages,
            reasoning=reasoning,
            seed=seed,
        )

        try:
            response = _post_json(
                f"{server_url}/v1/chat/completions",
                payload,
                timeout_seconds,
            )
            content = _extract_chat_content(response)
            usage = _extract_usage(response)
        finally:
            if unload_after_run:
                _post_json(
                    f"{server_url}/models/unload",
                    {"model": model},
                    min(timeout_seconds, 60),
                )

        return (content, json.dumps(usage, ensure_ascii=False, indent=2))


class LlamaCppVisionChat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "server_url": (
                    "STRING",
                    {"default": "http://127.0.0.1:8080"},
                ),
                "models_ini_path": (
                    "STRING",
                    {"default": MODELS_INI_PATH},
                ),
                "model": (_get_model_choices(MODELS_INI_PATH, vision_only=True),),
                "system_prompt": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "user_prompt": (
                    "STRING",
                    {"multiline": True, "default": "Describe this image."},
                ),
                "reasoning": (
                    "BOOLEAN",
                    {"default": False},
                ),
                "seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 0xFFFFFFFF},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 120, "min": 1, "max": 3600},
                ),
                "unload_after_run": (
                    "BOOLEAN",
                    {"default": False},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("response", "usage_json")
    FUNCTION = "chat"
    CATEGORY = "charlierz/LLM"

    def chat(
        self,
        image,
        server_url,
        models_ini_path,
        model,
        system_prompt,
        user_prompt,
        reasoning,
        seed,
        timeout_seconds,
        unload_after_run,
    ):
        server_url = _normalize_server_url(server_url)
        model = model.strip()
        if not model:
            raise ValueError("model is required")

        _validate_model_supports_image(
            server_url,
            model,
            models_ini_path,
            min(timeout_seconds, 30),
        )
        image_url = _image_to_png_data_url(image)

        messages: list[dict[str, Any]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": user_prompt},
                ],
            }
        )

        payload = _build_chat_payload(
            model=model,
            messages=messages,
            reasoning=reasoning,
            seed=seed,
        )

        try:
            response = _post_json(
                f"{server_url}/v1/chat/completions",
                payload,
                timeout_seconds,
            )
            content = _extract_chat_content(response)
            usage = _extract_usage(response)
        finally:
            if unload_after_run:
                _post_json(
                    f"{server_url}/models/unload",
                    {"model": model},
                    min(timeout_seconds, 60),
                )

        return (content, json.dumps(usage, ensure_ascii=False, indent=2))


def _get_model_choices(models_ini_path: str, vision_only: bool = False) -> list[str]:
    choices = _read_models_ini_choices(models_ini_path, vision_only=vision_only)
    return choices or [""]


def _read_models_ini_choices(path: str, vision_only: bool = False) -> list[str]:
    return [
        display_name
        for display_name, entry in _read_models_ini_name_map(path).items()
        if not vision_only or entry["has_mmproj"]
    ]


def _read_models_ini_name_map(path: str) -> dict[str, dict[str, Any]]:
    if not os.path.exists(path):
        return {}

    name_map: dict[str, dict[str, Any]] = {}
    current_section = ""
    current_alias = ""
    current_has_mmproj = False

    def add_current_model() -> None:
        section = current_section.strip()
        display_name = (current_alias or current_section).strip()
        if not section or not display_name or display_name.endswith("-reasoning"):
            return
        name_map.setdefault(
            display_name,
            {"section": section, "has_mmproj": current_has_mmproj},
        )

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("[") and line.endswith("]"):
                add_current_model()
                current_section = line[1:-1].strip()
                current_alias = ""
                current_has_mmproj = False
                continue

            key, separator, value = line.partition("=")
            if not separator:
                continue
            key = key.strip().lower()
            if key == "alias":
                current_alias = value.strip()
            elif key == "mmproj":
                current_has_mmproj = bool(value.strip())

    add_current_model()
    return name_map


def _normalize_server_url(server_url: str) -> str:
    server_url = server_url.strip().rstrip("/")
    if not server_url:
        raise ValueError("server_url is required")
    return server_url


def _build_chat_payload(
    model: str,
    messages: list[dict[str, Any]],
    reasoning: bool,
    seed: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "reasoning": "on" if reasoning else "off",
        "chat_template_kwargs": {"enable_thinking": reasoning},
    }
    if seed >= 0:
        payload["seed"] = seed
    return payload


def _get_json(url: str, timeout_seconds: int) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llama.cpp server returned HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach llama.cpp server: {e.reason}") from e

    if not text:
        return {}
    return json.loads(text)


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llama.cpp server returned HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to reach llama.cpp server: {e.reason}") from e

    if not text:
        return {}
    return json.loads(text)


def _image_to_png_data_url(image: Any) -> str:
    if len(image.shape) != 4:
        raise ValueError(
            "Expected IMAGE tensor shape [batch, height, width, channels], "
            f"got {tuple(image.shape)}"
        )

    first_image = image[0].detach().cpu().clamp(0, 1)
    array = (first_image.numpy() * 255.0).round().astype("uint8")

    if array.shape[-1] == 1:
        pil_image = Image.fromarray(array[..., 0], mode="L")
    elif array.shape[-1] == 4:
        pil_image = Image.fromarray(array, mode="RGBA")
    else:
        pil_image = Image.fromarray(array[..., :3], mode="RGB")

    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _get_llama_models_data(server_url: str, timeout_seconds: int) -> list[dict[str, Any]]:
    response = _get_json(f"{server_url}/models", timeout_seconds)
    if isinstance(response, dict):
        data = response.get("data", response.get("models", []))
    else:
        data = response
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _get_model_name(model_info: dict[str, Any]) -> str:
    for key in ("id", "model", "name"):
        value = model_info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _validate_model_supports_image(
    server_url: str,
    model: str,
    models_ini_path: str,
    timeout_seconds: int,
) -> None:
    models = _get_llama_models_data(server_url, timeout_seconds)
    model_names = {
        _get_model_name(item): item for item in models if _get_model_name(item)
    }
    validation_model = model
    model_info = model_names.get(validation_model)

    if model_info is None:
        entry = _read_models_ini_name_map(models_ini_path).get(model)
        validation_model = entry["section"] if entry else model
        model_info = model_names.get(validation_model)

    if model_info is None:
        available = ", ".join(model_names.keys())
        alias_note = ""
        if validation_model != model:
            alias_note = f" Alias '{model}' resolved to '{validation_model}'."
        raise ValueError(
            f"Selected model '{model}' was not found in llama.cpp /models metadata."
            f"{alias_note} Available models: {available or '(none)'}"
        )

    architecture = model_info.get("architecture")
    modalities = (
        architecture.get("input_modalities") if isinstance(architecture, dict) else None
    )
    if not isinstance(modalities, list) or "image" not in modalities:
        alias_note = ""
        if validation_model != model:
            alias_note = f" alias '{model}' resolves to '{validation_model}', which"
        else:
            alias_note = f" '{model}'"
        raise ValueError(
            f"Selected model{alias_note} does not advertise image input support in "
            f"/models architecture.input_modalities. Found: {modalities!r}"
        )


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    return usage if isinstance(usage, dict) else {}


def _extract_chat_content(response: Any) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            "llama.cpp response did not include choices[0].message.content: "
            f"{json.dumps(response, ensure_ascii=False)}"
        ) from e

    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


NODE_CLASS_MAPPINGS = {
    "LlamaCppChat": LlamaCppChat,
    "LlamaCppVisionChat": LlamaCppVisionChat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LlamaCppChat": "Llama.cpp Chat",
    "LlamaCppVisionChat": "Llama.cpp Vision Chat",
}
