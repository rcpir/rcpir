# AWS (S3, optionally CloudFront)

Status (2026-10-31): **not yet tested on our own account**. Numbers come from other people's public buckets and
CloudFront sites (`benchmarks/range_bench.mjs`, from Israel, 88 × 4 KiB per lookup). Prices are list prices for
us-east-1; Tel Aviv (`il-central-1`) is somewhat higher.

## What we can and can't do

| | S3 direct (bucket in Tel Aviv) | CloudFront + S3 |
|---|---|---|
| Range requests | Yes | Yes |
| Protocol | **HTTP/1.1 only** (~6 connections per hostname) | HTTP/2 and HTTP/3 |
| CDN cache | No, every range is an S3 read | Yes, Tel Aviv edge; caches only the ranges requested, so random lookups keep missing |
| Operator can see the ranges | **No**: AWS owns the hostname, S3 logs have no range field | **Yes**, if enabled: CloudFront logs have `sc-range-start/end`, and edge code can be added unseen |
| Country block, spending cap | **No**: anyone with the URL can create billed reads | Yes: geo-blocking included, flat-rate plan has no overage |
| All of R as one object | Yes | Yes (cacheable up to 50 GB; Cloudflare: 512 MB) |

## One hostname or many (S3 direct)

A browser opens ~6 HTTP/1.1 connections per hostname, so 88 ranges take ~15 rounds.

AWS gives every bucket several hostnames for the same objects (fixed, not configurable). Verified on a Frankfurt
bucket (same ETag, 206 everywhere):

| Form | Hostname |
|---|---|
| Virtual-hosted (default) | `<bucket>.s3.<region>.amazonaws.com` |
| Virtual-hosted, dual-stack (adds IPv6) | `<bucket>.s3.dualstack.<region>.amazonaws.com` |
| Path-style | `s3.<region>.amazonaws.com/<bucket>` |
| Path-style, dual-stack | `s3.dualstack.<region>.amazonaws.com/<bucket>` |
| Legacy dash (older regions only; probably not Tel Aviv) | `<bucket>.s3-<region>.amazonaws.com`, `s3-<region>.amazonaws.com/<bucket>` |

More hostnames are possible with **copies of R in several buckets** (each bucket has its own virtual-hosted names;
~$0.025 per GB-month per copy). All of these are AWS hostnames, so the setup stays operator-proof.

| Setup | Rounds | Lookup time |
|---|---|---|
| Frankfurt, one hostname (measured) | ~15 | **1.2–1.4 s** |
| Tel Aviv, one hostname | ~15 | **~0.4 s** (estimated) |
| Tel Aviv, one bucket, 4 hostnames | ~4 | **~0.15 s** (estimated; client change, untested) |
| Tel Aviv, 3 buckets, ~8 hostnames | ~2 | ~0.1 s (estimated; extra connection setup limits the gain) |

Estimates: rounds × (round trip + ~15 ms per S3 read). Measured round trip to S3 front end: Tel Aviv **9–11 ms**,
Frankfurt 64–70 ms.

Reference: GitHub Pages 0.10–0.15 s, Cloudflare R2 + CDN 0.15–0.18 s, CloudFront fully cached 0.06–0.19 s.

## Estimated pricing

S3 direct (pay per request, no cap):

| Item | Price | Per lookup (88 GETs, 352 KiB) |
|---|---|---|
| GET requests | ~$0.0004 per 1,000 | $0.000035 |
| Data transfer to internet | ~$0.09 per GB | $0.00003 |
| **Total** | | **~$0.07 per 1,000 lookups** (~$7 per 100k) |
| Storage of R (~1 GB) | ~$0.025 per GB-month | ~$0.03 per month |
| Abuse example | someone downloads all of R 1,000 times | ~$90 |

CloudFront flat-rate **Free plan**: $0, 1M requests + 100 GB per month (~11k lookups), no overage (delivery may be
slowed above it). S3 reads on cache misses are still billed. Probably requires the *Paid* AWS account plan: accounts
on the AWS Free Tier are not eligible.

New AWS accounts get $100–200 of credits (6 months), enough for all tests.

## Next steps

1. Bucket in `il-central-1`, one 64 MiB shard, public read, CORS `GET` with `Content-Range, Content-Length` exposed.
2. Benchmark one hostname, then three hostnames, against the estimates above.
3. Optional: CloudFront in front, to measure the cache-miss penalty with a Tel Aviv origin.
