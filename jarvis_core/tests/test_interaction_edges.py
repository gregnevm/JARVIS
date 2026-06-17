"""TC-3 — observed-graph: interaction_edges (нормалізовані пари collaborates_with)."""
from __future__ import annotations

from jarvis_core.orggraph import interaction_edges


def test_pairs_author_with_each_subject() -> None:
    assert interaction_edges("A", ["B", "C"]) == [("A", "B"), ("A", "C")]


def test_normalizes_order_for_dedup() -> None:
    # автор B, суб'єкт A → та сама пара (A,B), що й author A subj B
    assert interaction_edges("B", ["A"]) == [("A", "B")]


def test_skips_self_empty_and_dups() -> None:
    assert interaction_edges("A", ["A", "", "  ", "B", "B"]) == [("A", "B")]


def test_empty_subjects() -> None:
    assert interaction_edges("A", []) == []
