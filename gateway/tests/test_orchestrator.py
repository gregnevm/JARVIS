"""extract_text — діставання тексту відповіді з різних форматів n8n/Ollama."""
from app.orchestrator import FALLBACK, extract_text


def test_plain_string():
    assert extract_text("готово") == "готово"


def test_empty_string_falls_back():
    assert extract_text("") == FALLBACK


def test_dict_text_key():
    assert extract_text({"text": "привіт"}) == "привіт"


def test_dict_alternative_keys():
    assert extract_text({"answer": "42"}) == "42"


def test_ollama_message_shape():
    assert extract_text({"message": {"content": "зміст"}}) == "зміст"


def test_unknown_falls_back():
    assert extract_text({"foo": "bar"}) == FALLBACK
    assert extract_text(123) == FALLBACK
