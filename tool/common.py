from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            import nrbf
        except ImportError as exc:
            raise RuntimeError("NRBF manifest requires: pip install nrbf") from exc
        value = nrbf.loads(raw)
    if not isinstance(value, list):
        raise ValueError("Expected allmanifest.dat to contain a list")
    return value


def find_nested(value: Any, target: str) -> Iterable[Any]:
    if isinstance(value, dict):
        if target in value:
            yield value[target]
        for child in value.values():
            yield from find_nested(child, target)
    elif isinstance(value, list):
        for child in value:
            yield from find_nested(child, target)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fnv1_32(name: str) -> int:
    value = 2166136261
    for byte in name.lower().encode("utf-8"):
        value = ((value * 16777619) & 0xFFFFFFFF) ^ byte
    return value
