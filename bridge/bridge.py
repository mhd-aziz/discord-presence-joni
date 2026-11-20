#!/usr/bin/env python3
"""Health bridge that re-exposes Hermes localhost health over Tailscale.

Hermes binds 127.0.0.1 only, so a companion on another machine cannot probe it.
Required env: JONI_BRIDGE_HOST (comma separated), JONI_BRIDGE_PORT.
Optional: JONI_BRIDGE_TIMEOUT.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
REQUIRED = ["JONI_BRIDGE_HOST", "JONI_BRIDGE_PORT"]
CHECKS = [("hermes_api", "http://127.0.0.1:9119/api/health")]

BIND_PORT = None
BIND_HOSTS = []
CHECK_TIMEOUT = None

BOUND = set()
BOUND_LOCK = threading.Lock()


def load_env_file(path):
    # Fills os.environ from .env without overriding exported values, so systemd
    # EnvironmentFile wins. Blank values count as unset.
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        if value:
            os.environ.setdefault(key.strip(), value)


def env(name, default=None):
    return os.environ.get(name) or default


def require(names):
    missing = [name for name in names if not env(name)]
    if missing:
        print(f"[config] missing required env: {', '.join(missing)}")
        raise SystemExit(1)


def probe(url, timeout=None):
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method="GET"), timeout=timeout or CHECK_TIMEOUT
        ) as response:
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
    load_env_file(ENV_FILE)
    require(REQUIRED)
    BIND_PORT = int(env("JONI_BRIDGE_PORT"))
    BIND_HOSTS = [host.strip() for host in env("JONI_BRIDGE_HOST").split(",") if host.strip()]
    CHECK_TIMEOUT = float(env("JONI_BRIDGE_TIMEOUT", "3"))
    threads = []
    # Start every bind thread first: joining inside this loop blocks on the
    # first host and never starts the remaining listeners.
    for host in BIND_HOSTS:
        thread = threading.Thread(target=serve, args=(host,), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"[bridge] starting listener on {host}:{BIND_PORT}")
    for thread in threads:
        thread.join()
