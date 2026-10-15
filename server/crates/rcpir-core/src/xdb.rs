//! Loading the packed database `X.bin` (`docs/db_format.md` §4): column-major,
//! `t` consecutive columns of `L` bytes each.

use std::path::Path;

use anyhow::{Context, Result, ensure};
use sha2::{Digest, Sha256};

use crate::params::Params;

/// Reads `X.bin` fully into RAM and checks its size (`t * L` bytes) and, if `verify`,
/// its SHA-256 against `db_digest`.
pub fn load_x(path: &Path, params: &Params, verify: bool) -> Result<Vec<u8>> {
    let x = std::fs::read(path).with_context(|| format!("cannot read {}", path.display()))?;
    ensure!(
        x.len() == params.t * params.l,
        "X.bin has {} bytes but params.json requires t * L = {}",
        x.len(),
        params.t * params.l
    );
    if verify {
        let actual = sha256_digest(&x);
        ensure!(
            actual == params.db_digest,
            "db_digest mismatch: params.json says {}, X.bin hashes to {actual}",
            params.db_digest
        );
    }
    Ok(x)
}

/// `sha256:<lowercase hex>` of `data`.
pub fn sha256_digest(data: &[u8]) -> String {
    format!("sha256:{}", hex::encode(Sha256::digest(data)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fixture;
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    #[test]
    fn load_checks_size_and_digest() {
        let dir = std::env::temp_dir().join(format!("rcpir-xdb-test-{}", std::process::id()));
        let x = fixture::random_x(13, 24, &mut StdRng::seed_from_u64(7));
        let params = Params::parse(fixture::params_json(13, 24, &sha256_digest(&x)).as_bytes()).unwrap();
        std::fs::create_dir_all(&dir).unwrap();
        let x_path = dir.join("X.bin");
        std::fs::write(&x_path, &x).unwrap();
        assert_eq!(load_x(&x_path, &params, true).unwrap().len(), 13 * 24);

        let mut wrong_digest = params.clone();
        wrong_digest.db_digest = format!("sha256:{}", "00".repeat(32));
        assert!(load_x(&x_path, &wrong_digest, true).is_err());
        assert!(load_x(&x_path, &wrong_digest, false).is_ok());

        let mut wrong_size = params.clone();
        wrong_size.t = 12;
        assert!(load_x(&x_path, &wrong_size, false).is_err());
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
