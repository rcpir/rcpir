# Google Drive

Status (2026-10-31): **works, but too slow**: ~1.6–2.2 s per lookup, about 15–20× GitHub Pages, and the API quota
allows only ~56 lookups per minute per project. Tested on our own copy of R (15 shards in a folder shared as "anyone
with the link"; 20 random columns byte-identical to GitHub Pages).

## Endpoints

| Endpoint | Range (206) | Browser on another site | Verdict |
|---|---|---|---|
| `drive.google.com/uc?export=download&id=<ID>` | Via a 303 redirect without CORS | No | Use the target below |
| `drive.usercontent.google.com/download?id=<ID>&export=download` | Yes | **No**: `403` when the request carries `Sec-Fetch-Site: cross-site`, which browsers always send (`206` with `same-site`, `same-origin`, `none`) | Non-browser clients only |
| **Drive API** `www.googleapis.com/drive/v3/files/<ID>?alt=media&key=<API_KEY>` | Yes | **Yes**: echoes the Origin in `Access-Control-Allow-Origin`, preflight for `Range` allowed. `Content-Range` is not exposed (the client does not need it) | Usable, slow |

Both serve the same files from Google hostnames (operator cannot add a logging layer). No CDN cache.

## Performance (from Israel, 88 × 4 KiB per lookup, `benchmarks/range_bench.mjs`)

| Run | Wall time per lookup |
|---|---|
| Drive API, browser, cross-site page, `cache: no-store` (14 × 64 MiB) | **1.59–1.90 s** |
| Drive API, Node HTTP/2 (14 × 64 MiB) | 1.86–2.07 s |
| `drive.usercontent`, Node HTTP/2 (15 shards) | 2.0–2.6 s |
| Reference: GitHub Pages, Node / browser | 70–98 ms / 106–219 ms |

The time is per request on Google's side, not connection setup or parallelism: one HTTP/2 connection is reused for
all requests (Drive allows 100 concurrent streams), and a single 4 KiB range on a warm connection takes 0.9–1.8 s
(1 range per lookup: 1.51 s, 88 ranges: 2.22 s). Small files are a bit faster (~1 s per range for 256 KiB–10 MB).
This matches the high random-read latency reported for Drive by rclone users
([forum](https://forum.rclone.org/t/google-drive-latency-improvements/24236)).

## Drive API access and quota

- Operator needs a Google Cloud project (free) with the Drive API enabled and an **API key** restricted to the Drive
  API (Credentials → Create credentials → API key; not the "Help me choose" wizard). End users need nothing. The key
  is public by design; misuse can only consume the project's quota. A website (referrer) restriction is weak and
  needs a `referrerPolicy` on the fetches (the site sends `no-referrer`).
- [Limits](https://developers.google.com/workspace/drive/api/guides/limits): `files.get` with `alt=media` costs
  **200 units**, i.e. 17,600 per lookup. Per project 1,000,000 units/min (**~56 lookups/min**, all visitors
  together), per user 325,000 units/min, 400M units/day before billing (billing beyond quota planned for 2026).
  Exceeding: `403 User rate limit exceeded` / `429`.
- OAuth does not lift the per-project limit, needs the restricted scope `drive.readonly` (Google verification and
  security assessment), and ties every range request to the visitor's Google identity.

## Logs (privacy)

- Cloud project of the API key: aggregate API metrics only; Drive is not among the Workspace audit logs forwarded to
  Cloud Logging ([docs](https://docs.cloud.google.com/logging/docs/audit/gsuite-audit-logging)).
- Workspace accounts only: the admin's Drive audit log records each download with **document ID** (= shard), time
  and actor; users outside the domain appear as anonymous, without IP; no range field
  ([Drive log events](https://knowledge.workspace.google.com/admin/reports/drive-log-events)). With per-shard files
  this reveals the shard of each column. A personal account has no such log.

## Possible mitigation (not implemented)

$S$ and $He$ do not depend on the article, so the client could fetch the $s$ columns before the user picks an
article and send only the compute query at click time. This hides retrieval latency for any host, but not the quota.
