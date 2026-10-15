use std::fs::OpenOptions;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use anyhow::Context;
use axum_server::tls_rustls::RustlsConfig;
use bytes::Bytes;
use clap::Parser;
use rcpir_core::{CpuBackend, Params, xdb};
use rcpir_server::{AppState, Args, Batcher, router};
use tracing_subscriber::EnvFilter;
use tracing_subscriber::prelude::*;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    init_logging(args.log_file.as_deref())?;
    // Panics (bugs) go to the log with their thread, location and backtrace. A panic during a pass
    // is caught by the executor and the server continues (batcher.rs).
    std::panic::set_hook(Box::new(|info| {
        let thread = std::thread::current();
        let backtrace = std::backtrace::Backtrace::force_capture();
        tracing::error!(thread = thread.name().unwrap_or("unnamed"), %backtrace, "{info}");
    }));
    // Errors that stop the server (startup checks, listener) are logged too, so they reach the
    // log file.
    if let Err(e) = run(args).await {
        tracing::error!("{e:#}");
        std::process::exit(1);
    }
    Ok(())
}

/// Log to stdout and, with `--log-file`, append to that file as well (without colors). The level
/// comes from `RUST_LOG` (default `info`).
fn init_logging(log_file: Option<&Path>) -> anyhow::Result<()> {
    let file_layer = match log_file {
        Some(path) => {
            let file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .with_context(|| format!("cannot open log file {}", path.display()))?;
            Some(
                tracing_subscriber::fmt::layer()
                    .with_writer(Mutex::new(file))
                    .with_ansi(false),
            )
        }
        None => None,
    };
    tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with(tracing_subscriber::fmt::layer())
        .with(file_layer)
        .init();
    Ok(())
}

async fn run(args: Args) -> anyhow::Result<()> {
    let params_raw = std::fs::read(&args.params).with_context(|| format!("cannot read {}", args.params.display()))?;
    let params = Params::parse(&params_raw).with_context(|| format!("invalid {}", args.params.display()))?;

    let x = xdb::load_x(&args.x, &params, !args.no_verify_digest)?;
    if args.no_verify_digest {
        tracing::warn!("--no-verify-digest: X.bin was NOT checked against db_digest");
    }
    let threads = match args.threads {
        Some(n) => n as usize,
        None => std::thread::available_parallelism()?.get(),
    };
    let backend = CpuBackend::new(x, params.t, params.l, threads, args.pin_cores.clone())?;
    tracing::info!(t = params.t, L = params.l, threads, "database loaded");

    let batcher = Batcher::start(
        Arc::new(backend),
        params.l,
        args.max_batch as usize,
        Duration::from_micros(args.max_wait),
        args.max_queue as usize,
    );
    let state = Arc::new(AppState {
        params,
        params_raw: Bytes::from(params_raw),
        batcher,
    });
    let app = router(state, args.cors_origin.clone()).into_make_service();

    if args.plain {
        tracing::info!("listening on http://{} (HTTP/1.1 and h2c)", args.listen);
        axum_server::bind(args.listen).serve(app).await?;
    } else {
        // Clap guarantees both paths are present without --plain.
        let (cert, key) = (args.tls_cert.unwrap(), args.tls_key.unwrap());
        let tls = RustlsConfig::from_pem_file(&cert, &key)
            .await
            .with_context(|| format!("cannot load TLS certificate {} / key {}", cert.display(), key.display()))?;
        tracing::info!("listening on https://{} (HTTP/2 and HTTP/1.1)", args.listen);
        axum_server::bind_rustls(args.listen, tls).serve(app).await?;
    }
    Ok(())
}
