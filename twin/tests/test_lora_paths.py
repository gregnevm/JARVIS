"""resolve_lora_path — twin data_dir."""
from pathlib import Path

from app.lora_paths import resolve_lora_path


def test_resolve_relative_version(tmp_path: Path):
    f = tmp_path / "twin" / "lora" / "v1.gguf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    p = resolve_lora_path("v1.gguf", tmp_path)
    assert p == f.resolve()
