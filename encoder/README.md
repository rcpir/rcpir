# `rcpir-encoder`

Encoder for the √n RC-PIR (LPN over $\mathbb F_2$). Implements `docs/encoder.md` with a CPU backend
(tests, small DBs) and a CUDA backend (1-bit tensor cores, `gf2_cuda.py`).

Specs: `docs/encoder.md`, `docs/db_format.md`, `docs/params_format.md`, `docs/h_prg.md`,
`docs/lpn_parameters.md`, `docs/protocol.md`.

## Setup and tests

The encoder depends on `rcpir_common` (`../common`: h_prg, block encoding, paths, params validation).

```bash
conda env create -p .env -f environment.yml                    # at the repository root
cd encoder
../.env/bin/python -m pytest -q                                # no install needed (pythonpath = src, ../common/src)
../.env/bin/pip install -e ../common -e .                      # optional: provides the `rcpir-encode` command
../.env/bin/pip install "cupy-cuda12x[ctk]"                    # for --device cuda (NVIDIA GPU, sm_80+)
```

Without installing: `PYTHONPATH=src:../common/src ../.env/bin/python -m rcpir_encoder ...`.

## CLI

```
rcpir-encode DB.jsonl --out DIR [--lambda 128] (--c C | --target-comm BITS | --insecure-m M --insecure-s S)
             [--table] [--dry-run] [--yes] [--seed HEX] [--device cpu|cuda] [--shard-mib 64] [--no-verify] [--resume]
```

| Flag | Meaning |
|---|---|
| `--c C` | Mode A (default, `C = 16`): storage factor $c=m/t$ → smallest secure $s$. |
| `--target-comm BITS` | Mode B: target total communication → smallest secure $m$. Asks for confirmation unless `--yes` (no answer, e.g. empty stdin, means no). |
| `--insecure-m M --insecure-s S` | **Test only.** Skip parameter selection and use $(m,s)$ as given. Prints a loud warning; `params.json` gets `security.mode = "insecure-override"`, `security.insecure = true` (attack bits are still computed). Needed for tiny DBs, where Mode A is infeasible. |
| `--table` | Add the Mode A trade-off table for $c\in\{2,4,16,256,4096\}$ to the report. |
| `--dry-run` | Scan, select parameters, print the report (and the time estimate), write nothing. |
| `--seed HEX` | Fixed `h_seed` (32 hex chars). Default: 16 bytes from the OS CSPRNG. |
| `--device` | `cpu` (default) or `cuda` (needs CuPy and an sm_80+ NVIDIA GPU; all of $X$ must fit in VRAM). |
| `--shard-mib` | Upper bound on the shard size of $R$ in MiB (default 64). Shards hold whole columns: `columns_per_shard` $=\min(\lfloor 2^{20}\cdot$`MIB`$/L\rfloor, m)$, stored in `params.json`. |
| `--no-verify` | Skip the verification step. |
| `--resume` | Continue an interrupted run in `DIR` (see below). |

Exit codes: `0` success, `1` input/parameter/verification error, `2` usage error (from argparse).

The report (stdout) contains the database summary (`db_format.md` §5: padding overhead, shape balance
warnings), the LPN parameters (`lpn_parameters.md` §7) and an estimated preprocessing time.
The estimate comes from timing the backend and `h_prg` on a small random problem at start-up; it is
rough (about 2× too high in the runs below).
Progress messages go to stderr.

### Output

```
DIR/
  params.json                     # written last; its presence marks a complete run
  X.bin                           # packed X for the compute server (column-major, t x L bytes)
  site/                           # upload as-is to the retrieval host
    .well-known/rc-pir.json       # byte-identical copy of params.json
    rc-pir/r/xxxxxxxx             # shards of R = XH: columns_per_shard columns of L bytes each
```

While running, `DIR/.rcpir-progress.json` holds the state for `--resume`. It is deleted at the end.
A fresh run refuses a non-empty `DIR`.

## Pipeline (`pipeline.py`)

1. **Scan** (`dbformat.scan`): validates every line (errors carry 1-based line numbers) and computes
   $t$, $L$ and the SHA-256 of the input file.
2. **Select** (`lpn.mode_a` / `lpn.mode_b` / `lpn.insecure_override`), then print the report.
3. **Seed.**
4. **Pack** `X.bin` (`dbformat.pack`, second streaming pass), which yields `db_digest`.
5. **$R=XH$ by column panels of $H$:**
   - Each panel is generated with `rcpir_common.hprg.h_panel` (one AES-CTR encryptor per column).
   - It is multiplied by the backend, and the panel's columns are written at their offsets in their shards
     (a panel may span shards).
   - The progress file is updated after every panel.
   - At the end, `r_digest` is computed by reading the shards in order.
6. **Verify** (`verify.py`, unless `--no-verify`): spot check of 1000 random columns (all if $m\le1000$),
   recomputed with `matmul_cpu` and compared with the columns in the shards. If a fraction $f$ of the columns is wrong,
   it passes with probability $\le(1-f)^{1000}$; rare isolated errors (a bit flip) are not caught. Against the
   CUDA backend it is an independent computation; with `--device cpu` it only checks writes and resume.
   `X.bin` against the input is not checked here (see `e2e/retrieve_all.mjs`).
7. **Validate** `params.json` with `rcpir_common.params.validate`, write `site/.well-known/rc-pir.json`,
   then `params.json` (atomic rename), then delete the progress file.

**Resume.**
- The parameters and seed come from the progress file; mode flags and `--seed` on the command line are
  ignored.
- The input file must be unchanged: its SHA-256 is checked.
- `X.bin` is always repacked (cheap compared to step 5, and deterministic).
- Encoding continues at the first incomplete panel. Resuming a complete run is a no-op.

## `gf2_matmul` interface (`gf2.py`): where the GPU backend plugs in

All arrays use the packed, column-major, MSB-first layouts that are written to disk, so a backend never
has to repack anything:

| Argument | Shape / dtype | Content |
|---|---|---|
| `X` | `(t, L) uint8` (may be a read-only `np.memmap` of `X.bin`) | `X[r]` = column $r$ of $X$ |
| `H` | `(mp, ceil(t/8)) uint8` | `H[k]` = column $j_0+k$ of $H$, as returned by `rcpir_common.hprg.h_panel` |
| result | `(mp, L) uint8` | row $k$ = column $j_0+k$ of $R$ = XOR of `X[r]` over $r$ with $H_{r,j_0+k}=1$ (exactly the bytes of the column in its shard) |

A backend is a function `matmul(X, H, t) -> np.ndarray` plus a `panel_cols(t, L)`, returned by
`gf2.get_backend(device)`. `test_matmul_cuda` checks the CUDA backend bit for bit against the CPU one.

**CPU backend (`matmul_cpu`).**
- Method: unpack bits, run a float32 BLAS GEMM, take the parity of the integer result and repack.
- Exactness: float32 holds the integer sums exactly up to $2^{24}$, so the CPU backend requires $t\le 2^{24}$.
- Memory: the byte range of the columns of $X$ is processed in tiles (about 1 GiB of scratch memory).
- Measured throughput: ≈3–5e11 bit-MAC/s on the i7-14700KF. That is about 70–100× slower than the M4RI
  multi-process baseline and 350–500× slower than the GPU 1-bit kernel (`--device cuda`), so it is
  meant for tests and small databases.

## Measured runs (i7-14700KF, WSL2)

| DB | Parameters | $R=XH$ time | Result |
|---|---|---|---|
| $t=3$, 11-byte max payload | insecure $m=40$, $s=5$ | <0.1 s | verify OK |
| $t=1000$, ≤199-byte payloads ($L=208$) | insecure $m=4000$, $s=12$ | <1 s | verify OK |
| $t=4096$, ≤4092-byte payloads ($L=4096$, $n$ = 16 MiB) | Mode A, $c=16$: $m=65536$, $s=43$, $\lambda'=172$, comm 176.6 KiB | 18–23 s depending on machine load (2.0–2.4 GB RSS) | verify OK (3.4 s) |

## Modules

| Module | Content |
|---|---|
| `dbformat.py` | JSONL validation, scan/pack (column encoding: `rcpir_common.blocks`) |
| `lpn.py` | λ′, attack bounds, `secure`, `m_min`, Mode A/B, insecure override, report, table |
| `gf2.py` | `matmul_cpu`, `panel_cols`, `get_backend` |
| `gf2_cuda.py` | `matmul_cuda` (1-bit tensor-core kernel via CuPy), `panel_cols` |
| `pipeline.py` | encode / resume / time estimate, `params.json`, shards |
| `verify.py` | verify step: spot check of random columns of $R=XH$ on the CPU |
| `cli.py` | argument parsing |
