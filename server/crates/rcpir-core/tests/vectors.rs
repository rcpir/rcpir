//! Conformance with the cross-language vectors in `testvectors/vectors/`.

use std::path::PathBuf;

use rcpir_core::bits::is_well_formed;
use rcpir_core::fixture::{naive_answer, unit_query};
use rcpir_core::xdb::sha256_digest;
use rcpir_core::{Backend, CpuBackend, Params};
use serde_json::Value;

fn load(name: &str) -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../testvectors/vectors")
        .join(name);
    serde_json::from_slice(&std::fs::read(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))).unwrap()
}

fn cases<'a>(v: &'a Value, key: &str) -> &'a Vec<Value> {
    v[key].as_array().unwrap()
}

fn unhex(v: &Value) -> Vec<u8> {
    hex::decode(v.as_str().unwrap()).unwrap()
}

fn int(v: &Value) -> usize {
    v.as_u64().unwrap() as usize
}

/// The compute server parses q_c: valid packings are accepted, malformed ones rejected.
#[test]
fn bitpack() {
    let v = load("bitpack.json");
    for c in cases(&v, "valid") {
        assert!(is_well_formed(&unhex(&c["packed_hex"]), int(&c["t"])), "{}", c["name"]);
    }
    for c in cases(&v, "invalid") {
        assert!(!is_well_formed(&unhex(&c["packed_hex"]), int(&c["t"])), "{}", c["name"]);
    }
}

/// The fields of `params.json` the compute server reads (`rcpir_core::Params`).
const SERVER_FIELDS: [&str; 4] = ["format_version", "t", "L", "db_digest"];

/// Valid fixtures parse. Each invalid fixture is the spec example with one rule violated: the
/// server rejects it iff a field it reads differs from the spec example (it ignores the others).
#[test]
fn params_fixtures() {
    let v = load("params.json");
    let parse = |c: &Value| Params::parse(c["params"].to_string().as_bytes());
    for c in cases(&v, "valid") {
        parse(c).unwrap_or_else(|e| panic!("{}: {e}", c["name"]));
    }
    let base = &cases(&v, "valid").iter().find(|c| c["name"] == "spec_example").unwrap()["params"];
    let mut rejected = 0;
    for c in cases(&v, "invalid") {
        let touches_server_field = SERVER_FIELDS.iter().any(|&f| c["params"].get(f) != base.get(f));
        assert_eq!(parse(c).is_err(), touches_server_field, "{}", c["name"]);
        rejected += usize::from(touches_server_field);
    }
    assert!(rejected > 0, "no invalid fixture concerns a server field");
}

/// X.bin layout: the digest matches, and the backend's X e_j is block j's column.
#[test]
fn x_bin_layout_and_answers() {
    let v = load("db_format.json");
    for c in cases(&v, "valid") {
        let x = unhex(&c["x_bin_hex"]);
        let (t, l) = (int(&c["t"]), int(&c["L"]));
        assert_eq!(sha256_digest(&x), c["db_digest"].as_str().unwrap());
        let backend = CpuBackend::new(x.clone(), t, l, 2, None).unwrap();
        for j in 0..t {
            let q = unit_query(t, j);
            let mut out = vec![0u8; l];
            backend.answer_batch(&[&q], &mut [&mut out]);
            assert_eq!(out, naive_answer(&x, t, l, &q));
            let payload = unhex(&c["payloads_hex"][j]);
            assert_eq!(u32::from_be_bytes(out[..4].try_into().unwrap()) as usize, payload.len());
            assert_eq!(
                &out[4..4 + payload.len()],
                payload.as_slice(),
                "{} block {j}",
                c["name"]
            );
        }
    }
}
