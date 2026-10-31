# OneDrive / SharePoint (Microsoft 365, TAU account)

Status (2026-10-31): **works from a browser, ~0.7–1.0 s per lookup, but the documented anonymous-link limit allows
only ~34 lookups per 5 minutes per OneDrive**. Tested on our own copy
of R: 15 shards in a folder shared as "Anyone with the link", and **all of R as one 950 MB file with its own Anyone link**
(SHA-256 = `r_digest`; 20 random columns of each, incl. the first and last, byte-identical to GitHub Pages).

## Endpoints

| Endpoint | Range (206) | Browser on another site | Verdict |
|---|---|---|---|
| Share link `…/:f:/g/personal/<user>/<token>` (folder) or `…/:u:/g/…` (file) | Via a redirect that sets a guest `FedAuth` cookie | No | Entry point only |
| File path `/personal/<user>/Documents/<folder>/<file>` | Yes, **with the cookie** | **No**: no CORS headers; the cookie is third-party | Slow anyway (5.4–6.4 s per lookup) |
| `/personal/<user>/_layouts/15/download.aspx?UniqueId=<file id>` | Yes, **with the cookie** (`403` without) | **No**: `Access-Control-Allow-Origin: *` but needs the cookie, and `*` is not allowed for credentialed requests | Non-browser clients only |
| **`/personal/<user>/_layouts/15/download.aspx?share=<token of a per-file Anyone link>`** | **Yes, no cookie** | **Yes**: `Access-Control-Allow-Origin: *`, works with `Sec-Fetch-Site: cross-site`. `Content-Range` is not exposed (the client does not need it) | **Usable** |
| Same with a folder token, or without `/personal/<user>` | No: `200` with an HTML error page | — | — |
| v2.0/v2.1 API (`@content.downloadUrl`), Microsoft Graph | — | — | Not for guests: `403 accessDenied`, "OAuth only flow is enabled", Graph `401` |

So every shard (or all of R as one file) needs its own **Anyone link**, created in the OneDrive UI (Share → Anyone
with the link → Copy). A folder link is not enough for browsers. All hostnames are Microsoft's
(`<tenant>-my.sharepoint.com`), so the operator cannot add a logging layer. No CDN cache (`CONFIG_NOCACHE`).

## Performance (from Israel, 88 × 4 KiB per lookup, `benchmarks/range_bench.mjs`)

| Run | Wall time per lookup |
|---|---|
| **All of R as one file (950 MB)**, Anyone link, **browser**, cross-site page, `cache: no-store` | **0.67–1.04 s** |
| Same, Node HTTP/2 | 0.51–1.06 s |
| Same, browser, `cache: default` (the client's current mode) | **20.5 s** (Chromium queues concurrent ranges to one URL) |
| One 64 MiB shard, Anyone link, browser, cross-site page, `cache: no-store` / Node HTTP/2 | 0.59–0.86 s / 0.63–1.54 s |
| `download.aspx?UniqueId` + guest cookie, Node HTTP/2 (15 shards) | 0.30–1.11 s |
| File path + guest cookie, Node HTTP/2 (15 shards) | 5.4–6.4 s |
| Reference: GitHub Pages, Node / browser | 70–98 ms / 106–219 ms |

One HTTP/2 connection carries all requests. A single 4 KiB range via `download.aspx` takes 136–196 ms, so 88 concurrent
ranges queue on Microsoft's side. File size does not matter (64 MiB and 950 MB perform alike). Responses list
`RateLimit-*` in `Access-Control-Expose-Headers` but do not send them, so the remaining budget is not visible.

## Limits

[SharePoint throttling](https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online)
(defaults, "Microsoft may change these limits at any time"):

- **Per site (a personal OneDrive is one site): 3,000 anonymous-link requests per 5 min** and 100 GB anonymous egress
  per 2 h. If every range counts, that is **~34 lookups per 5 min for all visitors together** (not verified: we did not
  load-test, which Microsoft forbids, on a university account). Exceeding: `429`/`503` with `Retry-After`; persistent
  excess can get the app or user blocked.
- The same page says unsupported use "may result in throttling", with the example "using SharePoint and OneDrive as
  an intermediary service between Microsoft 365 and another repository". Serving public files via Anyone links is not
  named there; Microsoft's terms of use were not checked.
- Tenant policies (TAU IT) decide whether Anyone links are allowed and may make them expire.

## Logs (privacy)

- Tenant admins (TAU IT, Microsoft Purview audit) get an **`AnonymousLinkUsed`** event when an Anyone link is used,
  with the resource URL as `ObjectId`
  ([sharing auditing](https://learn.microsoft.com/en-us/purview/audit-log-sharing)). No range field. With one file per
  shard this reveals the shard of each column to the tenant admins; with all of R as **one file** it reveals nothing
  beyond the time. The file owner (us) has no per-request log.
- Not checked: whether every range request produces an event, and which client fields (IP, user agent) anonymous
  events carry.

## Next steps (if pursued)

1. Client: `cache: "no-store"` on column fetches (needed for every single-object host), and per-host URLs instead of
   `/rc-pir/r/<shard>` paths.
2. Single-file layout: `params.json` needs `columns_per_shard` = m (231,932), which changes the pinned params hash.
3. Same mitigation as Google Drive: fetch the $s$ columns before the user picks an article (hides latency, not quota).
