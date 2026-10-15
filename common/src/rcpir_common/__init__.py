"""Spec primitives shared by the Python components (encoder, test-vector generator).

Modules: `bits` (MSB-first packing), `hprg` (aes128-ctr-col-v1), `blocks` (block <-> column),
`protocol` (paths, header, digest strings), `params` (params.json constants and validation).
The TypeScript client and the Rust server implement the same primitives; all are checked
against `testvectors/vectors/`.
"""
