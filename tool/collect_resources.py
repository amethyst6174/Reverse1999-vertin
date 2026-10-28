from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

from common import file_hash, write_json


def adb(serial: str, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
    command = ["adb", "-s", serial, *args]
    return subprocess.run(command, check=True, capture_output=capture, text=capture)


def pull(serial: str, remote: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    adb(serial, "pull", remote, str(destination))


def extract_apk_banks(apk: Path, destination: Path, hero: str, language: str) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    prefix = f"assets/Android/audios/Android/{language}/"
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            name = info.filename
            filename = PurePosixPath(name).name
            if name.startswith(prefix) and name.lower().endswith(".bnk") and hero in filename:
                target = destination / filename
                target.write_bytes(archive.read(info))
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect current Reverse: 1999 resources")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial", default="127.0.0.1:7555")
    parser.add_argument("--package", default="com.mover.twcfwl1999")
    parser.add_argument("--hero", default="5043")
    parser.add_argument("--language", default="en")
    parser.add_argument("--apk", type=Path, help="Optional current APK containing built-in BNKs")
    args = parser.parse_args()

    root = args.output.resolve()
    configs = root / "configs"
    bundles = root / "bundles"
    device_banks = root / "banks" / "device"
    apk_banks = root / "banks" / "apk"
    for directory in (configs, bundles, device_banks):
        directory.mkdir(parents=True, exist_ok=True)

    remote = f"/storage/emulated/0/Android/data/{args.package}/files/ResLib/Android"
    config_names = ["allmanifest.dat", "resinfo.dat", "metainfo.dat", "langcfg.dat"]
    config_names.extend(f"datacfg_{index}.dat" for index in range(1, 6))
    for name in config_names:
        try:
            pull(args.serial, f"{remote}/configs/{name}", configs / name)
        except subprocess.CalledProcessError:
            if name not in {"langcfg.dat", "metainfo.dat"}:
                raise

    story_name = hashlib.md5(b"configs/story").hexdigest() + ".dat"
    pull(args.serial, f"{remote}/bundles/{story_name}", bundles / story_name)

    command = f'find "{remote}/audios/Android/{args.language}" -maxdepth 1 -type f -name "*{args.hero}*.bnk"'
    listing = adb(args.serial, "shell", command, capture=True).stdout.splitlines()
    pulled = 0
    expected_prefix = f"{remote}/audios/Android/{args.language}/"
    for remote_path in listing:
        remote_path = remote_path.strip()
        if not remote_path.startswith(expected_prefix) or not remote_path.endswith(".bnk"):
            continue
        pull(args.serial, remote_path, device_banks / PurePosixPath(remote_path).name)
        pulled += 1

    apk_count = 0
    if args.apk:
        apk_count = extract_apk_banks(args.apk.resolve(), apk_banks, args.hero, args.language)

    files = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "size": path.stat().st_size,
         "sha256": file_hash(path)}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    report = {
        "package": args.package,
        "serial": args.serial,
        "remote_root": remote,
        "hero": args.hero,
        "language": args.language,
        "story_bundle": story_name,
        "device_banks": pulled,
        "apk_banks": apk_count,
        "files": files,
    }
    write_json(root / "collection.json", report)
    print(json.dumps({key: report[key] for key in ("story_bundle", "device_banks", "apk_banks")}, indent=2))


if __name__ == "__main__":
    main()
