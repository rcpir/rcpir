//! Deterministic test fixtures: random `X`, random queries, a bit-level reference answer and a
//! matching `params.json`. Used by the tests; not used by the server.

use rand::RngCore;
use rand::rngs::StdRng;

use crate::bits::{get_bit, tail_mask};

/// Random column-major `X` with `t` columns of `l` bytes.
pub fn random_x(t: usize, l: usize, rng: &mut StdRng) -> Vec<u8> {
    let mut x = vec![0u8; t * l];
    rng.fill_bytes(&mut x);
    x
}

/// Random packed query in `F_2^t` with zero trailing bits.
pub fn random_query(t: usize, rng: &mut StdRng) -> Vec<u8> {
    let mut q = vec![0u8; t.div_ceil(8)];
    rng.fill_bytes(&mut q);
    *q.last_mut().unwrap() &= tail_mask(t);
    q
}

/// Unit query `e_j` in `F_2^t`.
pub fn unit_query(t: usize, j: usize) -> Vec<u8> {
    let mut q = vec![0u8; t.div_ceil(8)];
    q[j / 8] = 0x80 >> (j % 8);
    q
}

/// Bit-level reference for `X q`: answer bit `r` is `XOR_j (X[r][j] AND q[j])`, where row `r`
/// of column `j` is bit `r` of the column. Deliberately slow and independent of the backend.
pub fn naive_answer(x: &[u8], t: usize, l: usize, q: &[u8]) -> Vec<u8> {
    let mut out = vec![0u8; l];
    for r in 0..8 * l {
        let column_has_bit = |j: usize| get_bit(&x[j * l..(j + 1) * l], r);
        let bit = (0..t).filter(|&j| get_bit(q, j) && column_has_bit(j)).count() % 2 == 1;
        if bit {
            out[r / 8] |= 0x80 >> (r % 8);
        }
    }
    out
}

/// A valid `params.json` for a DB of shape `t x L`. `m`, `s`, `h_seed` and `r_digest` are
/// placeholders (the server does not use them). `security` marks the test-only override.
pub fn params_json(t: usize, l: usize, db_digest: &str) -> String {
    let p = serde_json::json!({
        "format_version": 1,
        "t": t,
        "ell": 8 * l,
        "L": l,
        "m": 16 * t,
        "s": 4,
        "h_prg": "aes128-ctr-col-v1",
        "h_seed": "000102030405060708090a0b0c0d0e0f",
        "noise": "fixed-weight",
        "db_digest": db_digest,
        "r_digest": format!("sha256:{}", "0".repeat(64)),
        "security": {"mode": "insecure-override", "insecure": true},
        "created": "2026-10-09T00:00:00Z",
        "encoder_version": "test-fixture"
    });
    serde_json::to_string_pretty(&p).unwrap() + "\n"
}
