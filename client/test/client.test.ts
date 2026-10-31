// End to end against in-process mock retrieval and compute servers.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, before, describe, test } from "node:test";
import { RcPirClient } from "../src/client.js";
import { RcPirError } from "../src/errors.js";
import type { RetrievalProvider } from "../src/providers.js";
import { isWellFormed, makeDb, samplePayloads, startServers, type Faults, type MockDb } from "./helpers.js";

const isCode = (code: string) => (e: unknown) => e instanceof RcPirError && e.code === code;

describe("RcPirClient", () => {
  let db: MockDb;
  let srv: Awaited<ReturnType<typeof startServers>>;
  let client: RcPirClient;

  before(async () => {
    db = await makeDb(samplePayloads(13, 21), 40, 5); // t = 13 is not a multiple of 8
    srv = await startServers(db);
    client = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute });
  });
  after(() => srv.close());

  test("retrieves every block with s distinct columns and one well-formed query", async () => {
    assert.equal(client.insecure, true);
    for (let i = 0; i < db.t; i++) {
      srv.columnRequests.length = 0;
      srv.queries.length = 0;
      assert.deepEqual(await client.retrieve(i), db.payloads[i], `block ${i}`);
      assert.equal(new Set(srv.columnRequests).size, db.s);
      assert.equal(srv.queries.length, 1);
      assert.ok(isWellFormed(srv.queries[0]!, db.t));
    }
  });

  test("a fresh S for every query", async () => {
    const supports = new Set<string>();
    for (let k = 0; k < 10; k++) {
      srv.columnRequests.length = 0;
      await client.retrieve(0);
      supports.add(srv.columnRequests.sort((a, b) => a - b).join(","));
    }
    assert.ok(supports.size > 1);
  });

  test("pinned SHA-256 of params.json", async () => {
    const pin = createHash("sha256").update(db.paramsBytes).digest("hex");
    await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, pinSha256: pin });
    await assert.rejects(
      RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, pinSha256: "00".repeat(32) }),
      isCode("params-pin-mismatch"),
    );
  });

  test("fromParams (trusted source)", async () => {
    const c = await RcPirClient.fromParams(db.paramsBytes, { retrieval: srv.retrieval, compute: srv.compute });
    assert.deepEqual(await c.retrieve(7), db.payloads[7]);
  });

  test("provider: columns from one object with all of R (GoogleDrive layout), params from the retrieval origin", async () => {
    const located: number[] = [];
    const provider: RetrievalProvider = {
      name: "test",
      locate(j, p) {
        located.push(j);
        return { url: new URL("/all?key=SECRET", srv.retrieval), offset: j * p.L };
      },
    };
    const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, provider });
    for (const i of [0, 6, db.t - 1]) assert.deepEqual(await c.retrieve(i), db.payloads[i], `block ${i}`);
    assert.equal(located.length, 3 * db.s);
  });

  test("provider: error messages do not show the URL's query string (API keys)", async () => {
    const provider: RetrievalProvider = {
      name: "test",
      locate: (j, p) => ({ url: new URL("/missing?key=SECRET", srv.retrieval), offset: j * p.L }),
    };
    const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, provider });
    await assert.rejects(c.retrieve(0), (e) => isCode("http-status")(e) && !(e as Error).message.includes("SECRET"));
  });

  test("prepare: columns downloaded ahead with progress; retrieve then only sends the query", async () => {
    srv.columnRequests.length = 0;
    const progress: number[] = [];
    const p = client.prepare((done, total) => {
      assert.equal(total, db.s);
      progress.push(done);
    });
    assert.equal(new Set(p.S).size, db.s);
    assert.equal(p.query, null);
    await p.ready;
    assert.deepEqual(progress, Array.from({ length: db.s }, (_, k) => k + 1));
    assert.deepEqual([...srv.columnRequests].sort((a, b) => a - b), [...p.S].sort((a, b) => a - b));
    srv.columnRequests.length = 0;
    srv.queries.length = 0;
    assert.deepEqual(await client.retrieve(5, p), db.payloads[5]);
    assert.equal(srv.columnRequests.length, 0);
    assert.deepEqual(p.query, srv.queries[0]);
  });

  test("prepare: retrieve before the columns are in", async () => {
    const p = client.prepare();
    assert.deepEqual(await client.retrieve(3, p), db.payloads[3]);
  });

  test("prepare: a prepared lookup is used once, and only by its client", async () => {
    const p = client.prepare();
    await client.retrieve(1, p);
    await assert.rejects(client.retrieve(2, p), isCode("bad-argument"));
    const other = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute });
    await assert.rejects(other.retrieve(1, client.prepare()), isCode("bad-argument"));
  });

  test("bad index, origin with a path, invalid URL, bad timeout", async () => {
    await assert.rejects(client.retrieve(db.t), isCode("bad-argument"));
    await assert.rejects(
      RcPirClient.connect({ retrieval: srv.retrieval + "/db", compute: srv.compute }),
      isCode("bad-argument"),
    );
    await assert.rejects(RcPirClient.connect({ retrieval: "not a url", compute: srv.compute }), isCode("bad-argument"));
    for (const timeoutMs of [0, -1, NaN]) {
      await assert.rejects(
        RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, timeoutMs }),
        isCode("bad-argument"),
      );
    }
  });
});

describe("failures", () => {
  let db: MockDb;
  before(async () => {
    db = await makeDb(samplePayloads(9, 10), 24, 3);
  });

  async function retrieveWith(faults: Faults, timeoutMs?: number): Promise<Uint8Array> {
    const srv = await startServers(db, faults);
    try {
      const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, timeoutMs });
      return await c.retrieve(0);
    } finally {
      srv.close();
    }
  }

  /** Polls until cond() holds; fails after `ms`. */
  async function eventually(cond: () => boolean, ms = 2000): Promise<void> {
    for (const end = Date.now() + ms; !cond(); await new Promise((ok) => setTimeout(ok, 10))) {
      if (Date.now() > end) assert.fail("condition not reached");
    }
  }

  test("params.json differs between origins", () =>
    assert.rejects(retrieveWith({ computeParamsBytes: new TextEncoder().encode(JSON.stringify(db.params)) }),
      isCode("params-mismatch")));
  test("wrong digest header", () =>
    assert.rejects(retrieveWith({ digestHeader: "sha256:" + "00".repeat(32) }), isCode("digest-mismatch")));
  test("missing digest header", () => assert.rejects(retrieveWith({ digestHeader: null }), isCode("digest-mismatch")));
  test("short column range", () => assert.rejects(retrieveWith({ shortColumns: true }), isCode("bad-length")));
  test("host ignores Range (200 with the whole shard)", () =>
    assert.rejects(retrieveWith({ ignoreRange: true }), isCode("http-status")));
  test("long compute answer", () => assert.rejects(retrieveWith({ longAnswer: true }), isCode("bad-length")));

  test("prepare: a failed download rejects ready and the retrieve that uses it", async () => {
    const srv = await startServers(db, { columnStatus: 404 });
    try {
      const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute });
      c.prepare(); // never used: its failure must not become an unhandled rejection
      const p = c.prepare();
      await assert.rejects(p.ready, isCode("http-status"));
      await assert.rejects(c.retrieve(0, p), isCode("http-status"));
      await new Promise((ok) => setTimeout(ok, 50));
    } finally {
      srv.close();
    }
  });
  test("column 404", () => assert.rejects(retrieveWith({ columnStatus: 404 }), isCode("http-status")));

  test("timeout: compute server never answers; the query is aborted", async () => {
    const srv = await startServers(db, { hangCompute: true });
    try {
      const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, timeoutMs: 300 });
      const start = Date.now();
      await assert.rejects(c.retrieve(0), isCode("timeout"));
      assert.ok(Date.now() - start < 2000);
      await eventually(() => srv.abortedQueries() === 1);
    } finally {
      srv.close();
    }
  });

  test("first failure aborts the other requests (no wait for the timeout)", async () => {
    // Columns fail after 100 ms, when the (hanging) compute query has surely arrived.
    const srv = await startServers(db, { hangCompute: true, columnStatus: 404, columnDelayMs: 100 });
    try {
      const c = await RcPirClient.connect({ retrieval: srv.retrieval, compute: srv.compute, timeoutMs: 60_000 });
      await assert.rejects(c.retrieve(0), isCode("http-status"));
      await eventually(() => srv.abortedQueries() === 1);
    } finally {
      srv.close();
    }
  });

  test("network: nothing listens on the compute origin", async () => {
    const srv = await startServers(db);
    const dead = await startServers(db);
    dead.close(); // its port is now closed
    try {
      await assert.rejects(
        RcPirClient.connect({ retrieval: srv.retrieval, compute: dead.compute }),
        (e) => isCode("network")(e) && /ECONNREFUSED/.test((e as Error).message),
      );
    } finally {
      srv.close();
    }
  });
});
