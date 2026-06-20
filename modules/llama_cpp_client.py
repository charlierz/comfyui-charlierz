from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def normalize_server_url(server_url: str) -> str:
    server_url = server_url.strip().rstrip("/")
    if not server_url:
        raise ValueError("server_url is required")
    return server_url


def get_json(url: str, timeout_seconds: int = 10) -> Any:
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


def post_json(url: str, payload: dict[str, Any], timeout_seconds: int = 60) -> Any:
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


def unload_model(server_url: str, model: str, timeout_seconds: int = 60) -> Any:
    """Unload a model, swallowing errors so they don't mask the original call."""
    try:
        return post_json(
            f"{normalize_server_url(server_url)}/models/unload",
            {"model": model},
            timeout_seconds,
        )
    except Exception as exc:
        print(f"[charlierz] Failed to unload model {model}: {exc}")
        return None
