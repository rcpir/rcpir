// The retrieval providers: column locations and argument checks (no network).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { RcPirError } from "../src/errors.js";
import type { Params } from "../src/params.js";
import { GitHubPages, GoogleDrive } from "../src/providers.js";

// Compiled to client/build-test/test/, so the repository root is three levels up.
const load = (name: string): any =>
  JSON.parse(readFileSync(new URL(`../../../testvectors/vectors/${name}`, import.meta.url), "utf8"));
const params = (p: { L: number; m: number; columns_per_shard: number }) => p as unknown as Params;
const badArgument = (e: unknown) => e instanceof RcPirError && e.code === "bad-argument";

test("GitHubPages: column locations of column_location.json on https://<site>.github.io", () => {
  const gh = new GitHubPages("rcpir");
  assert.equal(gh.name, "GitHub Pages");
  for (const c of load("column_location.json").cases) {
    const { url, offset } = gh.locate(c.j, params({ L: c.L, m: c.j + 1, columns_per_shard: c.columns_per_shard }));
    assert.equal(url.href, `https://rcpir.github.io${c.path}`);
    assert.equal(offset, c.offset);
  }
});

test("GitHubPages: the site name is lowercased (hostnames are case-insensitive)", () => {
  const { url } = new GitHubPages("RcPir").locate(16384, params({ L: 4096, m: 231932, columns_per_shard: 16384 }));
  assert.equal(url.href, "https://rcpir.github.io/rc-pir/r/00000001");
});

test("GitHubPages: the site name cannot change the host", () => {
  for (const bad of ["", "evil.com/x", "a.b", "-x", "x-", "x@y", "x:1"]) {
    assert.throws(() => new GitHubPages(bad), badArgument, bad);
  }
});

test("GoogleDrive: one file, column j at j * L, Drive API URL with the key", () => {
  const gd = new GoogleDrive("1eEkZP-xN63uG1-34x4Q19zRb9nj0arPG", "KEY_123");
  assert.equal(gd.name, "Google Drive");
  const p = params({ L: 4096, m: 231932, columns_per_shard: 16384 });
  for (const j of [0, 1, 16384, 231931]) {
    const { url, offset } = gd.locate(j, p);
    assert.equal(url.origin + url.pathname, "https://www.googleapis.com/drive/v3/files/1eEkZP-xN63uG1-34x4Q19zRb9nj0arPG");
    assert.equal(url.searchParams.get("alt"), "media");
    assert.equal(url.searchParams.get("key"), "KEY_123");
    assert.equal(offset, j * 4096);
  }
});

test("GoogleDrive: bad file ID or missing key", () => {
  for (const bad of ["", "../x", "a/b", "a?b", "a b"]) assert.throws(() => new GoogleDrive(bad, "k"), badArgument, bad);
  assert.throws(() => new GoogleDrive("abc", ""), badArgument);
});
