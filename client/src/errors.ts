export type RcPirErrorCode =
  | "params-invalid" // params.json fails validation (params_format.md §4)
  | "params-mismatch" // the copies on the two origins differ
  | "params-pin-mismatch" // SHA-256 of params.json differs from the pinned value
  | "bad-argument" // e.g. index out of range, malformed origin URL, bad timeout
  | "network" // a request failed before a complete response arrived (DNS, TCP, TLS, CORS, reset)
  | "timeout" // the requests of one call did not complete within timeoutMs
  | "http-status" // a server answered with a status other than 200
  | "bad-length" // a response body has the wrong length
  | "digest-mismatch" // RC-PIR-DB-Digest header differs from params.db_digest
  | "decode-invalid"; // block header says len > L-4

export class RcPirError extends Error {
  constructor(
    readonly code: RcPirErrorCode,
    message: string,
    options?: { cause?: unknown },
  ) {
    super(message, options);
    this.name = "RcPirError";
  }
}
