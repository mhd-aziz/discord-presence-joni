#!/usr/bin/env python3
"""Health bridge that re-exposes Hermes localhost health over Tailscale.

Hermes on .19 binds 127.0.0.1 only, so the companion on .12 cannot probe it.
Consumers: companion via http://100.82.26.92:1919/, bot via localhost.
Env: JONI_BRIDGE_HOST (comma separated), JONI_BRIDGE_PORT, JONI_BRIDGE_TIMEOUT.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BIND_PORT = int(os.environ.get("JONI_BRIDGE_PORT", "1919"))
BIND_HOSTS = [
    host.strip()
    for host in os.environ.get("JONI_BRIDGE_HOST", "127.0.0.1,100.82.26.92").split(",")
    if host.strip()
]
CHECK_TIMEOUT = float(os.environ.get("JONI_BRIDGE_TIMEOUT", "3"))
CHECKS = [("hermes_api", "http://127.0.0.1:9119/api/health")]

BOUND = set()
BOUND_LOCK = threading.Lock()


def probe(url, timeout=CHECK_TIMEOUT):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as response:
            return {"ok": True, "status": response.status}
    except urllib.error.HTTPError as e:
        return {"ok": e.code < 500, "status": e.code}
    except Exception as e:
        return {"ok": False, "status": None, "error": str(e)[:120]}


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = 1


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        results = {name: probe(url) for name, url in CHECKS}
        body = {
            "ok": True,
            "backend_online": results.get("hermes_api", {}).get("ok", False),
            "checks": results,
            # Report sockets that really bound: echoing config here would claim
            # both hosts while only one is listening.
            "listening_on": sorted(BOUND),
        }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def serve(host):
    # Retry forever: the Tailscale IP may appear ~100s after boot, so any fixed
    # retry budget loses the race and leaves the socket closed for good.
    delay, attempt = 3, 0
    while True:
        try:
            server = ReusableThreadingHTTPServer((host, BIND_PORT), Handler)
        except OSError as e:
            attempt += 1
            if attempt == 1 or attempt % 20 == 0:
                print(f"[bridge] bind {host}:{BIND_PORT} failed ({e}); retry in {delay}s (attempt {attempt})")
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        with BOUND_LOCK:
            BOUND.add(host)
        print(f"[bridge] listening on {host}:{BIND_PORT}")
        server.serve_forever()
        return


if __name__ == "__main__":
    threads = []
    # Start every bind thread first: joining inside this loop blocks on the
    # first host (127.0.0.1) and never starts the Tailscale listener.
    for host in BIND_HOSTS:
        thread = threading.Thread(target=serve, args=(host,), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"[bridge] starting listener on {host}:{BIND_PORT}")
    for thread in threads:
        thread.join()
