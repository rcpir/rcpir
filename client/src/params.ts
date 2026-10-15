// params.json (docs/params_format.md): parsing and validation (§4).

import { toHex } from "./bits.js";
import { RcPirError } from "./errors.js";

export interface Params {
  format_version: number;
  t: number;
  ell: number;
  L: number;
  m: number;
  s: number;
  h_prg: string;
  h_seed: string;
  noise: string;
  db_digest: string;
  r_digest: string;
  columns_per_shard: number;
  security?: { mode?: string; insecure?: boolean; [k: string]: unknown };
}

const INTEGERS = ["format_version", "t", "ell", "L", "m", "s", "columns_per_shard"] as const;
const STRINGS = ["h_prg", "h_seed", "noise", "db_digest", "r_digest"] as const;
const DIGEST = /^sha256:[0-9a-f]{64}$/;

/** Parses and validates params.json. Throws RcPirError("params-invalid"). */
export function parseParams(bytes: Uint8Array): Params {
  const fail = (msg: string): never => {
    throw new RcPirError("params-invalid", `params.json: ${msg}`);
  };
  let p: Params;
  try {
    p = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return fail("not valid JSON");
  }
  if (typeof p !== "object" || p === null) fail("not a JSON object");
  for (const k of INTEGERS) if (!Number.isSafeInteger(p[k])) fail(`"${k}" must be an integer`);
  for (const k of STRINGS) if (typeof p[k] !== "string") fail(`"${k}" must be a string`);

  if (p.format_version !== 1) fail(`unsupported format_version ${p.format_version}`);
  if (p.h_prg !== "aes128-ctr-col-v1") fail(`unknown h_prg "${p.h_prg}"`);
  if (p.noise !== "fixed-weight") fail(`unknown noise "${p.noise}"`);
  if (p.t < 1) fail("t must be >= 1");
  if (!(1 <= p.s && p.s <= p.m && p.m <= 2 ** 32)) fail("need 1 <= s <= m <= 2^32");
  if (p.L < 8 || p.L % 8 !== 0) fail("L must be >= 8 and a multiple of 8");
  if (p.ell !== 8 * p.L) fail("ell must equal 8 * L");
  if (!(1 <= p.columns_per_shard && p.columns_per_shard <= p.m)) fail("need 1 <= columns_per_shard <= m");
  if (!/^[0-9a-f]{32}$/.test(p.h_seed)) fail("h_seed must be 32 lowercase hex characters");
  if (!DIGEST.test(p.db_digest) || !DIGEST.test(p.r_digest)) fail("digests must be sha256:<64 lowercase hex>");
  return p;
}

/** True if params.json marks the test-only insecure override (encoder --insecure-m/--insecure-s). */
export function isInsecure(p: Params): boolean {
  return p.security?.insecure === true || p.security?.mode === "insecure-override";
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  return toHex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes as BufferSource)));
}
