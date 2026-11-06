# Dropbox

Status (2026-11-06): **works from a browser**. Dropbox rejects request bursts with `429`, counted **per file**, so one
copy of R needs ~2.8–3.2 s per lookup and **two copies ~1.5 s**. With `prepare()` the wait happens before the click
(click-to-block ~60 ms; in the demo ~0.25 s including the compute server). Tested on our own copy of R:
all of R as one 950 MB file (`rcpir_c4_L4k_R.bin`, size = $m L$), shared link "anyone with the link"; 12 random
columns byte-identical to GitHub Pages; real lookups via `rcpir-get --dropbox-link` identical to GitHub Pages.

## Endpoints

| Endpoint | Range (206) | Browser on another site | Verdict |
|---|---|---|---|
| Shared link `https://www.dropbox.com/scl/fi/<id>/<name>?rlkey=<key>&dl=1` (or `raw=1`) | Via 2 redirects to a temporary `uc<hash>.dl.dropboxusercontent.com/cd/0/…` URL | **No**: the first redirect has no CORS headers | Entry point only |
| **`https://dl.dropboxusercontent.com/scl/fi/<id>/<name>?rlkey=<key>`** | **Yes, no redirect** | **Yes**: `Access-Control-Allow-Origin: *`, `Content-Range` exposed, works with `Sec-Fetch-Site: cross-site` | **Used** (`Dropbox` provider) |

`dl=0/1` makes no difference on the direct host. HTTP/2, no CDN cache. The hostname is Dropbox's, so the operator
cannot add a logging layer. Multi-range requests not tested.

## Rate limit

Dropbox answers `429` (HTML, without CORS headers, so browsers report a network error) when requests to **one file**
come faster than roughly **40 per second, with bursts of ~50** (not documented, measured):

| Requests | Result |
|---|---|
| 88 at once (one HTTP/2 connection) | ~50 × 206, ~38 × 429, every lookup |
| 48 per lookup, lookups back to back (~35/s) | all 206 |
| At most 32 in flight, next request as soon as one finishes (~45/s) | 429 (browser and Node) |
| **At most 24 in flight (~30/s)** | **all 206** (5/5 lookups in Chromium) |
| 88 at once, **split over two copies** (two links, ~44 each) | **all 206** (3/3 lookups, 0.94–1.17 s) |

The limit is per file (or link), not per IP: copies add throughput. `Dropbox` takes one or more links to identical
copies, reads column $j$ from copy $j \bmod n$ (independent of the block, like $S$) and allows 24 requests in flight
per copy. Single requests stayed fine throughout; no longer-lasting block was seen.

## Performance (from Israel, 88 × 4 KiB per lookup)

| Run | Wall time |
|---|---|
| Single 4 KiB range, warm connection | 0.50–0.81 s |
| **`prepare()`, real client, Chromium, `maxParallel` 24** | **2.83–3.17 s** |
| `prepare()`, real client, Chromium, `maxParallel` 16 / 8 | 3.8–4.6 s / 7.4–7.7 s |
| `prepare()`, Node client (HTTP/1.1), `maxParallel` 24 | 3.1 s; click-to-block after it: 59 ms |
| Demo (wip/), **two copies**, click before the lookup is prepared / after | **1.5–2.3 s** / 0.24–0.26 s |
| Reference: GitHub Pages / Google Drive API (one file) | ~0.1 s / ~0.7 s |
