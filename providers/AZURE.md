# Azure (Blob Storage, optionally Front Door)

Status (2026-10-31): **not yet tested on our own account.** Numbers come from other people's public resources
(`benchmarks/range_bench.mjs`, from Israel, 88 ranges per lookup, browser, `cache: no-store`).

## Summary

| | Blob Storage direct | Front Door + Blob |
|---|---|---|
| Range requests | Yes | Yes |
| Protocol | **HTTP/1.1 only** (~6 connections per hostname) | HTTP/2 |
| Measured lookup | **1.25–1.91 s** (West Europe) | **121–135 ms** (edge near Israel) |
| Operator can see the ranges | **No**: Microsoft's hostname, no range in Blob logs | **Yes**, without code (see below) |
| Cost | Pay per read; no spending cap | **$35/month** base + traffic |

Not usable: Azure Files (needs auth and `x-ms-version`, tested), Static Web Apps Free (250 MB limit), classic
CDN / classic Front Door (no new profiles).

## Blob Storage direct

- Anonymous read on the container; CORS `*` gives `Access-Control-Allow-Origin: *` with no `Vary: Origin`.
- A range costs about one round trip, but 88 ranges take ~15 rounds over 6 connections. In Israel Central
  (~10 ms round trip, unmeasured) that is an estimated **~0.3 s** per lookup.
- More hostnames would cut the rounds (as with S3), but options are limited: route-specific endpoints are not
  available in Israel Central or Austria East, and the static website endpoint has no CORS (usable only if the
  demo site is served from it). Copies of R in extra storage accounts add hostnames.

## Front Door: ranges can be logged

- WAF custom rule on the `Range` header with action *Log*: the WAF log records the header value (also for cache
  hits).
- Rules Engine variable `{http_req_header_Range}` copied into the origin URL or `x-ms-client-request-id`: logged
  on cache misses (Front Door `OriginURL`, Blob `ClientRequestId`).

Like CloudFront and Cloudflare, privacy behind the CDN rests on trusting the operator.

## Worth an account?

Front Door: no, no advantage over Cloudflare or CloudFront. Blob direct in Israel Central: yes, a cheap test of the
only operator-proof Azure option. One 64 MiB shard, anonymous read, CORS `*` exposing `Content-Range,
Content-Length`; measure with `range_bench.mjs` (browser and node).

## Sources

[HTTP versions](https://learn.microsoft.com/rest/api/storageservices/http-version-support) ·
[StorageBlobLogs](https://learn.microsoft.com/azure/azure-monitor/reference/tables/storagebloblogs) ·
[Routing preference](https://learn.microsoft.com/azure/storage/common/network-routing-preference) ·
[Static website](https://learn.microsoft.com/azure/storage/blobs/storage-blob-static-website) ·
[Front Door logs](https://learn.microsoft.com/azure/frontdoor/front-door-diagnostics) ·
[WAF logs](https://learn.microsoft.com/azure/web-application-firewall/afds/waf-front-door-monitor) ·
[Server variables](https://learn.microsoft.com/azure/frontdoor/rule-set-server-variables)
