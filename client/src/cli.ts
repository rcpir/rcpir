#!/usr/bin/env node
// rcpir-get: retrieve one block privately (Node >= 19).
//
//   rcpir-get --retrieval URL --compute URL --index i [--out FILE] [--pin-sha256 HEX] [--timeout-ms MS]
//
// Writes the payload to FILE, or to stdout. --timeout-ms bounds each of the two phases
// (params discovery, retrieval); default 30000. For self-signed development certificates
// set NODE_EXTRA_CA_CERTS=/path/to/ca.pem.

import { writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { RcPirClient } from "./client.js";

const USAGE = "usage: rcpir-get --retrieval URL --compute URL --index i [--out FILE] [--pin-sha256 HEX] [--timeout-ms MS]";

let args;
try {
  ({ values: args } = parseArgs({
    options: {
      retrieval: { type: "string" },
      compute: { type: "string" },
      index: { type: "string" },
      out: { type: "string" },
      "pin-sha256": { type: "string" },
      "timeout-ms": { type: "string" },
    },
  }));
} catch (e) {
  console.error(`${(e as Error).message}\n${USAGE}`);
  process.exit(2);
}
const timeoutOk = args["timeout-ms"] === undefined || /^[1-9]\d*$/.test(args["timeout-ms"]);
if (!args.retrieval || !args.compute || !/^\d+$/.test(args.index ?? "") || !timeoutOk) {
  console.error(USAGE);
  process.exit(2);
}

try {
  const opts = {
    retrieval: args.retrieval,
    compute: args.compute,
    pinSha256: args["pin-sha256"],
    timeoutMs: args["timeout-ms"] === undefined ? undefined : Number(args["timeout-ms"]),
  };
  const client = await RcPirClient.connect(opts);
  if (client.insecure) console.error("WARNING: insecure test parameters, no privacy against the compute server");
  const payload = await client.retrieve(Number(args.index));
  if (args.out) writeFileSync(args.out, payload);
  else process.stdout.write(payload);
} catch (e) {
  console.error(`error: ${(e as Error).message}`);
  process.exit(1);
}
