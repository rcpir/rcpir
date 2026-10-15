# Database Input Format

Status: agreed spec ( JSONL input, one block per column, 4-byte big-endian length header, static DB).
Notation follows `docs/lpn_parameters.md`: $X\in\mathbb{F}_2^{\ell\times t}$, client retrieves one column.

## 1. Model

The user supplies an ordered list of **blocks** (byte strings). Block $j$ becomes column $j$ of $X$:

- $t$ = number of blocks,
- $\ell$ = bit length of the largest encoded block (header + payload), rounded up for alignment.

There is no automatic $\sqrt n\times\sqrt n$ reshaping; the shape is whatever the block list implies.
The client retrieves a block by its index $j\in\{0,\dots,t-1\}$.

## 2. Input file (JSONL)

- UTF-8, one JSON object per line, `\n` line endings (a trailing newline is allowed; blank lines are not).
- Line $j$ (0-based) is block $j$. Error messages give **1-based** line numbers (like editors).
- A line containing only whitespace counts as blank (an error). Invalid UTF-8 anywhere is an error.
- Required field `"data"`: the payload, **standard base64** (RFC 4648 §4, alphabet `A–Z a–z 0–9 + /`, with `=` padding).
- Other fields are ignored (e.g. a `"key"` for the user's own bookkeeping).
- Payload length: any size from $0$ up to $2^{32}-1$ bytes (limited only by the header width).

Example:

```json
{"data": "SGVsbG8gd29ybGQ="}
{"data": "", "key": "empty-block"}
{"data": "AAECAwQ="}
```

## 3. Block encoding (one column of $X$)

```
column_j = block_header | payload | zero padding        (exactly L bytes)
block_header = u32 big-endian, value = |payload| in bytes
```

- $L = \mathrm{roundup}_8(4 + \max_j |\text{payload}_j|)$ bytes, so $\ell = 8L$ bits (a multiple of 64).
- Zero padding is unambiguous because the header carries the length. Decoders do not check the
  padding bytes (only `len ≤ L-4`).
- Header format and bit order are fixed by this spec (not configurable, not stored in `params.json`).
- Bit order: **MSB-first** everywhere (network order). Element $8b+k$ of a packed vector is bit
  $7-k$ of byte $b$ (numpy `bitorder='big'`, the default). For $X$: row $8b+k$ of column $j$ is
  bit $7-k$ of byte $b$ of the column. The same rule packs every $\mathbb{F}_2$ vector in the system
  (columns of $H$, the compute query $q_c\in\mathbb{F}_2^t$); unused trailing bits are zero.
- All multi-byte integers are big-endian.

Decoding (client): recover column $j$ ($L$ bytes), read `len = u32_be(bytes[0:4])`, return `bytes[4 : 4+len]`;
reject if `len > L-4`.

## 4. Preprocessing passes

The input is read twice, streaming:

1. **Scan:** validate every line, count $t$, track $\max|\text{payload}|$ and $\sum|\text{payload}|$.
2. **Pack:** decode each payload and write column $j$ ($L$ bytes) into the packed $X$ file
   (column-major: $t$ consecutive columns of $L$ bytes). The compute server uses this file as is.

Errors (abort with line number): invalid JSON, missing/non-string `"data"`, invalid base64,
payload ≥ $2^{32}$ bytes, empty file.

## 5. Report printed after the scan

- $t$, $\max|\text{payload}|$, $L$, $\ell$, $n=t\ell$ bits.
- Padding overhead: $1-\dfrac{\sum_j(4+|\text{payload}_j|)}{tL}$ — warn above a threshold
  (e.g. 50%), since one outlier block inflates storage and communication for all blocks.
- Shape balance: communication $\approx t+(s+1)\ell+s\lceil\log_2 m\rceil$ is minimised near
  $t\approx(s+1)\ell$; warn when far off (the tool never reshapes; splitting/merging is left to the user).
- LPN parameters, storage and communication as in `docs/lpn_parameters.md` §7, with $t,\ell$ taken from the DB.

## 6. Public information

$t$ and $\ell$ (hence the number of blocks and the maximum block size) are public. Individual block
lengths are not revealed beyond that: every retrieval returns a full $\ell$-bit column.

## 7. Assumptions

- No minimum on $t$. ($t$ is also the LPN dimension; if it is too small the parameter selector
  reports infeasibility or a very large $c$.)
- Static database. Changing any block changes every column of $R=XH$, so updates mean re-encoding.
- Large blocks are allowed; their cost (communication $\approx s\ell$, storage $\ell m$) appears in the report.
