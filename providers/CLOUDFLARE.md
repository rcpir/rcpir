# Cloudflare (R2 + CDN)

Status (2026-10-30): **usable** as retrieval host with R2 behind a custom domain and the CDN cache. Hostname,
client IP and Ray IDs are censored below (`<host>`, `<ip>`, `<ray>`).

## Products

| Product | Range (206) | Verdict |
|---|---|---|
| Workers static assets / Pages | No: always `200` with the whole file | Unusable |
| R2 via `r2.dev` | Yes | Dev only: rate-limited, no WAF, no cache. Disable it |
| R2 via custom domain, no cache | Yes, any offset (tested 100 GB deep) | Slow: ~0.2–0.7 s per range, 90 concurrent ranges 1.6–2.1 s (other people's public buckets) |
| R2 S3 endpoint (`*.r2.cloudflarestorage.com`, presigned URLs) | Yes | Too slow: 3.3–4.1 s per lookup (see below) |
| **R2 via custom domain + CDN cache** | Yes | **Used**. Results below |

## Setup

- Domain must be a zone in the same account (Free plan is fine). Bucket location hint: EEUR.
- `r2.dev` URL disabled.
- WAF custom rule (Block): `(http.host eq "<host>" and ip.src.country ne "IL")`. Verified: `403` from France,
  Slovenia, Ukraine and the US (check-host.net probes).
- Recommended, not yet active at the time of testing: block paths outside `/rc-pir/r/`, methods other than
  GET/HEAD/OPTIONS, and any query string (R2 bills 404 reads; each new query string was a cache MISS = billed read).
- Cache rule: eligible for cache, Edge TTL override, cache key ignores the query string.
- CORS: **do not use the R2 CORS policy**. It adds `Vary: Origin` and the CDN then keeps a separate cached copy
  per Origin value (verified: new Origin → MISS, same Origin → HIT). Set `Access-Control-Allow-Origin: *` and
  `Access-Control-Expose-Headers: Content-Range, Content-Length` with a Transform Rule instead. A single `Range`
  header needs no preflight.
- Origin Range Requests: leave **off**. With it the edge fetches 1 MiB chunks instead of the whole object, so the
  1-byte warm-up no longer fills the cache, and R2 learns which 1 MiB region a lookup needs.

## Limits and billing

- Max cached file: **512 MB** on Free, Pro and Business; 5 GB on Enterprise (more on request).
- Cache Reserve does not help: not used for R2 public buckets on the zone, no origin range requests.
- R2 free tier: 10 GB storage, 1M Class A, 10M Class B per month. **No spending cap.** Cache hits do not reach R2.

## Performance (from Israel, 15 shards of 64 MiB, 88 × 4 KiB per lookup, `benchmarks/range_bench.mjs`)

Requests are served from Frankfurt (`colo=FRA`), not Tel Aviv.

| Run | Wall time per lookup |
|---|---|
| Cold edge, no warm-up | 3.6 s, then 252 ms, 181 ms |
| Warm, browser, cross-site page, `cache: no-store` | **153–180 ms** |
| Warm, Node HTTP/2 | 126–150 ms |
| Warm, browser, `cache: default` (current client) | 673–788 ms (Chromium queues ranges per URL) |
| Reference: GitHub Pages (Fastly, Marseille) | 101–151 ms |

## Logs (privacy)

The zone's request logs (Observability) record **path, time and client IP, but not the range**:

```json
{ "securityAction": "unknown", "rayName": "<ray>", "originResponseStatus": 0, "edgeResponseStatus": 206,
  "datetime": "2026-10-30T09:06:50Z", "clientRequestPath": "/rc-pir/r/0000000c", "clientRequestHTTPMethodName": "GET",
  "clientRequestHTTPHost": "<host>:443", "clientIP": "<ip>", "clientCountryName": "IL", "cacheStatus": "hit" }
```

R2 Data Access Logs (opt-in, 7 days) have no range field either. Cloudflare itself sees the ranges. The zone owner
can still log them without code: Logpush custom fields (listed for all plans) cannot log the `Range` request header
but can log the `Content-Range` response header, so the options below only hide shard counts from the default logs.

With several shards, the account owner therefore learns how many elements of $S$ fall into each shard. Options:

| Option | Requests per lookup | Notes |
|---|---|---|
| A. Fixed number of noise positions per shard | 88 | Changes the noise distribution (−35 bits of entropy); needs a new security analysis |
| B. Pad every shard to $K$ requests (redraw $S$ if a shard exceeds $K$) | 230 at $K=16$ | Uniform noise conditioned on an event of probability 99.8%: loss ≤ 0.003 bits |
| C. One object ≤ 512 MB (constant path) | 176 ($c=2$, $R$ = 475 MB) | Unchanged noise; 2× requests |

## Verifiability

A client cannot prove that `<host>` is served by R2 without operator code in front of it. The zone owner can attach
a Worker, Snippet, Transform Rule or logging to the hostname at any time without changing anything public: DNS stays
the same (proxied Cloudflare IPs, no visible R2 record), and so does the certificate (a per-hostname
Cloudflare-managed certificate, the same kind Workers and Pages custom domains get). Such code would see every range,
and could serve the same bytes, ETag, headers and R2-style 404 pages from the bucket. Timing does not help: a cache
hit costs ~8 ms more than an edge-only response (median 66 vs 57 ms), well within the ±20 ms jitter, and a Worker
runs before the cache and adds about 1 ms. Every response from `<host>` matched a plain R2 bucket behind the cache,
but that describes only the current configuration. Only a hostname the operator does not control (`*.github.io`,
`*.r2.dev`, `*.r2.cloudflarestorage.com`) moves this trust from the operator to the provider.

## Why not the S3 endpoint (`<account>.r2.cloudflarestorage.com`)

It is operator-proof (only Cloudflare controls it) and supports Range, but:

- **HTTP/1.1 only**: the server negotiates `http/1.1` and refuses an `h2`-only TLS offer; no HTTP/3. A browser uses
  ~6 connections per host, so 88 ranges take ~15 sequential rounds.
- **No CDN cache** (no `cf-cache-status`): every range is an R2 read, ~180–250 ms each and billed as Class B.
  R2's internal read cache did not make repeated ranges faster.
- Measured in Chromium (presigned URL of another R2 account, 88 × 4 KiB, `no-store`): **3.3–4.1 s per lookup**,
  requests finishing ~6 at a time; Node with 6 HTTP/1.1 connections: 3.2–3.3 s. About 20× slower than the custom
  domain with CDN.
- No WAF or country block, so anyone with the URL can generate billed reads.
- Presigned URLs expire after at most 7 days and must be re-signed regularly.
