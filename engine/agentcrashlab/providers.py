from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PROVIDERS = {
    "meta": {"url": "https://api.meta.ai/v1", "key": "MODEL_API_KEY", "model_key": "META_MODEL", "model": "muse-spark-1.3"},
    "baseten": {"url": "https://inference.baseten.co/v1", "key": "BASETEN_API_KEY", "model_key": "BASETEN_MODEL", "model": "meta-models/muse-spark-open-1026"},
    "fireworks": {"url": "https://api.fireworks.ai/inference/v1", "key": "FIREWORKS_API_KEY", "model_key": "FIREWORKS_MODEL", "model": ""},
}


def configuration():
    return [{"id": k, "configured": bool(os.environ.get(v["key"])) and bool(os.environ.get(v["model_key"], v["model"])), "model": os.environ.get(v["model_key"], v["model"])} for k, v in PROVIDERS.items()]


def complete(provider, model, messages):
    config = PROVIDERS.get(provider)
    if not config or not os.environ.get(config["key"]):
        raise ValueError(f"{provider} is not configured; add its server-side API key")
    model = model or os.environ.get(config["model_key"], config["model"])
    if not model:
        raise ValueError("Set the provider's explicit model ID first")
    request = urllib.request.Request(config["url"] + "/chat/completions", data=json.dumps({"model": model, "messages": messages, "max_tokens": 2048}).encode(), headers={"Authorization": "Bearer " + os.environ[config["key"]], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Provider bodies may echo private request content. Keep diagnostics bounded.
        raise RuntimeError(f"Provider returned HTTP {exc.code}") from None
    return {"content": result["choices"][0]["message"]["content"], "usage": result.get("usage", {}), "provider": provider, "model": model, "cost_usd": None}
