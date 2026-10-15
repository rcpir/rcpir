"""Encoder pipeline (docs/encoder.md §2, §4, §5). The verify step (6) is in verify.py.

Output:
    DIR/params.json                       written last; marks a complete run
    DIR/X.bin                             for the compute server
    DIR/site/.well-known/rc-pir.json      copy of params.json
    DIR/site/rc-pir/r/xxxxxxxx            the shards of R = XH: columns_per_shard columns of L bytes each
    DIR/.rcpir-progress.json              only while running (state for --resume)
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rcpir_common import hprg, params as params_spec, protocol

from . import __version__, dbformat, gf2, lpn
from .verify import verify

PROGRESS_FILE = ".rcpir-progress.json"
DEFAULT_SHARD_BYTES = 64 << 20          # upper bound on the size of a shard of R (--shard-mib 64)


class EncodeError(Exception):
    pass


@dataclass
class EncodeOptions:
    db: Path
    out: Path
    lambda_value: int = lpn.DEFAULT_LAMBDA
    c: float = lpn.DEFAULT_C                # Mode A (used unless one of the options below is set)
    target_comm: int | None = None          # Mode B
    insecure_m: int | None = None           # test-only override (together with insecure_s)
    insecure_s: int | None = None
    table: bool = False
    dry_run: bool = False
    yes: bool = False
    seed: bytes | None = None
    device: str = "cpu"
    verify: bool = True
    resume: bool = False
    panel_cols: int | None = None           # default: the backend's panel_cols
    shard_bytes: int = DEFAULT_SHARD_BYTES  # upper bound on the shard size (CLI: --shard-mib)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def shard_file(site: Path, k: int) -> Path:
    """File of shard k of R inside the site directory (protocol.md §2)."""
    return site / protocol.shard_path(k).lstrip("/")


def columns_per_shard(L: int, m: int, shard_bytes: int) -> int:
    """Most whole columns in a shard of at most shard_bytes (no column spans two shards), at most m."""
    if shard_bytes < L:
        raise EncodeError(f"the shard size bound ({shard_bytes} bytes) is smaller than one column (L = {L} bytes)")
    return min(shard_bytes // L, m)


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------------------------
# Steps 1-3: scan, parameters, report, seed and progress state

def select_parameters(opts: EncodeOptions, scan_result: dbformat.ScanResult) -> lpn.Selection:
    if opts.insecure_m is not None:
        return lpn.insecure_override(opts.lambda_value, scan_result.t, scan_result.ell, opts.insecure_m, opts.insecure_s)
    if opts.target_comm is not None:
        return lpn.mode_b(opts.lambda_value, scan_result.t, scan_result.ell, opts.target_comm)
    return lpn.mode_a(opts.lambda_value, scan_result.t, scan_result.ell, opts.c)


def db_report(scan_result: dbformat.ScanResult, s: int) -> str:
    """db_format.md §5."""
    lines = ["Database",
             f"  t = {scan_result.t} blocks, max payload = {scan_result.max_payload} bytes, L = {scan_result.L} bytes, ell = {scan_result.ell} bits",
             f"  n = {scan_result.n} bits, padding overhead = {scan_result.padding_overhead:.1%}"]
    if scan_result.padding_overhead > 0.5:
        lines.append("  WARNING: padding overhead above 50%: one large block inflates storage and "
                     "communication for all blocks")
    # Communication ~ t + (s+1) ell with t * ell = n fixed is smallest when t = (s+1) ell.
    ratio = scan_result.t / ((s + 1) * scan_result.ell)
    lines.append(f"  shape balance: t / ((s+1) ell) = {ratio:.3g} (best near 1)")
    if not 0.25 <= ratio <= 4:      # i.e. communication more than 25% above the balanced shape
        lines.append(f"  WARNING: unbalanced shape; consider {'splitting' if ratio < 1 else 'merging'} "
                     f"blocks (the encoder never reshapes)")
    return "\n".join(lines)


def estimate_seconds(matmul, device: str, t: int, L: int, m: int) -> float:
    """Time h_prg and R = XH on a small random problem with the same backend and extrapolate.

    h_prg scales with t m and the matmul with t L m; writing R is not included.
    The GPU problem is larger so that its fixed per-call costs do not dominate.
    """
    tt, LL, mp = (min(t, 32768), min(L, 4096), min(m, 8192)) if device == "cuda" else \
        (min(t, 4096), min(L, 1024), min(m, 1024))
    X = np.random.default_rng(0).integers(0, 256, size=(tt, LL), dtype=np.uint8)
    start = time.perf_counter()
    H = hprg.h_panel(bytes(16), tt, 0, mp)
    prg = time.perf_counter() - start
    matmul(X, H, tt)                     # warm-up (BLAS start-up; CUDA compile and upload of X)
    start = time.perf_counter()
    matmul(X, H, tt)
    mm = time.perf_counter() - start
    return prg * (t / tt) * (m / mp) + mm * (t / tt) * (L / LL) * (m / mp)


def print_report(opts: EncodeOptions, scan_result: dbformat.ScanResult, selection: lpn.Selection,
                 matmul) -> None:
    """Database report, LPN parameter report, optional --table and the estimated preprocessing time."""
    print(db_report(scan_result, selection.s))
    print(lpn.report(selection))
    if opts.table:
        print(lpn.table(opts.lambda_value, scan_result.t, scan_result.ell))
    L, m = scan_result.L, selection.m
    cps = columns_per_shard(L, m, opts.shard_bytes)
    print(f"R: {m} columns of {L} bytes in {-(-m // cps)} shards of {cps} columns ({cps * L} bytes each, "
          f"the last one possibly smaller)")
    est = estimate_seconds(matmul, opts.device, scan_result.t, L, m)
    print(f"Estimated preprocessing time ({opts.device}): ~{est:.0f} s (without writing R)", flush=True)


def new_state(opts: EncodeOptions, scan_result: dbformat.ScanResult, selection: lpn.Selection,
              progress_path: Path) -> dict:
    """Fresh run: choose h_seed and write the progress file before any column of R is written."""
    seed = opts.seed if opts.seed is not None else secrets.token_bytes(16)
    state = {"input_sha256": scan_result.input_sha256, "m": selection.m, "s": selection.s,
             "columns_per_shard": columns_per_shard(scan_result.L, selection.m, opts.shard_bytes),
             "h_seed": seed.hex(), "security": selection.security_object(), "columns_done": 0}
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    # CR: Do we really need write_atomic here? What is the reason?
    write_atomic(progress_path, json.dumps(state).encode())
    return state


def load_state(progress_path: Path, scan_result: dbformat.ScanResult) -> dict:
    """--resume: parameters and seed come from the progress file; the command-line choices are ignored."""
    state = json.loads(progress_path.read_text())
    if state["input_sha256"] != scan_result.input_sha256:
        raise EncodeError("--resume: the input file differs from the interrupted run")
    log(f"resuming: {state['columns_done']} of {state['m']} columns already written")
    return state


def confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


# ----------------------------------------------------------------------------------------------
# Step 5: R = XH

def compute_r(X: np.ndarray, seed: bytes, site: Path, state: dict, progress_path: Path, matmul,
              width: int) -> None:
    """R = XH by column panels of H of `width` columns, starting at column state["columns_done"].

    Writes the panel's columns into their shards (a panel may span several shards), then updates
    state["columns_done"] and saves the progress file, so that --resume restarts at the first
    incomplete panel. Columns are always written at their final offsets, so a crash in the middle
    of a panel leaves nothing that the resumed run does not overwrite.
    """
    t, m, cps = X.shape[0], state["m"], state["columns_per_shard"]
    shard_file(site, 0).parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    for j0 in range(state["columns_done"], m, width):
        R = matmul(X, hprg.h_panel(seed, t, j0, min(width, m - j0)), t)
        j1 = j0 + len(R)
        for k in range(j0 // cps, (j1 - 1) // cps + 1):
            a, b = max(j0, k * cps), min(j1, (k + 1) * cps)        # columns of the panel in shard k
            path = shard_file(site, k)
            with open(path, "r+b" if path.exists() else "wb") as f:
                f.seek((a - k * cps) * R.shape[1])
                f.write(R[a - j0:b - j0])
        state["columns_done"] = j1
        write_atomic(progress_path, json.dumps(state).encode())
        log(f"  columns {state['columns_done']}/{m}, {time.perf_counter() - start:.1f} s")


DIGEST_CHUNK = 64 << 20                 # r_digest reads the shards in chunks: RAM stays flat for one huge shard


def r_digest(site: Path, m: int, cps: int) -> str:
    """`r_digest` of params.json: SHA-256 of the shards in order = of all m columns in index order."""
    h = hashlib.sha256()
    for k in range(-(-m // cps)):
        with open(shard_file(site, k), "rb") as f:
            while chunk := f.read(DIGEST_CHUNK):
                h.update(chunk)
    return protocol.digest_tag(h.hexdigest())


# ----------------------------------------------------------------------------------------------

def encode(opts: EncodeOptions) -> dict | None:
    """Run the pipeline. Returns params.json as a dict (None for --dry-run or a declined prompt)."""
    out, site = opts.out, opts.out / "site"
    progress_path = out / PROGRESS_FILE
    matmul, panel_cols = gf2.get_backend(opts.device)

    if opts.resume and (out / "params.json").exists():
        log("the run is already complete")
        return json.loads((out / "params.json").read_text())
    if opts.resume and not progress_path.exists():
        raise EncodeError(f"--resume: no progress file in {out}")
    if not opts.resume and not opts.dry_run and out.exists() and any(out.iterdir()):
        raise EncodeError(f"output directory {out} is not empty (use --resume to continue an interrupted run)")

    # 1. scan
    log(f"scanning {opts.db} ...")
    scan_result = dbformat.scan(opts.db)

    if opts.resume:
        state = load_state(progress_path, scan_result)
    else:
        # 2. parameters and report
        selection = select_parameters(opts, scan_result)
        print_report(opts, scan_result, selection, matmul)
        if opts.dry_run:
            return None
        if selection.mode == "B" and not opts.yes and not confirm("Proceed with these parameters?"):
            log("aborted (pass --yes to skip the confirmation)")
            return None
        # 3. seed and progress file
        state = new_state(opts, scan_result, selection, progress_path)

    t, L, m = scan_result.t, scan_result.L, state["m"]
    seed = bytes.fromhex(state["h_seed"])

    # 4. pack X.bin (also on resume: it is cheap compared to step 5 and deterministic)
    log("packing X.bin ...")
    db_digest = dbformat.pack(opts.db, scan_result, out / "X.bin")
    X = np.memmap(out / "X.bin", dtype=np.uint8, mode="r", shape=(t, L))

    # 5. R = XH and its digest
    compute_r(X, seed, site, state, progress_path, matmul, opts.panel_cols or panel_cols(t, L))

    params = {
        "format_version": params_spec.FORMAT_VERSION,
        "t": t,
        "ell": 8 * L,
        "L": L,
        "m": m,
        "s": state["s"],
        "h_prg": hprg.H_PRG,
        "h_seed": state["h_seed"],
        "noise": params_spec.NOISE,
        "db_digest": protocol.digest_tag(db_digest),
        "r_digest": r_digest(site, m, state["columns_per_shard"]),
        "columns_per_shard": state["columns_per_shard"],
        "security": state["security"],
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "encoder_version": __version__,
    }

    params_spec.validate(params)        # what the client and the server will check

    # 6. verify
    if opts.verify:
        verify(site, params, X)

    # 7. params.json last
    data = (json.dumps(params, indent=2) + "\n").encode()
    well_known = site / protocol.WELL_KNOWN_PATH.lstrip("/")
    well_known.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(well_known, data)
    write_atomic(out / "params.json", data)
    progress_path.unlink()
    log(f"done: {out / 'params.json'}")
    return params

