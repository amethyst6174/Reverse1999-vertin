from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from common import file_hash, fnv1_32


class Bank:
    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        self.sha256 = hashlib.sha256(self.raw).hexdigest()
        self.chunks: dict[bytes, bytes] = {}
        position = 0
        while position < len(self.raw):
            if position + 8 > len(self.raw):
                raise ValueError("Truncated BNK chunk")
            tag = self.raw[position:position + 4]
            size = int.from_bytes(self.raw[position + 4:position + 8], "little")
            end = position + 8 + size
            if end > len(self.raw):
                raise ValueError("Invalid BNK chunk size")
            self.chunks[tag] = self.raw[position + 8:end]
            position = end
        version = int.from_bytes(self.chunks[b"BKHD"][:4], "little")
        if version != 150:
            raise ValueError(f"Unsupported Wwise bank version: {version}")
        self.media = list(struct.iter_unpack("<III", self.chunks.get(b"DIDX", b"")))
        self.objects = self._read_hirc()

    def _read_hirc(self) -> dict[int, tuple[int, bytes]]:
        hirc = self.chunks[b"HIRC"]
        count = int.from_bytes(hirc[:4], "little")
        objects = {}
        position = 4
        for _ in range(count):
            object_type = hirc[position]
            size = int.from_bytes(hirc[position + 1:position + 5], "little")
            object_id = int.from_bytes(hirc[position + 5:position + 9], "little")
            objects[object_id] = (object_type, hirc[position + 9:position + 5 + size])
            position += 5 + size
        return objects

    def resolve(self, event_name: str) -> dict:
        event_id = fnv1_32(event_name)
        event_type, event = self.objects[event_id]
        if event_type != 4 or not event or event[0] != 1 or len(event) != 5:
            raise ValueError("event_not_single_action")
        action_id = int.from_bytes(event[1:5], "little")
        action_type, action = self.objects[action_id]
        if action_type != 3 or action[:2] != b"\x03\x04":
            raise ValueError("action_not_supported_play")
        sound_id = int.from_bytes(action[2:6], "little")
        sound_type, sound = self.objects[sound_id]
        if sound_type != 2 or len(sound) < 9:
            raise ValueError("target_not_direct_sound")
        media_id = int.from_bytes(sound[5:9], "little")
        matches = [(index, offset, size) for index, (ident, offset, size)
                   in enumerate(self.media, 1) if ident == media_id]
        if len(matches) != 1:
            raise ValueError("media_not_unique_in_bank")
        ordinal, offset, size = matches[0]
        wem = self.chunks[b"DATA"][offset:offset + size]
        if len(wem) != size or wem[:4] != b"RIFF":
            raise ValueError("invalid_wem")
        return {
            "event_id": event_id,
            "action_id": action_id,
            "sound_id": sound_id,
            "media_id": media_id,
            "ordinal": ordinal,
            "offset": offset,
            "size": size,
            "wem": wem,
        }


def load_voice_configs(table_root: Path, hero: str) -> list[dict]:
    records = {}
    for path in table_root.rglob("*audio*.json"):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], list):
            continue
        for row in value[1]:
            if not (isinstance(row, list) and len(row) >= 3 and isinstance(row[0], int)
                    and isinstance(row[1], str) and isinstance(row[2], str)):
                continue
            if hero not in row[2]:
                continue
            key = (str(row[0]), row[1], row[2])
            records[key] = {
                "voice_id": str(row[0]), "event_name": row[1], "bank": row[2],
                "config_table": path.name,
            }
    return sorted(records.values(), key=lambda item: (int(item["voice_id"]), item["event_name"]))


def load_banks(source: Path) -> dict[str, Bank]:
    paths = sorted(source.rglob("*.bnk"), key=lambda path: ("device" not in path.parts, str(path)))
    banks = {}
    for path in paths:
        if path.stem in banks:
            continue
        try:
            banks[path.stem] = Bank(path)
        except Exception as exc:
            print(f"Skipping {path.name}: {exc}")
    return banks


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract hero voice as non-looping PCM WAV")
    parser.add_argument("source", type=Path, help="Collected source directory")
    parser.add_argument("tables", type=Path, help="Decrypted tables directory")
    parser.add_argument("output", type=Path, help="WAV output directory")
    parser.add_argument("--vgmstream", type=Path, required=True, help="vgmstream test.exe or vgmstream-cli")
    parser.add_argument("--hero", default="5043")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    configs = load_voice_configs(args.tables, args.hero)
    banks = load_banks(args.source / "banks")
    rows = []
    decoded = {}
    with tempfile.TemporaryDirectory(prefix="r1999-wem-") as temporary:
        temporary = Path(temporary)
        for index, config in enumerate(configs, 1):
            bank = banks.get(config["bank"])
            if not bank:
                rows.append(dict(config, status="bank_unavailable"))
                continue
            try:
                media = bank.resolve(config["event_name"])
            except (KeyError, ValueError, IndexError) as exc:
                rows.append(dict(config, status="event_unresolved", error=str(exc)))
                continue
            filename = f"{config['bank']}_{media['ordinal']}.wav"
            wav_path = args.output / filename
            key = (bank.sha256, media["media_id"])
            if key not in decoded:
                wem_path = temporary / f"{config['bank']}_{media['media_id']}.wem"
                wem_path.write_bytes(media["wem"])
                result = subprocess.run(
                    [str(args.vgmstream.resolve()), "-i", "-o", str(wav_path.resolve()), str(wem_path)],
                    capture_output=True,
                )
                if result.returncode or not wav_path.exists():
                    rows.append(dict(config, status="decode_failed",
                                     error=result.stderr.decode(errors="replace")[-500:]))
                    continue
                decoded[key] = wav_path
            elif decoded[key] != wav_path and not wav_path.exists():
                wav_path.write_bytes(decoded[key].read_bytes())
            row = dict(config)
            row.update({key: value for key, value in media.items() if key != "wem"})
            row.update({
                "status": "decoded",
                "wav": filename,
                "wav_path": str(wav_path.resolve()),
                "wav_sha256": file_hash(wav_path),
                "wem_sha256": hashlib.sha256(media["wem"]).hexdigest(),
                "bank_path": str(bank.path.resolve()),
                "bank_sha256": bank.sha256,
                "decode_mode": "one_shot",
                "decoder_args": "-i -o",
                "looping_ignored": True,
            })
            rows.append(row)
            if index % 200 == 0:
                print(f"Processed {index}/{len(configs)}")

    with (args.output / "audio_index.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (args.output / "audio_index.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"config_records": len(configs), "decoded_records": sum(r["status"] == "decoded" for r in rows),
                      "unique_wav": len({r.get("wav") for r in rows if r.get("wav")})}, indent=2))


if __name__ == "__main__":
    main()
