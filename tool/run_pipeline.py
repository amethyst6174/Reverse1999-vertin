from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def run(script: Path, *arguments: object) -> None:
    command = [sys.executable, str(script), *(str(value) for value in arguments)]
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reusable Reverse: 1999 voice extraction pipeline")
    parser.add_argument("--result", type=Path, default=Path("result"))
    parser.add_argument("--serial", default="127.0.0.1:7555")
    parser.add_argument("--package", default="com.mover.twcfwl1999")
    parser.add_argument("--hero", default="5043")
    parser.add_argument("--language", default="en")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--vgmstream", type=Path, required=True)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--list-prefix", default="/data/admin4/dataset/hero5043/WAV/")
    args = parser.parse_args()

    scripts = Path(__file__).resolve().parent
    result = args.result.resolve()
    source = result / "source"
    config = result / "config"
    story = result / "story"
    wav = result / "WAV"
    mapping = result / "mapping"

    if not args.skip_collect:
        command = [
            scripts / "collect_resources.py", "--output", source,
            "--serial", args.serial, "--package", args.package,
            "--hero", args.hero, "--language", args.language,
        ]
        if args.apk:
            command.extend(["--apk", args.apk])
        run(command[0], *command[1:])
    run(scripts / "decrypt_datacfg.py", source / "configs", config)
    run(scripts / "extract_story.py", source, story)
    run(scripts / "extract_audio.py", source, config / "tables", wav,
        "--vgmstream", args.vgmstream, "--hero", args.hero)
    run(scripts / "map_voice_text.py", wav / "audio_index.jsonl", story, mapping,
        "--list-prefix", args.list_prefix)
    print(f"Finished. Results: {result}")


if __name__ == "__main__":
    main()
