// @rcpir/client: client for the sqrt(n) RC-PIR over F_2 (docs/protocol.md).
// No runtime dependencies: only WebCrypto and fetch (browsers in a secure context, Node >= 19).

export { RcPirClient, Prepared, DEFAULT_TIMEOUT_MS, type ClientOptions } from "./client.js";
export { GitHubPages, GoogleDrive, type RetrievalProvider } from "./providers.js";
export { RcPirError, type RcPirErrorCode } from "./errors.js";
export { parseParams, isInsecure, sha256Hex, type Params } from "./params.js";
// Low-level steps, for deterministic conformance tests.
export { importHSeed, hColumn } from "./h_prg.js";
export { sampleSubset } from "./sample.js";
export { buildComputeQuery, buildHe, addIndex, columnLocation, combineAnswers, decodeBlock } from "./query.js";
export { toHex, fromHex } from "./bits.js";
