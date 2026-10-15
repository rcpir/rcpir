//! HTTP routes (`docs/protocol.md` §3, §5; `docs/params_format.md` §6).

use std::sync::Arc;
use std::time::Duration;

use axum::Router;
use axum::extract::{DefaultBodyLimit, State};
use axum::http::{HeaderName, HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use bytes::Bytes;
use rcpir_core::Params;
use rcpir_core::bits::is_well_formed;
use tower_http::cors::{AllowOrigin, CorsLayer};

use crate::batcher::{Batcher, QueryError};

pub struct AppState {
    pub params: Params,
    /// `params.json` exactly as read from disk (served byte-identical).
    pub params_raw: Bytes,
    pub batcher: Batcher,
}

/// `cors_origin` is the value of `Access-Control-Allow-Origin` (`*` or one origin).
pub fn router(state: Arc<AppState>, cors_origin: HeaderValue) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(if cors_origin == "*" {
            AllowOrigin::any()
        } else {
            AllowOrigin::exact(cors_origin)
        })
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([header::CONTENT_TYPE])
        .expose_headers([HeaderName::from_static("rc-pir-db-digest"), header::RETRY_AFTER])
        .max_age(Duration::from_secs(86400));
    // A body longer than one query gets 413 from the body limit, without being buffered.
    let body_limit = state.params.query_len();
    Router::new()
        .route("/rc-pir/query", post(query))
        .route("/.well-known/rc-pir.json", get(well_known))
        .layer(DefaultBodyLimit::max(body_limit))
        .layer(cors)
        .with_state(state)
}

fn error(status: StatusCode, message: String) -> Response {
    (status, message + "\n").into_response()
}

/// `Retry-After` (seconds) of a 503 when the queue is full.
const RETRY_AFTER_SECS: &str = "1";

fn answer(st: &AppState, result: Result<Vec<u8>, QueryError>) -> Response {
    match result {
        Ok(body) => (
            [
                (header::CONTENT_TYPE, "application/octet-stream"),
                (
                    HeaderName::from_static("rc-pir-db-digest"),
                    st.params.db_digest.as_str(),
                ),
            ],
            body,
        )
            .into_response(),
        Err(QueryError::Busy) => {
            let mut r = error(StatusCode::SERVICE_UNAVAILABLE, "server busy, retry later".into());
            r.headers_mut()
                .insert(header::RETRY_AFTER, HeaderValue::from_static(RETRY_AFTER_SECS));
            r
        }
        Err(QueryError::Failed) => error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "internal error (see the server log)".into(),
        ),
    }
}

async fn query(State(st): State<Arc<AppState>>, body: Bytes) -> Response {
    let query_len = st.params.query_len();
    if body.len() != query_len {
        let msg = format!("query must be ceil(t/8) = {query_len} bytes, got {}", body.len());
        return error(StatusCode::BAD_REQUEST, msg);
    }
    if !is_well_formed(&body, st.params.t) {
        return error(StatusCode::BAD_REQUEST, "unused trailing bits must be zero".into());
    }
    answer(&st, st.batcher.query(body).await)
}

async fn well_known(State(st): State<Arc<AppState>>) -> Response {
    ([(header::CONTENT_TYPE, "application/json")], st.params_raw.clone()).into_response()
}
