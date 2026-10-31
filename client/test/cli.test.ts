import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { after, before, describe, test } from "node:test";
import { makeDb, samplePayloads, startServers, type MockServers } from "./helpers.js";

const CLI = fileURLToPath(new URL("../src/cli.js", import.meta.url));

function run(args: string[]): Promise<{ code: number; stdout: Buffer; stderr: string }> {
  return new Promise((ok) => {
    execFile(process.execPath, [CLI, ...args], { encoding: "buffer" }, (err, stdout, stderr) => {
      const code = err ? ((err as { code?: number }).code ?? 1) : 0;
      ok({ code: typeof code === "number" ? code : 1, stdout, stderr: stderr.toString() });
    });
  });
}

describe("rcpir-get", () => {
  // Successful runs (stdout and --out) are covered by e2e/run.sh.
  let srv: MockServers;
  before(async () => {
    srv = await startServers(await makeDb(samplePayloads(10, 17), 32, 4));
  });
  after(() => srv.close());

  test("errors: bad pin, bad index, missing args, bad timeout", async () => {
    const base = ["--retrieval", srv.retrieval, "--compute", srv.compute];
    const r1 = await run([...base, "--index", "0", "--pin-sha256", "00".repeat(32)]);
    assert.equal(r1.code, 1);
    assert.match(r1.stderr, /SHA-256/);
    const r2 = await run([...base, "--index", "10"]);
    assert.equal(r2.code, 1);
    assert.match(r2.stderr, /index 10/);
    const r3 = await run([...base, "--index", "x"]);
    assert.equal(r3.code, 2);
    const r4 = await run(["--index", "0"]);
    assert.equal(r4.code, 2);
    const r5 = await run([...base, "--index", "0", "--gdrive-file", "abc"]); // RCPIR_GDRIVE_KEY not set
    assert.equal(r5.code, 1);
    assert.match(r5.stderr, /needs an API key/);
    for (const bad of ["0", "-5", "1.5", "x"]) {
      assert.equal((await run([...base, "--index", "0", "--timeout-ms", bad])).code, 2, `--timeout-ms ${bad}`);
    }
  });
});
