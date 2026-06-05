"""Нормалізація PUBLIC_APP_URL для Mini App."""
from __future__ import annotations

from app.webapp_urls import local_app_url, normalize_mini_app_url


def test_normalize_adds_app_suffix():
    assert normalize_mini_app_url("https://jarvis.example.com") == "https://jarvis.example.com/app"


def test_normalize_keeps_app_suffix():
    assert normalize_mini_app_url("https://jarvis.example.com/app/") == "https://jarvis.example.com/app"


def test_normalize_rejects_http():
    assert normalize_mini_app_url("http://localhost:8000/app") == ""


def test_local_app_url_canvas():
    assert local_app_url("http://127.0.0.1:8000", canvas=True) == "http://127.0.0.1:8000/app?canvas=1"
