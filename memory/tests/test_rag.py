"""chunk_text — чанкінг тексту з перекриттям."""
from app.rag import chunk_text


def test_empty():
    assert chunk_text("") == []


def test_whitespace_only():
    assert chunk_text("   \n  ") == []


def test_short_single_chunk():
    assert chunk_text("короткий текст") == ["короткий текст"]


def test_long_text_with_overlap():
    text = "".join(str(i % 10) for i in range(1000))  # 1000 символів
    chunks = chunk_text(text, max_chars=400, overlap=100)  # крок = 300
    assert len(chunks) == 4
    assert chunks[0] == text[:400]
    assert chunks[1] == text[300:700]  # перекриття 100
    assert chunks[-1] == text[900:1000]
    assert all(len(c) <= 400 for c in chunks)
