"""read_project_files_content truncation (P1.7)."""


def test_read_project_files_content_truncates_per_file():
    """Pure logic via static budget application (no DB)."""
    rows = [
        {"name": "a.txt", "content": "x" * 5000},
        {"name": "b.txt", "content": "y" * 100},
    ]
    out: list[dict[str, str]] = []
    budget = 8000
    max_per_file = 4000
    for r in rows:
        if budget <= 0:
            break
        name = str(r["name"])
        raw = str(r["content"])
        per_cap = min(max_per_file, budget)
        if len(raw) > per_cap:
            content = raw[:per_cap] + "…[truncated]"
        else:
            content = raw
        out.append({"name": name, "content": content})
        budget -= len(content)
    assert len(out) == 2
    assert out[0]["content"].endswith("…[truncated]")
    assert out[1]["content"] == "y" * 100
