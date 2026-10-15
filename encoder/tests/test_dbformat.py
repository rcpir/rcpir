"""JSONL scan/pack: what testvectors/vectors/db_format.json (test_vectors.py) does not cover."""

import pytest

from conftest import write_jsonl
from rcpir_encoder import dbformat
from rcpir_encoder.dbformat import DBFormatError


def test_scan_statistics(tmp_path):
    db = write_jsonl(tmp_path / "db.jsonl", [b"Hello world", b"", bytes(range(5))])
    sr = dbformat.scan(db)
    assert (sr.t, sr.max_payload, sr.sum_payload, sr.L, sr.n) == (3, 11, 16, 16, 384)
    assert sr.padding_overhead == pytest.approx(1 - (16 + 12) / 48)


def test_input_changed_between_passes(tmp_path):
    db = write_jsonl(tmp_path / "db.jsonl", [b"a", b"b"])
    sr = dbformat.scan(db)
    write_jsonl(db, [b"a", b"b", b"c"])
    with pytest.raises(DBFormatError, match="changed"):
        dbformat.pack(db, sr, tmp_path / "X.bin")
