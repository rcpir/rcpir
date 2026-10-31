// The client: params discovery and the retrieval flow of docs/protocol.md §4.

import { fromHex } from "./bits.js";
import { RcPirError } from "./errors.js";
import { importHSeed } from "./h_prg.js";
import { isInsecure, parseParams, sha256Hex, type Params } from "./params.js";
import type { RetrievalProvider } from "./providers.js";
import { addIndex, buildHe, checkIndex, columnLocation, combineAnswers, decodeBlock } from "./query.js";
import { sampleSubset } from "./sample.js";

export const DEFAULT_TIMEOUT_MS = 30_000;

export interface ClientOptions {
  /** Origin of the retrieval (static) server, e.g. "https://static.example.org". */
  retrieval: string;
  /**
   * Where the columns of R are (providers.ts). Default: the shards on the retrieval origin. params.json is always
   * read from the retrieval origin.
   */
  provider?: RetrievalProvider;
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

/** URL for error messages: without the query string, which may hold an API key (GoogleDrive). */
const shown = (url: URL) => url.origin + url.pathname;

/** Maps a rejection of fetch() or of reading the body to an RcPirError. */
function requestError(url: URL, signal: AbortSignal, e: unknown): RcPirError {
  if (signal.aborted && signal.reason instanceof RcPirError) return signal.reason; // our timeout
  // Node: TypeError("fetch failed") with the socket error as cause. Browsers: TypeError("Failed to
  // fetch") without details (CORS failures look the same).
  const cause = e instanceof Error && e.cause instanceof Error ? `: ${e.cause.message}` : "";
  const msg = e instanceof Error ? e.message : String(e);
  return new RcPirError("network", `request to ${shown(url)} failed: ${msg}${cause}`, { cause: e });
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
    throw new RcPirError("http-status", `HTTP ${res.status} from ${shown(url)}`);
  }
  let body: Uint8Array;
  try {
    body = new Uint8Array(await res.arrayBuffer());
  } catch (e) {
    throw requestError(url, signal, e);
  }
  if (length !== undefined && body.length !== length) {
    throw new RcPirError("bad-length", `${body.length} bytes from ${shown(url)}, expected ${length}`);
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
  private readonly provider: RetrievalProvider | undefined;

  private constructor(readonly params: Params, private readonly hKey: CryptoKey, opts: ClientOptions) {
    this.insecure = isInsecure(params);
    this.retrieval = toOrigin(opts.retrieval);
    this.compute = toOrigin(opts.compute);
    this.timeoutMs = checkTimeout(opts.timeoutMs);
    this.provider = opts.provider;
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

  /**
   * Starts a lookup without the index: samples a fresh S, computes H e and downloads the s columns of R. It reveals
   * nothing about the block that will be read, so it can run while the user picks one; pass the result to
   * retrieve(). onColumn(done, s) is called after each downloaded column (progress display).
   */
  prepare(onColumn?: (done: number, total: number) => void): Prepared {
    const { L, m, s } = this.params;
    const S = sampleSubset(m, s);
    let done = 0;
    const columns = withDeadline(this.timeoutMs, (signal) =>
      Promise.all(
        S.map(async (j) => {
          // One single-range GET per column (CORS-safelisted: no preflight); the host must answer 206.
          // cache: "no-store": with the default mode, Chromium's HTTP cache queues concurrent range requests to the
          // same URL (measured on rcpir.github.io: ~0.5 s per lookup instead of ~0.12 s; ~4.6 s with all of R in one
          // file). Caching is useless here anyway: S is fresh and random for every lookup.
          const { url, offset } = this.locate(j);
          const range: RequestInit = { headers: { Range: `bytes=${offset}-${offset + L - 1}` }, cache: "no-store" };
          const [col] = await fetchBytes(url, signal, range, L, 206);
          onColumn?.(++done, s);
          return col;
        }),
      ),
    );
    return new Prepared(this, S, buildHe(this.params, this.hKey, S), columns);
  }

  /**
   * Retrieves the payload of block i. `prepared` comes from prepare() and is used once; without it, a fresh one is
   * made, so the column downloads and the compute query run concurrently.
   */
  async retrieve(i: number, prepared?: Prepared): Promise<Uint8Array> {
    checkIndex(this.params, i);
    const p = prepared ?? this.prepare();
    // Single use: a second query with the same S for another index i' would reveal e_i + e_i'.
    if (!p.claim(this)) throw new RcPirError("bad-argument", "prepared lookup already used or from another client");
    const qc = addIndex(this.params, await p.he, i);
    p.query = qc;

    // The compute query and the (remaining) column downloads, under one deadline: the first failure aborts the query.
    const [[answer, res], columns] = await withDeadline(this.timeoutMs, (signal) =>
      Promise.all([
        fetchBytes(
          new URL("/rc-pir/query", this.compute),
          signal,
          { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: qc as BufferSource },
          this.params.L,
        ),
        p.columns,
      ]),
    );

    const digest = res.headers.get("RC-PIR-DB-Digest");
    if (digest !== this.params.db_digest) {
      throw new RcPirError("digest-mismatch", `compute server has DB ${digest}, params.json has ${this.params.db_digest}`);
    }
    return decodeBlock(combineAnswers(answer, columns));
  }

  /** URL and byte offset of column j: from the provider, or the shards on the retrieval origin. */
  private locate(j: number): { url: URL; offset: number } {
    if (this.provider) return this.provider.locate(j, this.params);
    const { path, offset } = columnLocation(j, this.params.columns_per_shard, this.params.L);
    return { url: new URL(path, this.retrieval), offset };
  }
}

/** A lookup prepared by RcPirClient.prepare(): S, H e and the s columns (downloaded or in flight). */
export class Prepared {
  /** Resolves when all s columns are downloaded; rejects on the first failure. */
  readonly ready: Promise<void>;
  /** The compute query q_c = H e + e_i sent by retrieve() (for display); null until then. */
  query: Uint8Array | null = null;
  private owner: RcPirClient | null;

  /** @internal */
  constructor(
    owner: RcPirClient,
    /** The column indices S, chosen independently of the block (for display). */
    readonly S: readonly number[],
    /** @internal */ readonly he: Promise<Uint8Array>,
    /** @internal */ readonly columns: Promise<Uint8Array[]>,
  ) {
    this.owner = owner;
    this.ready = columns.then(() => undefined);
    // Failures reach the caller through retrieve() or ready; never as unhandled rejections.
    for (const promise of [he, columns, this.ready]) promise.catch(() => {});
  }

  /** @internal Marks the set as used by `client`; false if it was used before or belongs to another client. */
  claim(client: RcPirClient): boolean {
    if (this.owner !== client) return false;
    this.owner = null;
    return true;
  }
}
