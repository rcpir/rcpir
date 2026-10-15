"""Encoder JSONL scan/pack against testvectors/vectors/db_format.json (cross-language vectors)."""

import json
from pathlib import Path

import pytest

from rcpir_encoder import dbformat
from rcpir_encoder.dbformat import DBFormatError

VEC = Path(__file__).resolve().parents[2] / "testvectors" / "vectors"
DB = json.loads((VEC / "db_format.json").read_text())


@pytest.mark.parametrize("case", DB["valid"], ids=lambda c: c["name"])
def test_valid(tmp_path, case):
    db = tmp_path / "db.jsonl"
    db.write_bytes(bytes.fromhex(case["jsonl_hex"]))
    sr = dbformat.scan(db)
    assert (sr.t, sr.max_payload, sr.sum_payload, sr.L, sr.ell) == (
        case["t"], case["max_payload"], case["sum_payload"], case["L"], case["ell"])
    digest = dbformat.pack(db, sr, tmp_path / "X.bin")
    assert (tmp_path / "X.bin").read_bytes().hex() == case["x_bin_hex"]
    assert f"sha256:{digest}" == case["db_digest"]


@pytest.mark.parametrize("case", DB["invalid"], ids=lambda c: c["name"])
def test_invalid(tmp_path, case):
    db = tmp_path / "db.jsonl"
    db.write_bytes(bytes.fromhex(case["jsonl_hex"]))
    with pytest.raises(DBFormatError) as ei:
        dbformat.scan(db)
    assert ei.value.line == (case["error_line"] or 0)      # null (empty file) = not tied to a line
