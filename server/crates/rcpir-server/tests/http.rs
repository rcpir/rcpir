//! HTTP handler tests: answers, error codes, CORS, micro-batching, panics, full queue, abandoned
//! queries.

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use axum::Router;
use axum::body::Body;
use axum::http::{HeaderValue, Method, Request, Response, StatusCode};
use bytes::Bytes;
use http_body_util::BodyExt;
use rand::SeedableRng;
use rand::rngs::StdRng;
use rcpir_core::fixture::{naive_answer, params_json, random_query, random_x, unit_query};
use rcpir_core::xdb::sha256_digest;
use rcpir_core::{Backend, CpuBackend, Params};
use rcpir_server::{AppState, Batcher, router};
use tower::ServiceExt;

const T: usize = 13; // t mod 8 != 0, so queries have 3 unused trailing bits
const L: usize = 72;
const QLEN: usize = 2;
/// The all-ones query in F_2^13 (3 unused trailing bits zero); `PanickyBackend` panics on it.
const ALL_ONES: [u8; QLEN] = [0xFF, 0xF8];

struct Server {
    app: Router,
    x: Vec<u8>,
    state: Arc<AppState>,
    /// Number of queries the backend has answered.
    answered: Arc<AtomicUsize>,
}

/// Counts the queries answered by the wrapped backend.
struct Counted(Arc<dyn Backend>, Arc<AtomicUsize>);

impl Backend for Counted {
    fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]) {
        self.0.answer_batch(queries, out);
        self.1.fetch_add(queries.len(), Ordering::Relaxed);
    }
}

/// A stand-in for a backend bug: panics on the all-ones query, answers the others normally.
struct PanickyBackend(CpuBackend);

impl Backend for PanickyBackend {
    fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]) {
        assert!(!queries.contains(&ALL_ONES.as_slice()), "injected backend bug");
        self.0.answer_batch(queries, out);
    }
}

/// Every pass takes `SLOW_PASS`, so the executor stays busy while a test queues queries.
struct SlowBackend(CpuBackend);

const SLOW_PASS: Duration = Duration::from_millis(300);

impl Backend for SlowBackend {
    fn answer_batch(&self, queries: &[&[u8]], out: &mut [&mut [u8]]) {
        std::thread::sleep(SLOW_PASS);
        self.0.answer_batch(queries, out);
    }
}

#[derive(Clone, Copy)]
enum Kind {
    Normal,
    Panicky,
    Slow,
}

fn server(max_batch: usize, max_wait: Duration, cors_origin: &str) -> Server {
    build_server(max_batch, max_wait, 1024, cors_origin, Kind::Normal)
}

fn build_server(max_batch: usize, max_wait: Duration, max_queue: usize, cors_origin: &str, kind: Kind) -> Server {
    let x = random_x(T, L, &mut StdRng::seed_from_u64(11));
    let params_raw = params_json(T, L, &sha256_digest(&x));
    let params = Params::parse(params_raw.as_bytes()).unwrap();
    let cpu = CpuBackend::new(x.clone(), T, L, 2, None).unwrap();
    let backend: Arc<dyn Backend> = match kind {
        Kind::Normal => Arc::new(cpu),
        Kind::Panicky => Arc::new(PanickyBackend(cpu)),
        Kind::Slow => Arc::new(SlowBackend(cpu)),
    };
    let answered = Arc::new(AtomicUsize::new(0));
    let backend = Arc::new(Counted(backend, answered.clone()));
    let batcher = Batcher::start(backend, L, max_batch, max_wait, max_queue);
    let state = Arc::new(AppState {
        params,
        params_raw: Bytes::from(params_raw),
        batcher,
    });
    let app = router(state.clone(), HeaderValue::from_str(cors_origin).unwrap());
    Server {
        app,
        x,
        state,
        answered,
    }
}

fn default_server() -> Server {
    server(16, Duration::ZERO, "*")
}

async fn send(app: &Router, method: Method, path: &str, body: Vec<u8>) -> Response<Body> {
    let req = Request::builder()
        .method(method)
        .uri(path)
        .body(Body::from(body))
        .unwrap();
    app.clone().oneshot(req).await.unwrap()
}

async fn post(app: &Router, path: &str, body: Vec<u8>) -> Response<Body> {
    send(app, Method::POST, path, body).await
}

async fn body_of(r: Response<Body>) -> Vec<u8> {
    r.into_body().collect().await.unwrap().to_bytes().to_vec()
}

fn assert_cors(r: &Response<Body>) {
    assert_eq!(r.headers()["access-control-allow-origin"], "*");
    let exposed = r.headers()["access-control-expose-headers"].to_str().unwrap();
    assert!(
        exposed.contains("rc-pir-db-digest") && exposed.contains("retry-after"),
        "{exposed}"
    );
}

#[tokio::test]
async fn single_query() {
    let s = default_server();
    let mut rng = StdRng::seed_from_u64(1);
    for _ in 0..5 {
        let q = random_query(T, &mut rng);
        let r = post(&s.app, "/rc-pir/query", q.clone()).await;
        assert_eq!(r.status(), StatusCode::OK);
        assert_cors(&r);
        assert_eq!(r.headers()["content-type"], "application/octet-stream");
        assert_eq!(r.headers()["rc-pir-db-digest"], s.state.params.db_digest.as_str());
        assert_eq!(body_of(r).await, naive_answer(&s.x, T, L, &q));
    }
    // e_12 (the last valid bit) returns column 12.
    let r = post(&s.app, "/rc-pir/query", unit_query(T, 12)).await;
    assert_eq!(body_of(r).await, &s.x[12 * L..]);
}

#[tokio::test]
async fn single_query_errors() {
    let s = default_server();
    for len in [0, 1] {
        let r = post(&s.app, "/rc-pir/query", vec![0; len]).await;
        assert_eq!(r.status(), StatusCode::BAD_REQUEST, "length {len}");
        assert_cors(&r);
    }
    // Longer than one query: rejected by the body limit.
    for len in [QLEN + 1, 1 << 20] {
        let r = post(&s.app, "/rc-pir/query", vec![0; len]).await;
        assert_eq!(r.status(), StatusCode::PAYLOAD_TOO_LARGE, "length {len}");
        assert_cors(&r);
    }
    // Bit 13 is an unused trailing bit.
    let r = post(&s.app, "/rc-pir/query", vec![0x00, 0x04]).await;
    assert_eq!(r.status(), StatusCode::BAD_REQUEST);
    let r = send(&s.app, Method::GET, "/rc-pir/query", vec![]).await;
    assert_eq!(r.status(), StatusCode::METHOD_NOT_ALLOWED);
    assert_cors(&r);
}

#[tokio::test]
async fn preflight_with_specific_origin() {
    let s = server(1, Duration::ZERO, "https://client.example");
    let req = Request::builder()
        .method(Method::OPTIONS)
        .uri("/rc-pir/query")
        .header("origin", "https://client.example")
        .header("access-control-request-method", "POST")
        .header("access-control-request-headers", "content-type")
        .body(Body::empty())
        .unwrap();
    let r = s.app.clone().oneshot(req).await.unwrap();
    assert!(r.status().is_success());
    let h = r.headers();
    assert_eq!(h["access-control-allow-origin"], "https://client.example");
    assert!(h["access-control-allow-methods"].to_str().unwrap().contains("POST"));
    assert_eq!(h["access-control-allow-headers"], "content-type");
    assert_eq!(h["access-control-max-age"], "86400");
}

/// With a long max_wait, concurrent single queries share passes; with max_batch = 1 they don't.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn micro_batching() {
    for max_batch in [16, 1] {
        let s = server(max_batch, Duration::from_millis(200), "*");
        let mut rng = StdRng::seed_from_u64(3);
        let queries: Vec<Vec<u8>> = (0..8).map(|_| random_query(T, &mut rng)).collect();
        let tasks: Vec<_> = queries
            .iter()
            .map(|q| {
                let (app, q) = (s.app.clone(), q.clone());
                tokio::spawn(async move { body_of(post(&app, "/rc-pir/query", q).await).await })
            })
            .collect();
        for (task, q) in tasks.into_iter().zip(&queries) {
            assert_eq!(task.await.unwrap(), naive_answer(&s.x, T, L, q));
        }
        let passes = s.state.batcher.passes.load(Ordering::Relaxed);
        if max_batch == 1 {
            assert_eq!(passes, 8);
        } else {
            assert!(passes < 8, "expected shared passes, got {passes}");
        }
    }
}

/// max_wait = 0 must not delay a lone query.
#[tokio::test]
async fn zero_wait_is_immediate() {
    let s = default_server();
    let start = Instant::now();
    let r = post(&s.app, "/rc-pir/query", unit_query(T, 0)).await;
    assert_eq!(r.status(), StatusCode::OK);
    assert!(start.elapsed() < Duration::from_millis(100));
}

/// A panic during a pass gives 500 for that query, and the server keeps answering (batcher.rs).
#[tokio::test]
async fn panic_in_pass_is_survived() {
    let s = build_server(1, Duration::ZERO, 1024, "*", Kind::Panicky);
    let mut rng = StdRng::seed_from_u64(4);
    for _ in 0..2 {
        let r = post(&s.app, "/rc-pir/query", ALL_ONES.to_vec()).await;
        assert_eq!(r.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_cors(&r);
        let q = random_query(T, &mut rng);
        let r = post(&s.app, "/rc-pir/query", q.clone()).await;
        assert_eq!(r.status(), StatusCode::OK);
        assert_eq!(body_of(r).await, naive_answer(&s.x, T, L, &q));
    }
}

/// A full queue answers 503 with Retry-After at once; the queued queries are still answered.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn full_queue_is_rejected() {
    let s = build_server(1, Duration::ZERO, 2, "*", Kind::Slow);
    let mut rng = StdRng::seed_from_u64(5);
    let queries: Vec<Vec<u8>> = (0..3).map(|_| random_query(T, &mut rng)).collect();
    // The first query occupies the executor; the next two fill the queue (max_queue = 2).
    let mut tasks = Vec::new();
    for q in &queries {
        let (app, q) = (s.app.clone(), q.clone());
        tasks.push(tokio::spawn(async move { post(&app, "/rc-pir/query", q).await }));
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    let start = Instant::now();
    let r = post(&s.app, "/rc-pir/query", unit_query(T, 0)).await;
    assert_eq!(r.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert!(start.elapsed() < SLOW_PASS / 2, "a full queue must not block");
    assert_eq!(r.headers()["retry-after"], "1");
    assert_cors(&r);
    for (task, q) in tasks.into_iter().zip(&queries) {
        let r = task.await.unwrap();
        assert_eq!(r.status(), StatusCode::OK);
        assert_eq!(body_of(r).await, naive_answer(&s.x, T, L, q));
    }
}

/// A query whose client is gone while it is queued is not computed. With `max_batch = 1` it is
/// the first query of a group; with `max_batch = 16` it is collected into C's group.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn abandoned_query_is_skipped() {
    for max_batch in [1, 16] {
        let s = build_server(max_batch, Duration::ZERO, 1024, "*", Kind::Slow);
        let mut rng = StdRng::seed_from_u64(6);
        let (qa, qb, qc) = (
            random_query(T, &mut rng),
            random_query(T, &mut rng),
            random_query(T, &mut rng),
        );
        let spawn_post = |q: Vec<u8>| {
            let app = s.app.clone();
            tokio::spawn(async move { post(&app, "/rc-pir/query", q).await })
        };
        let a = spawn_post(qa.clone());
        tokio::time::sleep(Duration::from_millis(50)).await; // A is in its pass
        let c = spawn_post(qc.clone()); // C is queued
        tokio::time::sleep(Duration::from_millis(20)).await;
        // B gives up while queued behind C: its handler is dropped.
        let b = tokio::time::timeout(Duration::from_millis(50), post(&s.app, "/rc-pir/query", qb)).await;
        assert!(b.is_err());
        assert_eq!(body_of(c.await.unwrap()).await, naive_answer(&s.x, T, L, &qc));
        assert_eq!(body_of(a.await.unwrap()).await, naive_answer(&s.x, T, L, &qa));
        // The queue is FIFO: once D is answered, B has been either skipped or computed.
        let d = post(&s.app, "/rc-pir/query", unit_query(T, 0)).await;
        assert_eq!(body_of(d).await, &s.x[..L]);
        let answered = s.answered.load(Ordering::Relaxed);
        assert_eq!(
            answered, 3,
            "max_batch = {max_batch}: B must not be computed (A, C, D only)"
        );
    }
}
