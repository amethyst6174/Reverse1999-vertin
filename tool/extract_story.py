from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

import UnityPy

from common import file_hash, find_nested, load_manifest, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract current json_story_step files")
    parser.add_argument("source", type=Path, help="Collected source directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest_path = args.source / "configs" / "allmanifest.dat"
    resinfo_path = args.source / "configs" / "resinfo.dat"
    manifest = load_manifest(manifest_path)
    info = next(item for item in manifest if item.get("abName") == "configs/story")
    bundle_name = hashlib.md5(b"configs/story").hexdigest() + ".dat"
    bundle_path = args.source / "bundles" / bundle_name
    raw = bundle_path.read_bytes()

    resinfo_raw = resinfo_path.read_bytes()
    if resinfo_raw.startswith(b"\x1f\x8b"):
        resinfo_raw = gzip.decompress(resinfo_raw)
    resinfo = json.loads(resinfo_raw.decode("utf-8-sig"))
    entries = list(find_nested(resinfo, "bundles/" + bundle_name))
    bundle_md5 = hashlib.md5(raw).hexdigest()
    if entries and not any(item.get("md5") == bundle_md5 and item.get("size") == len(raw) for item in entries):
        raise ValueError("Story bundle does not match resinfo")

    start = raw[:256].find(b"UnityFS\0")
    if start < 0:
        raise ValueError("UnityFS marker not found")
    expected = {
        name.lower() for name in info.get("assets", [])
        if re.fullmatch(r"configs/story/steps/json_story_step_\d+\.json", name.lower())
    }
    args.output.mkdir(parents=True, exist_ok=True)
    env = UnityPy.load(raw[start:])
    seen = set()
    files = []
    for asset_path, obj in env.container.items():
        normalized = asset_path.lower().removeprefix("assets/zresourceslib/")
        if normalized not in expected:
            continue
        if obj.type.name != "TextAsset":
            raise ValueError(f"Unexpected asset type: {asset_path}")
        text = obj.read_typetree()["m_Script"].lstrip("\ufeff")
        json.loads(text)
        destination = args.output / Path(normalized).name
        destination.write_text(text, encoding="utf-8")
        seen.add(normalized)
        files.append({"file": destination.name, "asset": asset_path, "sha256": file_hash(destination)})
    if seen != expected:
        raise ValueError(f"Missing {len(expected - seen)} indexed story assets")
    write_json(args.output / "provenance.json", {
        "source": "current local emulator resource bundle",
        "github_text_used": False,
        "bundle": str(bundle_path.resolve()),
        "bundle_md5": bundle_md5,
        "bundle_sha256": file_hash(bundle_path),
        "bundle_prefix_bytes": start,
        "story_files": len(files),
        "files": files,
    })
    print(f"Extracted {len(files)} story files")


if __name__ == "__main__":
    main()
