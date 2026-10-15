//! Command-line options (`docs/compute_server.md` §2).

use std::net::SocketAddr;
use std::path::PathBuf;

use axum::http::HeaderValue;
use clap::{ArgGroup, Parser};

/// RC-PIR compute server: answers `X q_c` over F_2 (docs/compute_server.md).
#[derive(Debug, Parser)]
#[command(name = "rcpir-server", version)]
#[command(group(ArgGroup::new("transport").required(true).args(["tls_cert", "plain"])))]
pub struct Args {
    /// params.json written by the encoder.
    #[arg(long)]
    pub params: PathBuf,

    /// Packed database X.bin (column-major, t columns of L bytes).
    #[arg(long)]
    pub x: PathBuf,

    /// Address to listen on.
    #[arg(long, default_value = "127.0.0.1:8443")]
    pub listen: SocketAddr,

    /// TLS certificate chain (PEM).
    #[arg(long, requires = "tls_key")]
    pub tls_cert: Option<PathBuf>,

    /// TLS private key (PEM).
    #[arg(long, requires = "tls_cert")]
    pub tls_key: Option<PathBuf>,

    /// Serve without TLS (HTTP/1.1, and HTTP/2 with prior knowledge), for tests or behind a
    /// TLS-terminating proxy.
    #[arg(long)]
    pub plain: bool,

    /// Worker threads per pass (default: all cores).
    #[arg(long, value_parser = clap::value_parser!(u64).range(1..))]
    pub threads: Option<u64>,

    /// Pin worker i to the i-th listed core, e.g. "0,2,4".
    #[arg(long, value_delimiter = ',')]
    pub pin_cores: Option<Vec<usize>>,

    /// Max queries per pass. 1 disables batching.
    #[arg(long, default_value_t = 16, value_parser = clap::value_parser!(u64).range(1..))]
    pub max_batch: u64,

    /// Max time in microseconds the first queued query waits for others.
    /// 0 = start right away with whatever is queued (queries arriving during a pass share the next).
    #[arg(long, default_value_t = 0)]
    pub max_wait: u64,

    /// Max queries waiting for a pass; when full, queries get 503 with Retry-After.
    #[arg(long, default_value_t = 1024, value_parser = clap::value_parser!(u64).range(1..))]
    pub max_queue: u64,

    /// Value of Access-Control-Allow-Origin ("*" or one origin such as https://example.org).
    #[arg(long, default_value = "*")]
    pub cors_origin: HeaderValue,

    /// Skip the SHA-256 check of X.bin against db_digest at startup (large DBs, benchmarks).
    #[arg(long)]
    pub no_verify_digest: bool,

    /// Also append the log to this file (created if missing). The log always goes to stdout.
    #[arg(long)]
    pub log_file: Option<PathBuf>,
}
