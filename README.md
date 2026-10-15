# RC-PIR with √n communication (LPN over F₂)

Implementation of the RC-PIR construction "Optimized Toy Example" (Hadamard-based PIR with dual LPN over $\mathbb{F}_2$). The specs are in
`docs/` (start with `docs/README.md`).

| Directory | Language | Content |
|---|---|---|
| `encoder/` | Python | `rcpir-encode`: JSONL database → `X.bin`, shards of $R=XH$, `params.json` |
| `server/` | Rust | Compute server: answers $Xq_c$ over HTTP/2 + TLS |
| `client/` | TypeScript | `@rcpir/client` library (browsers, Node) and the `rcpir-get` CLI |
| `common/` | Python | `rcpir_common`: spec primitives shared by `encoder/` and `testvectors/` |
| `testvectors/` | JSON + Python | Cross-language test vectors and their generator |
| `e2e/` | Bash, Python, JS | End-to-end test; development static (retrieval) server with CORS |
| `benchmarks/` | Bash, Python, JS, Rust | Benchmarks against SimplePIR/DoublePIR: communication, compute server, encoder, client |

The retrieval server is any static HTTPS host serving `DIR/site/` from the encoder.

## Setup and tests

```bash
git clone https://github.com/rcpir/rcpir && cd rcpir
conda env create -p .env -f environment.yml    # Python 3.12, numpy, cryptography, pytest
(cd client && npm install)                     # TypeScript compiler (no runtime dependencies)
scripts/test-all.sh                            # vectors, common, encoder, client, server, end to end
```

## Quick start (local, plain HTTP)

```bash
export PYTHONPATH=$PWD/encoder/src:$PWD/common/src
.env/bin/python -m rcpir_encoder DB.jsonl --out out --c 16          # tiny DBs: --insecure-m M --insecure-s S
.env/bin/python e2e/static_server.py out/site --port 8081 &
(cd server && cargo run --release --bin rcpir-server -- --params ../out/params.json --x ../out/X.bin \
   --plain --listen 127.0.0.1:8082) &
(cd client && npm run build) && node client/dist/cli.js --retrieval http://localhost:8081 \
   --compute http://localhost:8082 --index 0
```

## License

MIT, see `LICENSE`.
