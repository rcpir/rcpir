import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import SEED, random_payloads, write_jsonl
from rcpir_common import hprg
from rcpir_encoder import gf2, pipeline
from rcpir_encoder.cli import main
from rcpir_encoder.pipeline import PROGRESS_FILE, EncodeError, EncodeOptions, encode, shard_file
from rcpir_encoder.verify import VerificationError, read_column, verify


def opts(db, out, **kw):
    kw.setdefault("seed", SEED)
    return EncodeOptions(db=Path(db), out=Path(out), **kw)


def check_output(out: Path, payloads):
    params = json.loads((out / "params.json").read_text())
    t, L, m = params["t"], params["L"], params["m"]
    assert t == len(payloads) and params["ell"] == 8 * L and 1 <= params["s"] <= m
    assert (out / "site/.well-known/rc-pir.json").read_bytes() == (out / "params.json").read_bytes()
    assert not (out / PROGRESS_FILE).exists()
    x = (out / "X.bin").read_bytes()
    assert len(x) == t * L
    assert params["db_digest"] == "sha256:" + hashlib.sha256(x).hexdigest()
    cps = params["columns_per_shard"]
    shards = sorted(p for p in (out / "site/rc-pir/r").rglob("*") if p.is_file())
    assert shards == [shard_file(out / "site", k) for k in range(-(-m // cps))]
    assert [p.stat().st_size for p in shards] == [min(cps, m - k * cps) * L for k in range(len(shards))]
    r = b"".join(p.read_bytes() for p in shards)
    assert r == b"".join(read_column(out / "site", j, cps, L) for j in range(m))
    assert params["r_digest"] == "sha256:" + hashlib.sha256(r).hexdigest()
    return params


def test_columns_equal_xh(tmp_path, rng):
    """R = XH bit-exactly across panels that span shards, plus the output layout and digests."""
    payloads = random_payloads(rng, 21, 30)
    db = write_jsonl(tmp_path / "db.jsonl", payloads)
    out = tmp_path / "out"
    params = encode(opts(db, out, insecure_m=50, insecure_s=4, panel_cols=7, shard_bytes=100))
    check_output(out, payloads)
    t, L = params["t"], params["L"]
    assert params["columns_per_shard"] == 100 // L == 2                  # L = 40: bound not a multiple of L
    Xb = np.unpackbits(np.fromfile(out / "X.bin", dtype=np.uint8).reshape(t, L), axis=1).astype(np.int64)
    for j in range(params["m"]):
        h = np.unpackbits(np.frombuffer(hprg.h_column(SEED, t, j), np.uint8), count=t).astype(np.int64)
        expect = np.packbits(((h @ Xb) % 2).astype(np.uint8)).tobytes()
        assert read_column(out / "site", j, 2, L) == expect


def test_columns_per_shard(tmp_path, rng):
    db = write_jsonl(tmp_path / "db.jsonl", random_payloads(rng, 5, 4))          # L = 8
    assert pipeline.columns_per_shard(8, 50, 8) == 1
    assert pipeline.columns_per_shard(8, 50, 8 * 7 + 7) == 7
    assert pipeline.columns_per_shard(8, 50, 1 << 26) == 50                       # at most m: one shard
    with pytest.raises(EncodeError, match="smaller than one column"):
        encode(opts(db, tmp_path / "out", insecure_m=20, insecure_s=2, shard_bytes=7))


def test_mode_b_prompt(tmp_path, rng, monkeypatch):
    db = write_jsonl(tmp_path / "db.jsonl", random_payloads(rng, 600, 12))
    target = 600 + 128 + 60 * (128 + 20)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert encode(opts(db, tmp_path / "declined", target_comm=target)) is None
    assert not (tmp_path / "declined" / "params.json").exists()
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    params = encode(opts(db, tmp_path / "ok", target_comm=target, verify=False))
    assert params["security"]["mode"] == "B" and params["security"]["target_comm_bits"] == target
    monkeypatch.setattr("builtins.input", lambda prompt: 1 / 0)       # --yes must not ask
    assert encode(opts(db, tmp_path / "yes", target_comm=target, yes=True, verify=False))["s"] >= 1


class Crash(Exception):
    pass


def crash_at(monkeypatch, column):
    """Make the encoder crash when it starts the panel beginning at `column`."""
    real = hprg.h_panel

    def h_panel(seed, t, j0, count):
        if j0 == column:
            raise Crash
        return real(seed, t, j0, count)

    monkeypatch.setattr(pipeline.hprg, "h_panel", h_panel)


def test_resume_after_interruption(tmp_path, rng, monkeypatch):
    payloads = random_payloads(rng, 40, 20)
    db = write_jsonl(tmp_path / "db.jsonl", payloads)
    ref = encode(opts(db, tmp_path / "ref", insecure_m=100, insecure_s=6, verify=False))

    out = tmp_path / "out"
    with monkeypatch.context() as mp:
        crash_at(mp, column=30)            # after 2 panels of 15 columns
        with pytest.raises(Crash):
            encode(opts(db, out, insecure_m=100, insecure_s=6, panel_cols=15, shard_bytes=8 * 32))
    assert not (out / "params.json").exists()
    assert json.loads((out / PROGRESS_FILE).read_text())["columns_done"] == 30
    with pytest.raises(EncodeError, match="not empty"):
        encode(opts(db, out, insecure_m=100, insecure_s=6))
    # Resume takes parameters and seed from the progress file, not from the options.
    params = encode(opts(db, out, resume=True, seed=None, insecure_m=7, insecure_s=1, panel_cols=40))
    assert params["r_digest"] == ref["r_digest"] and params["h_seed"] == ref["h_seed"]
    check_output(out, payloads)
    assert encode(opts(db, out, resume=True))["r_digest"] == ref["r_digest"]     # complete: no-op


def test_resume_errors(tmp_path, monkeypatch):
    db = write_jsonl(tmp_path / "db.jsonl", [b"a", b"b"])
    out = tmp_path / "out"
    with pytest.raises(EncodeError, match="no progress file"):
        encode(opts(db, out, resume=True))
    with monkeypatch.context() as mp:
        crash_at(mp, column=4)
        with pytest.raises(Crash):
            encode(opts(db, out, insecure_m=10, insecure_s=2, panel_cols=4))
    write_jsonl(db, [b"a", b"c"])
    with pytest.raises(EncodeError, match="differs"):
        encode(opts(db, out, resume=True))


@pytest.mark.parametrize("scratch", [None, 64])     # 64 bytes: chunks of one column
def test_verify_detects_corruption(tmp_path, rng, monkeypatch, scratch):
    if scratch is not None:
        monkeypatch.setattr(gf2, "TEMP_MEMORY_BUDGET_BYTES", scratch)
    db = write_jsonl(tmp_path / "db.jsonl", random_payloads(rng, 30, 10))
    out = tmp_path / "out"
    params = encode(opts(db, out, insecure_m=20, insecure_s=3, shard_bytes=3 * 16 + 1))     # L = 16: 3 per shard
    X = np.memmap(out / "X.bin", dtype=np.uint8, mode="r", shape=(params["t"], params["L"]))
    cps, L = params["columns_per_shard"], params["L"]
    for j in range(params["m"]):            # m <= SPOT_CHECK_COLUMNS: every column is checked
        p = shard_file(out / "site", j // cps)
        good = p.read_bytes()
        pos = (j % cps) * L + int(rng.integers(L))
        p.write_bytes(good[:pos] + bytes([good[pos] ^ (1 << int(rng.integers(8)))]) + good[pos + 1:])
        with pytest.raises(VerificationError, match=f"column {j} "):
            verify(out / "site", params, X)
        p.write_bytes(good)
    verify(out / "site", params, X)


def test_dry_run_writes_nothing(tmp_path, rng, capsys):
    db = write_jsonl(tmp_path / "db.jsonl", random_payloads(rng, 600, 12))
    assert encode(opts(db, tmp_path / "out", dry_run=True, table=True)) is None
    assert not (tmp_path / "out").exists()
    text = capsys.readouterr().out
    assert "LPN parameters: Mode A, c = 16" in text and "Mode A trade-off" in text
    assert "Estimated preprocessing time" in text


# ---------------------------------------------------------------------------------------------- CLI


@pytest.mark.parametrize("argv,msg", [
    (["--insecure-m", "10"], "given together"),
    (["--seed", "abcd"], "32 hex characters"),
    (["--shard-mib", "0"], "--shard-mib must be >= 1"),
])
def test_cli_usage_errors(tmp_path, capsys, argv, msg):
    db = write_jsonl(tmp_path / "db.jsonl", [b"x"])
    with pytest.raises(SystemExit) as ei:
        main([str(db), "--out", str(tmp_path / "out")] + argv)
    assert ei.value.code == 2
    assert msg in capsys.readouterr().err


@pytest.mark.parametrize("argv,msg", [
    ([], "infeasible"),                              # Mode A, c = 16, t = 2
    (["--c", "1"], "infeasible"),
    (["--target-comm", "100"], "Minimum achievable communication"),
])
def test_cli_errors(tmp_path, capsys, argv, msg):
    db = write_jsonl(tmp_path / "db.jsonl", [b"x", b"y"])
    assert main([str(db), "--out", str(tmp_path / "out")] + argv) == 1
    assert msg in capsys.readouterr().err
