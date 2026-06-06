import base64
import io
import json
import urllib.error
import urllib.request
from typing import Any

from PIL import Image


class LlamaCppChat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "server_url": (
                    "STRING",
                    {"default": "http://127.0.0.1:8080"},
                ),
                "model": ([""],),
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
                "model": ([""],),
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


def _get_model_lookup_names(model_info: dict[str, Any]) -> list[str]:
    names = [_get_model_name(model_info)]
    aliases = model_info.get("aliases")
    if isinstance(aliases, list):
        names.extend(alias.strip() for alias in aliases if isinstance(alias, str))
    return [name for name in names if name]


def _validate_model_supports_image(
    server_url: str,
    model: str,
    timeout_seconds: int,
) -> None:
    models = _get_llama_models_data(server_url, timeout_seconds)
    model_names = {
        name: item for item in models for name in _get_model_lookup_names(item)
    }
    model_info = model_names.get(model)

    if model_info is None:
        available = ", ".join(model_names.keys())
        raise ValueError(
            f"Selected model '{model}' was not found in llama.cpp /models metadata. "
            f"Available models and aliases: {available or '(none)'}"
        )

    architecture = model_info.get("architecture")
    modalities = (
        architecture.get("input_modalities") if isinstance(architecture, dict) else None
    )
    if not isinstance(modalities, list) or "image" not in modalities:
        canonical_name = _get_model_name(model_info)
        alias_note = f" alias '{model}' resolves to '{canonical_name}', which"
        if model == canonical_name:
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
