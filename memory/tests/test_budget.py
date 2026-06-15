"""Token-budget утиліти (CA-2.5)."""
from app.budget import estimate_tokens, fit_token_budget


def test_estimate_tokens_basic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 4) == 1
    assert estimate_tokens("a" * 5) == 2  # ceil(5/4)
    assert estimate_tokens("a" * 4000) == 1000


def test_fit_token_budget_per_item_truncation():
    items = [{"name": "a", "content": "x" * 8000}]  # 2000 ток
    out = fit_token_budget(items, max_total_tokens=5000, max_per_item_tokens=500)
    # обрізано до 500 токенів ≈ 2000 символів + маркер
    assert out[0]["content"].endswith("…[truncated]")
    assert len(out[0]["content"]) <= 500 * 4 + len("…[truncated]")
    assert out[0]["name"] == "a"  # інші поля збережено


def test_fit_token_budget_total_stop():
    items = [
        {"name": "a", "content": "x" * 4000},  # 1000 ток
        {"name": "b", "content": "y" * 4000},  # 1000 ток
        {"name": "c", "content": "z" * 4000},  # не влізе
    ]
    out = fit_token_budget(items, max_total_tokens=2000, max_per_item_tokens=2000)
    assert [o["name"] for o in out] == ["a", "b"]  # третій відсічено бюджетом


def test_fit_token_budget_does_not_mutate_input():
    items = [{"name": "a", "content": "x" * 8000}]
    fit_token_budget(items, max_total_tokens=100, max_per_item_tokens=100)
    assert len(items[0]["content"]) == 8000  # оригінал недоторканий


def test_fit_token_budget_zero_budget():
    assert fit_token_budget([{"content": "x"}], max_total_tokens=0, max_per_item_tokens=10) == []
