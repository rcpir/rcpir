#!/usr/bin/env python3
"""Development retrieval server: serves the encoder's site/ directory as static files.

Adds what docs/protocol.md §2, §5 ask of the static host: single byte-range requests (206), CORS on
every response and `application/octet-stream` for the shards of R. HTTP/1.1 only (production: Caddy,
nginx, S3, ...).

    python e2e/static_server.py DIR/site --port 8081 [--tls-cert cert.pem --tls-key key.pem]
"""

import argparse
import functools
import os
import re
import ssl
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {"": "application/octet-stream", ".json": "application/json"}

    def send_head(self):
        """Single byte range `bytes=a-b` (all the client sends); everything else as before."""
        self.range_left = None
        m = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not m or not os.path.isfile(path):
            return super().send_head()
        a, b, size = int(m[1]), int(m[2]), os.path.getsize(path)
        if a > b or b >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        f = open(path, "rb")
        f.seek(a)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.send_header("Content-Length", str(b - a + 1))
        self.end_headers()
        self.range_left = b - a + 1
        return f

    def copyfile(self, source, outputfile):
        if self.range_left is None:
            return super().copyfile(source, outputfile)
        outputfile.write(source.read(self.range_left))

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def list_directory(self, path):     # no directory listings
        self.send_error(404)

    def log_message(self, *args):       # quiet
        pass


class Server(ThreadingHTTPServer):
    request_queue_size = 256            # the client opens s + 1 connections at once
    tls: ssl.SSLContext | None = None

    def finish_request(self, request, client_address):
        if self.tls:                    # TLS handshake in the worker thread, not in the accept loop
            request = self.tls.wrap_socket(request, server_side=True)
        super().finish_request(request, client_address)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--tls-cert")
    ap.add_argument("--tls-key")
    a = ap.parse_args()
    server = Server((a.host, a.port), functools.partial(Handler, directory=a.site))
    if a.tls_cert:
        server.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.tls.load_cert_chain(a.tls_cert, a.tls_key)
    server.serve_forever()


if __name__ == "__main__":
    main()
