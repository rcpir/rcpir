import assert from "node:assert/strict";
import { test } from "node:test";
import { sampleSubset } from "../src/sample.js";

test("size, range, distinct, sorted", () => {
  for (const [m, s] of [[1, 1], [10, 10], [48, 41], [2 ** 21, 45], [2 ** 32, 45]] as const) {
    const S = sampleSubset(m, s);
    assert.equal(S.length, s);
    S.forEach((j, k) => {
      assert.ok(Number.isInteger(j) && j >= 0 && j < m);
      if (k > 0) assert.ok(S[k - 1]! < j);
    });
  }
  assert.throws(() => sampleSubset(5, 6), RangeError);
});

test("uniform over the C(5,2) = 10 subsets (chi-square)", () => {
  const N = 50000;
  const counts = new Map<string, number>();
  for (let k = 0; k < N; k++) {
    const key = sampleSubset(5, 2).join(",");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  assert.equal(counts.size, 10);
  let chi2 = 0;
  for (const c of counts.values()) chi2 += (c - N / 10) ** 2 / (N / 10);
  assert.ok(chi2 < 33.7, `chi2 = ${chi2}`); // 9 degrees of freedom: P[chi2 > 33.7] ~ 1e-4
});

test("bound 3 (not a power of two) is unbiased", () => {
  const N = 30000;
  const hits = [0, 0, 0];
  for (let k = 0; k < N; k++) hits[sampleSubset(3, 1)[0]!]!++;
  for (const h of hits) assert.ok(Math.abs(h - N / 3) < 6 * Math.sqrt(N / 3), `hits ${hits}`);
});
