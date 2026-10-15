"""Database input format (docs/db_format.md).

JSONL input, one block per line; block j becomes column j of X (rcpir_common.blocks).
X.bin is column-major: t consecutive columns of L bytes.
"""

from __future__ import annotations

import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from rcpir_common.blocks import MAX_PAYLOAD, column_bytes, encode_column


class DBFormatError(ValueError):
    def __init__(self, line: int, message: str):
        self.line = line                                    # 1-based, 0 = not tied to a line
        super().__init__(f"line {line}: {message}" if line else message)


def _decode_line(raw: bytes, lineno: int) -> bytes:
    """Validate one JSONL line (without its newline) and return the decoded payload."""
    if raw.strip() == b"":
        raise DBFormatError(lineno, "blank line (not allowed)")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise DBFormatError(lineno, f"invalid UTF-8: {e}") from None
    except json.JSONDecodeError as e:
        raise DBFormatError(lineno, f"invalid JSON: {e}") from None
    if not isinstance(obj, dict):
        raise DBFormatError(lineno, "line is not a JSON object")
    if "data" not in obj:
        raise DBFormatError(lineno, 'missing field "data"')
    if not isinstance(obj["data"], str):
        raise DBFormatError(lineno, 'field "data" is not a string')
    try:
        payload = binascii.a2b_base64(obj["data"], strict_mode=True)
    except (binascii.Error, ValueError) as e:              # ValueError: non-ASCII characters
        raise DBFormatError(lineno, f'invalid base64 in "data": {e}') from None
    if len(payload) > MAX_PAYLOAD:
        raise DBFormatError(lineno, f"payload too large ({len(payload)} bytes)")
    return payload


def iter_payloads(path: Path):
    """Yield (lineno, payload) for every line, validating as we go."""
    with open(path, "rb") as f:
        for lineno, raw in enumerate(f, start=1):
            yield lineno, _decode_line(raw.removesuffix(b"\n"), lineno)


@dataclass(frozen=True)
class ScanResult:
    t: int                  # number of blocks
    max_payload: int        # bytes
    sum_payload: int        # bytes
    input_sha256: str       # of the raw input file (checked by --resume)

    @property
    def L(self) -> int:
        return column_bytes(self.max_payload)

    @property
    def ell(self) -> int:
        return 8 * self.L

    @property
    def n(self) -> int:
        return self.t * self.ell

    @property
    def padding_overhead(self) -> float:
        return 1 - (self.sum_payload + 4 * self.t) / (self.t * self.L)


def scan(path: Path) -> ScanResult:
    """Pass 1: validate every line, count blocks, track payload lengths."""
    lengths = [len(payload) for _, payload in iter_payloads(path)]
    if not lengths:
        raise DBFormatError(0, "empty input file (no blocks)")
    with open(path, "rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return ScanResult(t=len(lengths), max_payload=max(lengths), sum_payload=sum(lengths), input_sha256=sha)


def pack(path: Path, sr: ScanResult, out_path: Path) -> str:
    """Pass 2: write X.bin. Returns its sha256 hex digest (db_digest)."""
    h = hashlib.sha256()
    lineno = 0
    with open(out_path, "wb") as out:
        for lineno, payload in iter_payloads(path):
            if lineno > sr.t or len(payload) > sr.max_payload:
                raise DBFormatError(lineno, "input changed between scan and pack")
            col = encode_column(payload, sr.L)
            out.write(col)
            h.update(col)
    if lineno != sr.t:
        raise DBFormatError(0, "input changed between scan and pack")
    return h.hexdigest()
