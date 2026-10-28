from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from common import write_json

KEY = b"@_#*&Reverse2806".ljust(32, b" ")
IV = b"!_#@2022_Skyfly)".ljust(16, b" ")
SIGNATURE_SIZE = 48


def decrypt(data: bytes) -> tuple[bytes, dict]:
    if len(data) <= SIGNATURE_SIZE or (len(data) - SIGNATURE_SIZE) % 16:
        raise ValueError("Invalid datacfg ciphertext length")
    decryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
    plain = decryptor.update(data[SIGNATURE_SIZE:]) + decryptor.finalize()
    padding = plain[-1]
    if not 1 <= padding <= 16 or plain[-padding:] != bytes([padding]) * padding:
        raise ValueError("Invalid PKCS#7 padding")
    plain = plain[:-padding]
    outer = json.loads(plain.decode("utf-8-sig"))
    if not isinstance(outer, dict):
        raise ValueError("Expected a JSON table dictionary")
    tables = {}
    for name, value in outer.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError(f"Unsafe table name: {name!r}")
        tables[name] = json.loads(value) if isinstance(value, str) else value
    return plain, tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Decrypt Reverse: 1999 datacfg files")
    parser.add_argument("input", type=Path, help="Directory containing datacfg_*.dat")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = sorted(args.input.glob("datacfg_*.dat"))
    if not files:
        raise ValueError("No datacfg_*.dat files found")
    args.output.mkdir(parents=True, exist_ok=True)
    report = []
    for source in files:
        data = source.read_bytes()
        plain, tables = decrypt(data)
        (args.output / f"{source.stem}.json").write_bytes(plain)
        table_dir = args.output / "tables" / source.stem
        table_dir.mkdir(parents=True, exist_ok=True)
        for name, value in tables.items():
            write_json(table_dir / f"{name}.json", value)
        report.append({
            "input": str(source.resolve()),
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "plaintext_sha256": hashlib.sha256(plain).hexdigest(),
            "tables": len(tables),
            "padding_valid": True,
            "json_valid": True,
            "rsa_signature_verified": False,
        })
        print(f"{source.name}: {len(tables)} tables")
    write_json(args.output / "verification.json", report)


if __name__ == "__main__":
    main()
