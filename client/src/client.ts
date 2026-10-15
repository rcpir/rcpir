// The client: params discovery and the retrieval flow of docs/protocol.md §4.

import { fromHex } from "./bits.js";
import { RcPirError } from "./errors.js";
import { importHSeed } from "./h_prg.js";
import { isInsecure, parseParams, sha256Hex, type Params } from "./params.js";
import { buildComputeQuery, columnLocation, combineAnswers, decodeBlock } from "./query.js";
import { sampleSubset } from "./sample.js";

export const DEFAULT_TIMEOUT_MS = 30_000;

export interface ClientOptions {
  /** Origin of the retrieval (static) server, e.g. "https://static.example.org". */
  retrieval: string;
  /** Origin of the compute server, e.g. "https://compute.example.org". */
  compute: string;
  /** Expected SHA-256 (hex) of the params.json bytes. */
  pinSha256?: string;
  /**
   * Deadline for all requests of one call (`connect` or `retrieve`), including downloading the
   * bodies. Default DEFAULT_TIMEOUT_MS.
   */
  timeoutMs?: number;
}

function checkTimeout(ms: number | undefined): number {
  if (ms === undefined) return DEFAULT_TIMEOUT_MS;
  if (!Number.isFinite(ms) || ms <= 0) throw new RcPirError("bad-argument", `timeoutMs must be > 0, got ${ms}`);
  return ms;
}

/**
 * Runs the concurrent requests of one call under a single deadline. Every request must use the
 * given signal. On a timeout, or when one request fails, the requests still in flight are aborted.
 */
async function withDeadline<T>(timeoutMs: number, run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new RcPirError("timeout", `requests did not complete within ${timeoutMs} ms`)),
    timeoutMs,
  );
  try {
    return await run(controller.signal);
  } finally {
    clearTimeout(timer);
    controller.abort(); // after a failure: cancels the other requests; after success: no effect
  }
}

/** Maps a rejection of fetch() or of reading the body to an RcPirError. */
function requestError(url: URL, signal: AbortSignal, e: unknown): RcPirError {
  if (signal.aborted && signal.reason instanceof RcPirError) return signal.reason; // our timeout
  // Node: TypeError("fetch failed") with the socket error as cause. Browsers: TypeError("Failed to
  // fetch") without details (CORS failures look the same).
  const cause = e instanceof Error && e.cause instanceof Error ? `: ${e.cause.message}` : "";
  const msg = e instanceof Error ? e.message : String(e);
  return new RcPirError("network", `request to ${url} failed: ${msg}${cause}`, { cause: e });
}

/**
 * GET or POST `url`; requires status `status` (200, or 206 for a Range request) and, if given, a
 * body of exactly `length` bytes.
 */
async function fetchBytes(
  url: URL,
  signal: AbortSignal,
  init: RequestInit = {},
  length?: number,
  status = 200,
): Promise<[Uint8Array, Response]> {
  let res: Response;
  try {
    res = await fetch(url, { ...init, signal });
  } catch (e) {
    throw requestError(url, signal, e);
  }
  if (res.status !== status) {
    // Release the connection without reading the body (e.g. a whole shard if Range was ignored).
    res.body?.cancel().catch(() => {});
    throw new RcPirError("http-status", `HTTP ${res.status} from ${url}`);
  }
  let body: Uint8Array;
  try {
    body = new Uint8Array(await res.arrayBuffer());
  } catch (e) {
    throw requestError(url, signal, e);
  }
  if (length !== undefined && body.length !== length) {
    throw new RcPirError("bad-length", `${body.length} bytes from ${url}, expected ${length}`);
  }
  return [body, res];
}

/** All paths are absolute from the origin (protocol.md §1), so a URL with a path is a config error. */
function toOrigin(url: string): URL {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    throw new RcPirError("bad-argument", `not a valid URL: ${url}`);
  }
  if (u.pathname !== "/") throw new RcPirError("bad-argument", `expected an origin without a path: ${url}`);
  return u;
}

export class RcPirClient {
  /** True for databases encoded with the test-only insecure override: no privacy. */
  readonly insecure: boolean;
  private readonly retrieval: URL;
  private readonly compute: URL;
  private readonly timeoutMs: number;

  private constructor(readonly params: Params, private readonly hKey: CryptoKey, opts: ClientOptions) {
    this.insecure = isInsecure(params);
    this.retrieval = toOrigin(opts.retrieval);
    this.compute = toOrigin(opts.compute);
    this.timeoutMs = checkTimeout(opts.timeoutMs);
  }

  /** Fetches /.well-known/rc-pir.json from both origins; the two copies must be identical. */
  static async connect(opts: ClientOptions): Promise<RcPirClient> {
    const path = "/.well-known/rc-pir.json";
    const retrieval = new URL(path, toOrigin(opts.retrieval));
    const compute = new URL(path, toOrigin(opts.compute));
    const [[a], [b]] = await withDeadline(checkTimeout(opts.timeoutMs), (signal) =>
      Promise.all([fetchBytes(retrieval, signal), fetchBytes(compute, signal)]),
    );
    if (a.length !== b.length || a.some((x, k) => x !== b[k])) {
      throw new RcPirError("params-mismatch", "params.json differs between the two origins");
    }
    return RcPirClient.fromParams(a, opts);
  }

  /** Uses params.json bytes from a trusted source. */
  static async fromParams(paramsBytes: Uint8Array, opts: ClientOptions): Promise<RcPirClient> {
    if (opts.pinSha256 !== undefined) {
      const got = await sha256Hex(paramsBytes);
      if (got !== opts.pinSha256.toLowerCase()) {
        throw new RcPirError("params-pin-mismatch", `params.json SHA-256 is ${got}, pinned ${opts.pinSha256}`);
      }
    }
    const params = parseParams(paramsBytes);
    return new RcPirClient(params, await importHSeed(fromHex(params.h_seed)), opts);
  }

  /** Retrieves the payload of block i. */
  async retrieve(i: number): Promise<Uint8Array> {
    const { L, m, s, columns_per_shard } = this.params;
    const S = sampleSubset(m, s);
    const qc = await buildComputeQuery(this.params, this.hKey, S, i);

    // All s + 1 requests are sent concurrently, under one deadline.
    const [[answer, res], ...columns] = await withDeadline(this.timeoutMs, (signal) => {
      const computeRequest = fetchBytes(
        new URL("/rc-pir/query", this.compute),
        signal,
        { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: qc as BufferSource },
        L,
      );
      // One single-range GET per column (CORS-safelisted: no preflight); the host must answer 206.
      const columnRequests = S.map((j) => {
        const { path, offset } = columnLocation(j, columns_per_shard, L);
        const range = { headers: { Range: `bytes=${offset}-${offset + L - 1}` } };
        return fetchBytes(new URL(path, this.retrieval), signal, range, L, 206);
      });
      return Promise.all([computeRequest, ...columnRequests]);
    });

    const digest = res.headers.get("RC-PIR-DB-Digest");
    if (digest !== this.params.db_digest) {
      throw new RcPirError("digest-mismatch", `compute server has DB ${digest}, params.json has ${this.params.db_digest}`);
    }
    return decodeBlock(combineAnswers(answer, columns.map(([col]) => col)));
  }
}
