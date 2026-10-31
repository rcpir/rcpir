// Test helpers: a tiny encoded database (X, H from h_prg, R = XH) and in-process mock servers.

import { createHash } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { xorInto } from "../src/bits.js";
import { hColumn, importHSeed } from "../src/h_prg.js";

const sha256 = (b: Uint8Array): string => createHash("sha256").update(b).digest("hex");

/** Bit i of a packed MSB-first vector. */
export const getBit = (buf: Uint8Array, i: number): number => (buf[i >> 3]! >> (7 - (i & 7))) & 1;

/** Right length and unused trailing bits zero (what the compute server checks). */
export function isWellFormed(q: Uint8Array, t: number): boolean {
  return q.length === Math.ceil(t / 8) && (t % 8 === 0 || (q[q.length - 1]! & (0xff >> (t % 8))) === 0);
}

/** Column of X for one block: u32 BE length, payload, zero padding to L bytes. */
export function encodeColumn(payload: Uint8Array, L: number): Uint8Array {
  const col = new Uint8Array(L);
  new DataView(col.buffer).setUint32(0, payload.length);
  col.set(payload, 4);
  return col;
}

/** X q: XOR of the columns of X selected by the packed vector q. */
export function multiplyX(X: Uint8Array[], q: Uint8Array): Uint8Array {
  const out = new Uint8Array(X[0]!.length);
  X.forEach((col, r) => getBit(q, r) && xorInto(out, col));
  return out;
}

/** Deterministic payloads of varying length (block 0 has maxLen bytes, block 1 is empty). */
export function samplePayloads(t: number, maxLen: number): Uint8Array[] {
  return Array.from({ length: t }, (_, j) => {
    const len = j === 0 ? maxLen : j === 1 ? 0 : (j * 7) % (maxLen + 1);
    return Uint8Array.from({ length: len }, (_, k) => (j * 31 + k * 17 + 5) & 0xff);
  });
}

export interface MockDb {
  payloads: Uint8Array[];
  t: number;
  L: number;
  m: number;
  s: number;
  X: Uint8Array[]; // columns of X
  R: Uint8Array[]; // columns of R = XH
  columnsPerShard: number;
  params: Record<string, unknown>;
  paramsBytes: Uint8Array;
}

/**
 * Encodes `payloads` as the encoder would, with the insecure test override (small m). The default of
 * 3 columns per shard gives several shards, the last one possibly smaller.
 */
export async function makeDb(payloads: Uint8Array[], m: number, s: number, columnsPerShard = 3): Promise<MockDb> {
  const seed = "000102030405060708090a0b0c0d0e0f";
  const t = payloads.length;
  const L = Math.ceil((4 + Math.max(...payloads.map((p) => p.length))) / 8) * 8;
  const X = payloads.map((p) => encodeColumn(p, L));
  const key = await importHSeed(Buffer.from(seed, "hex"));
  const R: Uint8Array[] = [];
  for (let j = 0; j < m; j++) R.push(multiplyX(X, await hColumn(key, t, j)));
  const params = {
    format_version: 1,
    t,
    ell: 8 * L,
    L,
    m,
    s,
    h_prg: "aes128-ctr-col-v1",
    h_seed: seed,
    noise: "fixed-weight",
    db_digest: `sha256:${sha256(Buffer.concat(X))}`,
    r_digest: `sha256:${sha256(Buffer.concat(R))}`,
    columns_per_shard: columnsPerShard,
    security: { mode: "insecure-override", insecure: true },
  };
  const paramsBytes = new TextEncoder().encode(JSON.stringify(params, null, 2));
  return { payloads, t, L, m, s, X, R, columnsPerShard, params, paramsBytes };
}

/** Misbehaviours of the mock servers, for the failure tests. */
export interface Faults {
  digestHeader?: string | null; // RC-PIR-DB-Digest value; null omits the header
  computeParamsBytes?: Uint8Array; // different params.json on the compute origin
  shortColumns?: boolean; // column ranges one byte short
  columnStatus?: number; // status code for column requests
  ignoreRange?: boolean; // the retrieval server ignores Range and sends the whole shard with 200
  longAnswer?: boolean; // compute answer one byte long
  hangCompute?: boolean; // the compute server never answers queries
  columnDelayMs?: number; // the retrieval server waits this long before answering a column request
}

export interface MockServers {
  retrieval: string;
  compute: string;
  columnRequests: number[]; // column indices requested so far
  queries: Uint8Array[]; // compute query bodies received so far
  abortedQueries(): number; // queries whose connection the client closed before the answer was sent
  close(): void;
}

type Handler = (req: IncomingMessage, res: ServerResponse) => Promise<void> | void;

async function listen(handler: Handler) {
  const server = createServer((req, res) => void handler(req, res));
  await new Promise<void>((ok) => server.listen(0, "127.0.0.1", ok));
  return { server, url: `http://127.0.0.1:${(server.address() as AddressInfo).port}` };
}

export async function startServers(db: MockDb, faults: Faults = {}): Promise<MockServers> {
  const columnRequests: number[] = [];
  const queries: Uint8Array[] = [];
  let aborted = 0;

  const retrieval = await listen(async (req, res) => {
    if (req.url === "/.well-known/rc-pir.json") return void res.end(db.paramsBytes);
    if (faults.columnDelayMs) await new Promise((ok) => setTimeout(ok, faults.columnDelayMs));
    // /all (any query string): all of R as one object, the single-file layout of providers like GoogleDrive.
    const all = req.url?.split("?")[0] === "/all";
    const C = all ? db.m : db.columnsPerShard;
    const shard = all ? 0 : parseInt(req.url?.match(/^\/rc-pir\/r\/([0-9a-f]{8})$/)?.[1] ?? "ffffffff", 16);
    if (shard * C >= db.m) return void res.writeHead(404).end();
    const body = Buffer.concat(db.R.slice(shard * C, (shard + 1) * C));
    if (faults.ignoreRange) return void res.writeHead(200).end(body);
    // A single column, aligned: the client only ever asks for that.
    const [, a, b] = (req.headers.range?.match(/^bytes=(\d+)-(\d+)$/) ?? []).map(Number);
    if (a === undefined || b === undefined || a % db.L !== 0 || b - a + 1 !== db.L || b >= body.length) {
      return void res.writeHead(416).end();
    }
    const j = shard * C + a / db.L;
    columnRequests.push(j);
    if (faults.columnStatus) return void res.writeHead(faults.columnStatus).end();
    res.writeHead(206, { "Content-Range": `bytes ${a}-${b}/${body.length}` });
    res.end(faults.shortColumns ? db.R[j]!.subarray(1) : db.R[j]);
  });

  const compute = await listen(async (req, res) => {
    if (req.url === "/.well-known/rc-pir.json") return void res.end(faults.computeParamsBytes ?? db.paramsBytes);
    if (req.method !== "POST" || req.url !== "/rc-pir/query") return void res.writeHead(404).end();
    const qc = new Uint8Array(Buffer.concat(await req.toArray()));
    if (!isWellFormed(qc, db.t)) return void res.writeHead(400).end();
    queries.push(qc);
    res.on("close", () => void (res.writableEnded || aborted++));
    if (faults.hangCompute) return;
    const digest = faults.digestHeader === undefined ? (db.params["db_digest"] as string) : faults.digestHeader;
    if (digest !== null) res.setHeader("RC-PIR-DB-Digest", digest);
    const answer = multiplyX(db.X, qc);
    res.end(faults.longAnswer ? Buffer.concat([answer, Buffer.from([0])]) : answer);
  });

  return {
    retrieval: retrieval.url,
    compute: compute.url,
    columnRequests,
    queries,
    abortedQueries: () => aborted,
    close() {
      for (const { server } of [retrieval, compute]) {
        server.closeAllConnections();
        server.close();
      }
    },
  };
}
