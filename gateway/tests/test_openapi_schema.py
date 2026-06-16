"""AP-5: /v1 + key-management surface is discoverable in the OpenAPI schema."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_exposes_platform_surface() -> None:
    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()
    paths = spec.get("paths", {})
    for p in (
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/embeddings",
        "/v1/jobs",
        "/v1/jobs/{job_id}",
        "/v1/usage",
        "/v1/models",
        "/saas/api/keys",
        "/saas/api/keys/{key_id}",
    ):
        assert p in paths, f"missing OpenAPI path: {p}"
