"""to_vector_literal — серіалізація ембедингу у pgvector-літерал."""
from app.db import to_vector_literal


def test_floats():
    assert to_vector_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_ints_coerced_to_float():
    assert to_vector_literal([1, 2]) == "[1.0,2.0]"


def test_empty():
    assert to_vector_literal([]) == "[]"
