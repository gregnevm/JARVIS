"""AP-5.5: Postman collection is valid JSON and covers the /v1 + key-mgmt surface."""
from __future__ import annotations

import json
from pathlib import Path

_COLLECTION = Path(__file__).resolve().parents[2] / "sdk" / "jarvis-api.postman_collection.json"


def test_collection_valid_and_covers_surface() -> None:
    assert _COLLECTION.exists(), f"missing collection: {_COLLECTION}"
    spec = json.loads(_COLLECTION.read_text(encoding="utf-8"))
    urls = " ".join(
        (item.get("request", {}).get("url") or "")
        if isinstance(item.get("request", {}).get("url"), str)
        else json.dumps(item.get("request", {}).get("url"))
        for item in spec["item"]
    )
    for path in (
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/embeddings",
        "/v1/jobs",
        "/v1/usage",
        "/v1/models",
        "/saas/api/keys",
    ):
        assert path in urls, f"collection missing {path}"
    # variables present for base_url + api_key
    keys = {v["key"] for v in spec.get("variable", [])}
    assert {"base_url", "api_key"} <= keys
