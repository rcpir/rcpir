//! `params.json` parsing (`docs/params_format.md`).
//!
//! The compute server reads only the fields it uses and ignores all others (`m`, `s`, `h_prg`,
//! `h_seed`, `noise`, `ell`, `r_digest` and the metadata): they matter to the client and the
//! encoder, which validate the whole file. The file is still served byte-identical at
//! `/.well-known/rc-pir.json`.

use anyhow::{Result, ensure};
use serde::Deserialize;

/// The fields of `params.json` that the compute server uses.
#[derive(Debug, Clone, Deserialize)]
pub struct Params {
    /// Must be 1: a later format may change the layout of `X.bin` or of the queries.
    pub format_version: u64,
    /// Number of columns of `X`; queries are `ceil(t/8)` bytes.
    pub t: usize,
    /// Column length in bytes; answers are `L` bytes.
    #[serde(rename = "L")]
    pub l: usize,
    /// `sha256:<hex>` of `X.bin`: checked at startup and sent with every answer.
    pub db_digest: String,
}

/// A SHA-256 digest is 32 bytes, written as lowercase hex.
const SHA256_HEX_LEN: usize = 64;

fn is_sha256_digest(s: &str) -> bool {
    s.strip_prefix("sha256:")
        .is_some_and(|h| h.len() == SHA256_HEX_LEN && h.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')))
}

impl Params {
    /// Parses `params.json` and checks the rules of `params_format.md` §4 for the fields above.
    pub fn parse(bytes: &[u8]) -> Result<Params> {
        let p: Params = serde_json::from_slice(bytes)?;
        ensure!(p.format_version == 1, "format_version must be 1");
        ensure!(p.t >= 1, "t must be >= 1");
        ensure!(p.l >= 8 && p.l.is_multiple_of(8), "L must be >= 8 and a multiple of 8");
        ensure!(
            is_sha256_digest(&p.db_digest),
            "db_digest must be sha256:<64 lowercase hex>"
        );
        ensure!(p.t.checked_mul(p.l).is_some(), "t * L is too large");
        Ok(p)
    }

    /// Query length in bytes, `ceil(t/8)`.
    pub fn query_len(&self) -> usize {
        self.t.div_ceil(8)
    }
}
