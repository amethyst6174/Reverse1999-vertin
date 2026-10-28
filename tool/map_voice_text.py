from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path
import re


def clean(value: str) -> str:
    value = re.sub(r"<[^>]*>", "", value)
    return re.sub(r"\s+", " ", value.replace("|", " ")).strip()


def story_records(story_dir: Path) -> dict[str, list[dict]]:
    records = collections.defaultdict(list)
    for path in sorted(story_dir.glob("json_story_step_*.json")):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, list) or len(value) < 3 or not isinstance(value[2], list):
            continue
        for step in value[2]:
            if not (isinstance(step, list) and len(step) >= 3 and isinstance(step[2], list)):
                continue
            payload = step[2]
            if len(payload) < 16 or not isinstance(payload[15], list):
                continue
            voice_id = str(payload[14])
            if voice_id == "0":
                continue
            texts = payload[15]
            english = texts[2] if len(texts) > 2 and isinstance(texts[2], str) else ""
            speaker_data = payload[11] if len(payload) > 11 else []
            speaker = speaker_data[2] if isinstance(speaker_data, list) and len(speaker_data) > 2 else ""
            records[voice_id].append({
                "voice_id": voice_id,
                "story_file": path.name,
                "step_id": step[0],
                "speaker": speaker,
                "english_raw": english,
                "english": clean(english),
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Map decoded WAVs to current English story text")
    parser.add_argument("audio_index", type=Path)
    parser.add_argument("story_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--list-prefix", default="/data/admin4/dataset/hero5043/WAV/")
    parser.add_argument("--default-speaker", default="Vertin")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    texts = story_records(args.story_dir)
    audio_rows = [json.loads(line) for line in args.audio_index.read_text(encoding="utf-8").splitlines()]
    grouped = collections.defaultdict(list)
    for row in audio_rows:
        if row.get("status") == "decoded" and row.get("wav"):
            grouped[row["wav"]].append(row)

    rows = []
    for wav, links in sorted(grouped.items()):
        matched = []
        for link in links:
            matched.extend(texts.get(link["voice_id"], []))
        matched = list({(item["voice_id"], item["story_file"], item["step_id"]): item
                        for item in matched}.values())
        variants = sorted({item["english"] for item in matched if item["english"]})
        speakers = sorted({item["speaker"] for item in matched if item["speaker"]})
        if not matched:
            status = "no_story_step_for_voice"
        elif not variants:
            status = "empty_english_in_story"
        elif len(variants) > 1:
            status = "conflicting_english_texts"
        elif not re.search(r"[A-Za-z]", variants[0]):
            status = "nonverbal_text"
        else:
            status = "matched_unique_english"
        rows.append({
            "wav": wav,
            "wav_path": links[0]["wav_path"],
            "wav_sha256": links[0]["wav_sha256"],
            "status": status,
            "speaker": speakers[0] if len(speakers) == 1 else "",
            "english": variants[0] if status == "matched_unique_english" else "",
            "english_candidates": variants,
            "links": links,
            "story_records": matched,
        })

    with (args.output / "mapping.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    flat_rows = [{
        "wav": row["wav"], "wav_path": row["wav_path"], "wav_sha256": row["wav_sha256"],
        "status": row["status"], "speaker": row["speaker"], "english": row["english"],
        "voice_ids": ";".join(sorted({link["voice_id"] for link in row["links"]})),
        "banks": ";".join(sorted({link["bank"] for link in row["links"]})),
        "event_names": ";".join(sorted({link["event_name"] for link in row["links"]})),
        "story_steps": ";".join(f"{item['story_file']}:{item['step_id']}" for item in row["story_records"]),
        "english_candidates": json.dumps(row["english_candidates"], ensure_ascii=False),
    } for row in rows]
    fields = list(flat_rows[0]) if flat_rows else []
    for filename, selected in (("mapping.csv", flat_rows),
                               ("unmatched.csv", [row for row in flat_rows if row["status"] != "matched_unique_english"])):
        with (args.output / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(selected)

    list_lines = []
    for row in rows:
        if row["status"] != "matched_unique_english":
            continue
        speaker = row["speaker"] or args.default_speaker
        list_lines.append(f"{args.list_prefix}{row['wav']}|{speaker}|en|{row['english']}")
    (args.output / "gpt-sovits.list").write_text("\n".join(list_lines) + ("\n" if list_lines else ""), encoding="utf-8")
    summary = {"wav_files": len(rows), "status_counts": dict(collections.Counter(row["status"] for row in rows)),
               "gpt_sovits_lines": len(list_lines), "github_text_used": False}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
