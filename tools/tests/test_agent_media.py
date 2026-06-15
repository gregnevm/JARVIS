"""_ensure_tool_media — дописує [[photo:…]] з результатів generate_image."""
from app.agent import _ensure_tool_media


def test_appends_missing_photo_from_tool_result():
    messages = [
        {
            "role": "tool",
            "content": (
                "[generate_image] Зображення згенеровано. "
                "[[photo:/data/uploads/gen_123.png]]"
            ),
        }
    ]
    out = _ensure_tool_media("Ось котик!", messages)
    assert "[[photo:/data/uploads/gen_123.png]]" in out
    assert out.startswith("Ось котик!")


def test_does_not_duplicate_directive():
    messages = [
        {"role": "tool", "content": "[generate_image] [[photo:/data/uploads/gen_1.png]]"},
    ]
    answer = "Готово [[photo:/data/uploads/gen_1.png]]"
    assert _ensure_tool_media(answer, messages) == answer
