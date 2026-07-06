"""Remote macros."""
from app.macros import list_macros, run_macro


def test_list_macros_default():
    names = [m["name"] for m in list_macros()]
    assert "deploy" in names


async def test_run_macro_unknown():
    out = await run_macro("no-such-macro", 1)
    assert "не знайдено" in out.lower()
