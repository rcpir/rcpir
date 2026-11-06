#!/usr/bin/env node
// rcpir-get: retrieve one block privately (Node >= 19).
//
//   rcpir-get --retrieval URL --compute URL --index i [--out FILE] [--pin-sha256 HEX] [--timeout-ms MS]
//             [--gdrive-file ID | --onedrive-link URL | --dropbox-link URL ...]
//
// --gdrive-file: read the columns of R from this Google Drive file (all of R in one file) through the Drive API,
// with the API key from the environment variable RCPIR_GDRIVE_KEY.
// --onedrive-link: read them from this OneDrive file (all of R in one file), given by its "Anyone with the link"
// share link.
// --dropbox-link: read them from this Dropbox file (all of R in one file), given by its shared link
// (https://www.dropbox.com/scl/fi/<id>/<name>?rlkey=...); repeat it for copies of the file (faster: Dropbox limits
// the request rate per file). params.json still comes from --retrieval.
// Writes the payload to FILE, or to stdout. --timeout-ms bounds each of the two phases
// (params discovery, retrieval); default 30000. For self-signed development certificates
// set NODE_EXTRA_CA_CERTS=/path/to/ca.pem.

import { writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { RcPirClient } from "./client.js";
import { Dropbox, GoogleDrive, OneDrive } from "./providers.js";

const USAGE =
  "usage: rcpir-get --retrieval URL --compute URL --index i [--out FILE] [--pin-sha256 HEX] [--timeout-ms MS]\n" +
  "                 [--gdrive-file ID | --onedrive-link URL | --dropbox-link URL ...]";

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
      "gdrive-file": { type: "string" },
      "onedrive-link": { type: "string" },
      "dropbox-link": { type: "string", multiple: true },
    },
  }));
} catch (e) {
  console.error(`${(e as Error).message}\n${USAGE}`);
  process.exit(2);
}
const timeoutOk = args["timeout-ms"] === undefined || /^[1-9]\d*$/.test(args["timeout-ms"]);
const oneProvider = [args["gdrive-file"], args["onedrive-link"], args["dropbox-link"]].filter((a) => a !== undefined).length <= 1;
if (!args.retrieval || !args.compute || !/^\d+$/.test(args.index ?? "") || !timeoutOk || !oneProvider) {
  console.error(USAGE);
  process.exit(2);
}

try {
  const gdrive = args["gdrive-file"];
  const onedrive = args["onedrive-link"];
  const dropbox = args["dropbox-link"];
  const opts = {
    retrieval: args.retrieval,
    provider:
      gdrive !== undefined ? new GoogleDrive(gdrive, process.env["RCPIR_GDRIVE_KEY"] ?? "")
      : onedrive !== undefined ? new OneDrive(onedrive)
      : dropbox !== undefined ? new Dropbox(dropbox)
      : undefined,
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
