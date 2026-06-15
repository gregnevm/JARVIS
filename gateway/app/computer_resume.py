"""Текст resume після Computer Use confirm (спільний для PS panel і Platform Workbench)."""
from __future__ import annotations


def resume_text(origin: str, result: str) -> str:
    parts: list[str] = []
    origin = (origin or "").strip()
    if origin:
        parts.append(f"Оригінальний запит користувача:\n{origin[:3000]}")
    parts.append(f"Результат підтвердженої Computer Use дії на хості:\n{result[:6000]}")
    parts.append(
        "Коротко підсумуй для користувача українською. "
        "Якщо початкове завдання ще не виконано — продовж наступним кроком."
    )
    return "\n\n".join(parts)
