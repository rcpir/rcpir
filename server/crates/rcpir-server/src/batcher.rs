//! Pass executor with micro-batching (`docs/compute_server.md` §2).
//!
//! One thread runs all passes over `X`, one at a time (a pass is memory-bandwidth bound, so two
//! concurrent passes would only slow each other down).
//!
//! - Queries are grouped: the first queued query waits at most `max_wait` (from its arrival) for
//!   others, and at most `max_batch` queries share a pass. With `max_wait = 0` (the default) a pass
//!   starts at once with whatever is queued; queries that arrive during a pass share the next one.
//! - The queue holds at most `max_queue` queries; when it is full, a query is rejected at once
//!   ([`QueryError::Busy`], HTTP 503) instead of waiting.
//! - Queries whose client is gone (the handler was dropped, e.g. disconnect or timeout) are skipped
//!   and take no slot in a pass.
//!
//! A panic during a pass (a bug) is caught: it is logged, the queries of that pass get no answer
//! (the handlers return 500), and the executor goes on with the next queries.

use std::any::Any;
use std::panic::{self, AssertUnwindSafe};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, TrySendError};
use std::time::{Duration, Instant};

use bytes::Bytes;
use rcpir_core::Backend;
use tokio::sync::oneshot;

struct Job {
    query: Bytes,
    arrived: Instant,
    reply: oneshot::Sender<Vec<u8>>,
}

/// Why a query got no answer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueryError {
    /// The queue is full (`max_queue`): the client should retry later.
    Busy,
    /// The pass failed (a panic, logged) or the executor has stopped.
    Failed,
}

pub struct Batcher {
    jobs: mpsc::SyncSender<Job>,
    /// Number of passes run so far (for logs and tests).
    pub passes: Arc<AtomicU64>,
}

impl Batcher {
    /// Starts the executor thread for a database with answers of `l` bytes. At most `max_queue`
    /// queries wait for a pass (queries in the running pass not counted).
    pub fn start(
        backend: Arc<dyn Backend>,
        l: usize,
        max_batch: usize,
        max_wait: Duration,
        max_queue: usize,
    ) -> Batcher {
        let (jobs, rx) = mpsc::sync_channel(max_queue);
        let passes = Arc::new(AtomicU64::new(0));
        let executor = Executor {
            backend,
            l,
            max_batch,
            max_wait,
            passes: passes.clone(),
        };
        std::thread::Builder::new()
            .name("rcpir-executor".into())
            .spawn(move || executor.run(rx))
            .expect("cannot start the executor thread");
        Batcher { jobs, passes }
    }

    /// Answers one validated query. Never blocks on a full queue: returns `Busy` at once.
    pub async fn query(&self, query: Bytes) -> Result<Vec<u8>, QueryError> {
        let (reply, answer) = oneshot::channel();
        let job = Job {
            query,
            arrived: Instant::now(),
            reply,
        };
        match self.jobs.try_send(job) {
            Ok(()) => {}
            Err(TrySendError::Full(_)) => return Err(QueryError::Busy),
            Err(TrySendError::Disconnected(_)) => return Err(QueryError::Failed),
        }
        // The sender is dropped without an answer if the pass failed.
        answer.await.map_err(|_| QueryError::Failed)
    }
}

struct Executor {
    backend: Arc<dyn Backend>,
    l: usize,
    max_batch: usize,
    max_wait: Duration,
    passes: Arc<AtomicU64>,
}

impl Executor {
    fn run(self, rx: mpsc::Receiver<Job>) {
        // Ends when the server shuts down (all senders dropped).
        while let Ok(first) = rx.recv() {
            if first.reply.is_closed() {
                continue; // abandoned while queued
            }
            let deadline = first.arrived + self.max_wait;
            let mut group = vec![first];
            while group.len() < self.max_batch {
                let time_left = deadline.saturating_duration_since(Instant::now());
                let next = if time_left.is_zero() {
                    rx.try_recv().ok() // only take what is already queued
                } else {
                    rx.recv_timeout(time_left).ok()
                };
                match next {
                    Some(job) if job.reply.is_closed() => continue, // abandoned: skip
                    Some(job) => group.push(job),
                    None => break,
                }
            }
            let queries: Vec<&[u8]> = group.iter().map(|job| job.query.as_ref()).collect();
            // The backend keeps no state between passes (Backend docs), so it is safe to go on
            // after a panic.
            match panic::catch_unwind(AssertUnwindSafe(|| self.pass(&queries))) {
                Ok(answers) => {
                    for (job, answer) in group.into_iter().zip(answers.chunks(self.l)) {
                        let _ = job.reply.send(answer.to_vec());
                    }
                }
                Err(payload) => {
                    // Location and backtrace were logged by the panic hook (main.rs). Dropping
                    // `group` drops the reply senders, so the handlers answer 500.
                    tracing::error!(
                        k = group.len(),
                        panic = panic_message(payload.as_ref()),
                        "pass failed; its queries are answered with 500, the server continues"
                    );
                }
            }
        }
    }

    /// One pass over `X`; returns the answers concatenated (`queries.len() * L` bytes).
    fn pass(&self, queries: &[&[u8]]) -> Vec<u8> {
        let start = Instant::now();
        let mut answers = vec![0u8; queries.len() * self.l];
        let mut outs: Vec<&mut [u8]> = answers.chunks_mut(self.l).collect();
        self.backend.answer_batch(queries, &mut outs);
        self.passes.fetch_add(1, Ordering::Relaxed);
        tracing::debug!(
            k = queries.len(),
            elapsed_us = start.elapsed().as_micros() as u64,
            "pass"
        );
        answers
    }
}

/// The message of a panic payload (`panic!` with a literal or a formatted string).
fn panic_message(payload: &(dyn Any + Send)) -> &str {
    if let Some(s) = payload.downcast_ref::<&str>() {
        s
    } else if let Some(s) = payload.downcast_ref::<String>() {
        s
    } else {
        "(non-string panic payload)"
    }
}
