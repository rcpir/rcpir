# `h_prg`: Expanding `h_seed` into $H$

Status: agreed spec. Identifier in `params.json`: `"h_prg": "aes128-ctr-col-v1"`.

## 1. Requirements

- **Column random access:** the client computes only its $s$ columns $H_{*,j}$, $j\in S$.
- **Throughput:** the encoder generates all of $H\in\mathbb{F}_2^{t\times m}$ ($t\cdot m$ bits).
- **Standard primitives:** bit-exact reproduction with off-the-shelf libraries in the two components
  that use $H$: the encoder (Python, `cryptography`) and the client (TypeScript, WebCrypto, see
  `docs/stack.md`). The compute server never uses $H$; the Rust snippet below is kept only for reference.

## 2. Definition (`aes128-ctr-col-v1`)

Inputs: `h_seed` $K$ (16 bytes), $t$, column index $j\in\{0,\dots,m-1\}$.

1. For $k=0,1,\dots,\lceil t/128\rceil-1$: $\;B_k=\mathrm{AES\text{-}128}_K\big(\mathrm{BE64}(j)\,\|\,\mathrm{BE64}(k)\big)$.
2. $\mathrm{col}_j$ = first $\lceil t/8\rceil$ bytes of $B_0\|B_1\|\cdots$.
3. Clear the unused trailing bits of the last byte (bits for rows $\ge t$).
4. $H_{r,j}$ = bit $r$ of $\mathrm{col}_j$, MSB-first: bit $7-(r\bmod 8)$ of byte $\lfloor r/8\rfloor$.

`col_j` is exactly the MSB-first packing of $H_{*,j}$ used everywhere else (`db_format.md` §3), so
the client computes the packed $q_c$ as $\bigoplus_{j\in S}\mathrm{col}_j$ and then flips bit $i$.

### Equivalence with standard CTR mode

Steps 1–2 are AES-128 in CTR mode with initial counter block $\mathrm{IV}_j=\mathrm{BE64}(j)\,\|\,0^{64}$
and a 128-bit big-endian counter, encrypting $\lceil t/8\rceil$ zero bytes (the low 64 bits never
overflow since $t<2^{64}\cdot 128$). Hence:

```python
# Python, package `cryptography`
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
def h_column(seed: bytes, t: int, j: int) -> bytes:
    nbytes = (t + 7) // 8
    iv = j.to_bytes(8, "big") + bytes(8)
    enc = Cipher(algorithms.AES(seed), modes.CTR(iv)).encryptor()
    col = bytearray(enc.update(bytes(nbytes)) + enc.finalize())
    if t % 8:
        col[-1] &= (0xFF << (8 - t % 8)) & 0xFF   # zero rows >= t
    return bytes(col)
```

```rust
// Rust, crates `aes` + `ctr` (+ `cipher`)
use aes::Aes128;
use ctr::cipher::{KeyIvInit, StreamCipher};
type Ctr = ctr::Ctr128BE<Aes128>;

fn h_column(seed: &[u8; 16], t: usize, j: u64) -> Vec<u8> {
    let mut iv = [0u8; 16];
    iv[..8].copy_from_slice(&j.to_be_bytes());
    let mut col = vec![0u8; (t + 7) / 8];
    Ctr::new(seed.into(), &iv.into()).apply_keystream(&mut col);
    if t % 8 != 0 {
        *col.last_mut().unwrap() &= 0xFFu8 << (8 - t % 8);
    }
    col
}
```

(Implementations: `common/src/rcpir_common/hprg.py` (`h_column`, and the faster `h_panel` used by the
encoder) and `client/src/h_prg.ts` (WebCrypto). Both are checked against `testvectors/vectors/h_prg.json`,
so the Python (`cryptography`) and WebCrypto AES-CTR implementations agree on every case. The Rust
snippet has never been compiled; nothing in the system uses it.)

## 3. Seed

- 16 bytes from the OS CSPRNG, drawn once by the encoder, stored as 32 lowercase hex characters in
  `params.json` (`h_seed`). It is **public**.
- A new seed (and therefore re-encoding) is required after $Q=2^{32}$ queries.

## 4. Cost

- Client: $s\lceil t/128\rceil$ AES blocks per query (e.g. $45\cdot 1024$ blocks for $t=2^{17}$), negligible.
- Encoder: $m\lceil t/128\rceil$ AES blocks, i.e. $tm/8$ bytes of keystream (32 GiB for $t=2^{17}$, $c=16$).
  To be measured as part of the encoder pipeline.

## 5. Security modeling

The paper assumes dLPN for a uniformly random public $H$. Deriving $H$ from a public seed adds the
heuristic assumption that dLPN still holds for $H=\mathrm{AES}_K$-expanded columns with $K$ public,
i.e. that AES with a known random key behaves like a random function for this purpose. This is the
same kind of assumption FrodoKEM makes when it expands its public LWE matrix $A$ from a seed with
AES128 or SHAKE128.

## References

- FrodoKEM specification (matrix $A$ generation with AES128 / SHAKE128): https://frodokem.org/files/FrodoKEM-specification-20210604.pdf
- IETF draft-longa-cfrg-frodokem-03: https://www.ietf.org/archive/id/draft-longa-cfrg-frodokem-03.txt
