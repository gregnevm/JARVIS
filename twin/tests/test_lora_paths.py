"""resolve_lora_path — twin data_dir + containment (fail-closed)."""
from pathlib import Path

import pytest
from app.lora_paths import resolve_lora_path


def test_resolve_relative_version(tmp_path: Path):
    f = tmp_path / "twin" / "lora" / "v1.gguf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    p = resolve_lora_path("v1.gguf", tmp_path)
    assert p == f.resolve()


def test_resolve_absolute_within_data_dir(tmp_path: Path):
    # Легітимний абсолютний шлях усередині data_dir — дозволено.
    f = tmp_path / "twin" / "lora" / "abs.gguf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    p = resolve_lora_path(str(f), tmp_path)
    assert p == f.resolve()


def test_absolute_path_outside_data_dir_blocked(tmp_path: Path):
    # Абсолютний шлях ПОЗА data_dir (напр. /etc/passwd) — arbitrary-file-read.
    (tmp_path / "twin" / "lora").mkdir(parents=True)
    secret = tmp_path.parent / f"secret_{tmp_path.name}.txt"
    secret.write_text("TOPSECRET")
    try:
        with pytest.raises(FileNotFoundError):
            resolve_lora_path(str(secret), tmp_path)
    finally:
        secret.unlink(missing_ok=True)


def test_dotdot_traversal_blocked(tmp_path: Path):
    # `../`-траверсал, що виходить за data_dir, відсікається (fail-closed),
    # навіть якщо цільовий файл існує.
    (tmp_path / "twin" / "lora").mkdir(parents=True)
    secret = tmp_path.parent / f"trav_{tmp_path.name}.txt"
    secret.write_text("TOPSECRET")
    try:
        with pytest.raises(FileNotFoundError):
            resolve_lora_path(f"../{secret.name}", tmp_path)
        with pytest.raises(FileNotFoundError):
            resolve_lora_path(f"../../{secret.name}", tmp_path)
    finally:
        secret.unlink(missing_ok=True)


def test_empty_path_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_lora_path("", tmp_path)
    with pytest.raises(FileNotFoundError):
        resolve_lora_path("   ", tmp_path)


def test_basename_only_match_stays_contained(tmp_path: Path):
    # base/p.name кандидат: довільний вхід зводиться до basename у twin/lora/ —
    # має знайти файл за іменем і лишитися всередині data_dir.
    f = tmp_path / "twin" / "lora" / "byname.gguf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    p = resolve_lora_path("/whatever/dir/byname.gguf", tmp_path)
    assert p == f.resolve()


def test_symlink_escaping_data_dir_blocked(tmp_path: Path):
    # Класичний containment-bypass: симлінк УСЕРЕДИНІ twin/lora/, що вказує
    # ПОЗА data_dir. resolve() слідує за лінком → _within відсікає (fail-closed).
    lora_dir = tmp_path / "twin" / "lora"
    lora_dir.mkdir(parents=True)
    secret = tmp_path.parent / f"sym_{tmp_path.name}.txt"
    secret.write_text("TOPSECRET")
    link = lora_dir / "evil.gguf"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (Windows w/o privilege)")
    try:
        with pytest.raises(FileNotFoundError):
            resolve_lora_path("evil.gguf", tmp_path)
    finally:
        secret.unlink(missing_ok=True)


def test_symlink_inside_data_dir_allowed(tmp_path: Path):
    # Легітимний симлінк усередині data_dir (Blue-Green active/) → дозволено.
    lora_dir = tmp_path / "twin" / "lora"
    lora_dir.mkdir(parents=True)
    real = lora_dir / "v2.gguf"
    real.write_bytes(b"x")
    link = lora_dir / "active.gguf"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable (Windows w/o privilege)")
    p = resolve_lora_path("active.gguf", tmp_path)
    assert p == real.resolve()
