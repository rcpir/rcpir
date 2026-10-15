//! Core of the RC-PIR compute server: reading `params.json`, loading `X.bin`, and the
//! backend computing `X q` over `F_2`. Shared by the HTTP server and the benchmarks.
//!
//! Specs: `docs/compute_server.md`, `docs/params_format.md`, `docs/db_format.md`.

pub mod backend;
pub mod bits;
pub mod fixture;
pub mod params;
pub mod xdb;

pub use backend::{Backend, CpuBackend};
pub use params::Params;
