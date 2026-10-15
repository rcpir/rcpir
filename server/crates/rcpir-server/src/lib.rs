//! RC-PIR compute server (`docs/compute_server.md`, `docs/protocol.md` §3, §5).

pub mod app;
pub mod batcher;
pub mod config;

pub use app::{AppState, router};
pub use batcher::{Batcher, QueryError};
pub use config::Args;
