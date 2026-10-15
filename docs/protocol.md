# Wire Protocol (HTTP)

Status: agreed spec. $R$ in shards fetched by byte range, HTTP/2 over TLS, compute server is a web server,
MSB-first bit order, big-endian integers, one database per origin.

Notation: `docs/lpn_parameters.md`; formats: `docs/db_format.md`, `docs/params_format.md`.

## 1. Deployment model

- One database per origin (scheme + host + port). Both servers publish the same
  `/.well-known/rc-pir.json` (`params_format.md` §6).
- The client is configured with two origins: the retrieval origin and the compute origin.
- The client uses HTTP/2 (one connection per origin, requests multiplexed).

## 2. Retrieval server: shards of $R$, one byte range per column

The encoder writes $R=XH$ column by column (column $j\in\{0,\dots,m-1\}$ is $L$ bytes, MSB-first packing
of the $\ell$ bits) into **shards**: shard $k$ holds columns $kC,\dots,\min(m,(k+1)C)-1$ back to back,
where $C$ = `columns_per_shard` from `params.json`. All shards have $CL$ bytes except possibly the last.
No column spans two shards. The concatenation of the shards is all of $R$ in column order.
The retrieval server is any static file host that supports single byte-range requests.

$C$ is chosen by the encoder: the largest number of whole columns that fits a size bound $B$
(`--shard-mib`, default 64 MiB), i.e. $C=\min(\lfloor B/L\rfloor, m)$, so every shard is at most $B$ bytes.

Path of shard $k$ ($k$ as 8 lowercase hex digits) and location of column $j$:

```
/rc-pir/r/<k>       k = floor(j / C),   offset = (j mod C) * L,   length L
e.g. C = 16384, L = 4096, j = 16383 -> /rc-pir/r/00000000, bytes 67104768-67108863
```

Request/response:

- Client: `GET /rc-pir/r/<k>` with `Range: bytes=<offset>-<offset+L-1>` for each $j\in S$, all $s$
  requests issued concurrently.
- Server: `206 Partial Content`, `Content-Type: application/octet-stream`, body of exactly $L$ bytes.
- Client rejects any other status or length; in particular `200` (a host that ignores `Range` and sends
  the whole shard), cancelling the body.

Privacy: the set $S$ is independent of the queried index, so URLs, byte ranges, request order and
timing reveal nothing about it (a (shard, offset) pair is just the column index). Caching by CDNs or
proxies is harmless.

## 3. Compute server: `POST /rc-pir/query`

Request:

- Body: $q_c=He+e_i\in\mathbb{F}_2^t$ packed MSB-first, $\lceil t/8\rceil$ bytes, unused trailing bits zero.
- `Content-Type: application/octet-stream`.

Response:

- `200`, `Content-Type: application/octet-stream`, body: $Xq_c\in\mathbb{F}_2^\ell$, exactly $L$ bytes.
- Header `RC-PIR-DB-Digest: sha256:<hex>` (the `db_digest` the server holds); the client aborts on mismatch
  with `params.json`.
- `400` if the body is shorter than $\lceil t/8\rceil$ bytes or trailing bits are non-zero; `413` if it is
  longer (rejected without being buffered).
- `503` with `Retry-After: <seconds>` if the server's queue is full (the query was not processed), `500` if
  processing failed. The client may retry; resending the same $q_c$ (same $S$) is preferable, since the
  server learns nothing beyond the first copy and no query of the budget $Q$ is used up.

A client that needs several blocks sends several queries (concurrently, over one HTTP/2 connection); the
server merges concurrent queries into shared passes over $X$ (`docs/compute_server.md` §2).

## 4. Client flow for block $i$

1. Fetch and validate `params.json` (pinned digest or trusted source; compare the copies on both origins).
2. Sample $S\subseteq[m]$, $|S|=s$, uniformly with the OS CSPRNG.
3. Expand the $s$ columns $H_{*,j}$, $j\in S$, from `h_seed` (`h_prg`); compute $q_c=\sum_{j\in S}H_{*,j}+e_i$.
4. Concurrently: `GET` the $s$ column ranges (§2); `POST` $q_c$.
5. $\text{col}=Xq_c\oplus\bigoplus_{j\in S}R_{*,j}$ (bytewise XOR of $s+1$ buffers of $L$ bytes).
6. `len = u32_be(col[0:4])`; return `col[4:4+len]` (`db_format.md` §3).

Each query uses fresh $S$. The security analysis assumes at most $Q=2^{32}$ queries per $H$ in total;
after that the database must be re-encoded with a new `h_seed`. (Documented only; servers do not enforce it.)

## 5. Browser requirements (the client is a browser, `docs/stack.md`)

- **HTTPS on both origins.** WebCrypto needs a secure context and browsers speak HTTP/2 only over TLS
  (`localhost` counts as secure for development).
- **CORS on every response** (well-known file, shards, query endpoint):
  `Access-Control-Allow-Origin` (the client's origin or `*`).
- **Compute endpoint preflight.** `Content-Type: application/octet-stream` is not CORS-safelisted, so the
  browser first sends `OPTIONS /rc-pir/query`. The server answers with a `2xx` status (the Rust server,
  via `tower-http`, sends `200`; browsers accept any `2xx`) and
  `Access-Control-Allow-Methods: POST`, `Access-Control-Allow-Headers: Content-Type`, and
  `Access-Control-Max-Age` (e.g. `86400`) so the preflight is cached.
- **Expose the headers the client reads:** `Access-Control-Expose-Headers: RC-PIR-DB-Digest, Retry-After` on
  query responses.
- **Retrieval GETs** are simple requests (no preflight): a single byte range `bytes=a-b` is a
  CORS-safelisted `Range` value. The static host must still send `Access-Control-Allow-Origin`;
  choose a host that allows setting response headers.

## 6. Notes

- Storage is $mL\approx c\,n$ bytes in $\lceil m/C\rceil$ shards (e.g. 16 GiB in 256 shards of 64 MiB for
  a 1 GiB DB at $c=16$). Hosts limit file and total size: GitHub blocks files over 100 MiB and limits
  Pages sites to 1 GB, so check before deploying.
- Range support was checked on GitHub Pages and `raw.githubusercontent.com` (both answer `206`);
  S3, CloudFront, nginx and Caddy support it too.
