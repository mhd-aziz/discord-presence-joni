#!/usr/bin/env python3
"""Discord Rich Presence companion, runs on the machine with the Discord client.

Connects to the local Discord client over IPC and keeps presence alive while
Discord is open, reconnecting when the client restarts.
Required env: JONI_CLIENT_ID, JONI_BRIDGE_URL.
Optional: JONI_POLL, JONI_TIMEOUT, JONI_DISCORD_PROC, JONI_CLEAR_AFTER,
JONI_LOG, JONI_DRY_RUN.
"""
import os
import sys
import time

try:
    from pypresence import Presence
except ImportError:
    print("Missing dependency: pip install -r requirements.txt")
    sys.exit(1)

try:
    import psutil
except ImportError:
    psutil = None

import requests

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
REQUIRED = ["JONI_CLIENT_ID", "JONI_BRIDGE_URL"]

CLIENT_ID = None
BRIDGE_URL = None
POLL = 10
TIMEOUT = 4
DISCORD_PROCS = []
CLEAR_AFTER = 3
DRY_RUN = False
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "companion.log")

log_file = None


def load_env_file(path):
    # Fills os.environ from .env without overriding exported values. Blank
    # values count as unset, so a stub .env.example copy is harmless.
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


def load_config():
    global CLIENT_ID, BRIDGE_URL, POLL, TIMEOUT, DISCORD_PROCS, CLEAR_AFTER, DRY_RUN, LOG_PATH
    CLIENT_ID = env("JONI_CLIENT_ID")
    BRIDGE_URL = env("JONI_BRIDGE_URL")
    POLL = int(env("JONI_POLL", "10"))
    TIMEOUT = int(env("JONI_TIMEOUT", "4"))
    DISCORD_PROCS = [
        name.strip() for name in env("JONI_DISCORD_PROC", "Discord,discord").split(",") if name.strip()
    ]
    CLEAR_AFTER = int(env("JONI_CLEAR_AFTER", "3"))
    DRY_RUN = env("JONI_DRY_RUN", "0") == "1"
    LOG_PATH = env("JONI_LOG", LOG_PATH)


def log(message):
    # pythonw has no stdout, so the file log is what makes failures diagnosable.
    global log_file
    if log_file is None:
        try:
            log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")
        except Exception:
            log_file = False
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    if log_file:
        try:
            log_file.write(line + "\n")
        except Exception:
            pass


def process_running(name_substrings):
    if psutil is None:
        return True
    for process in psutil.process_iter(["name"]):
        try:
            name = process.info.get("name") or ""
            if any(s.lower() in name.lower() for s in name_substrings):
                return True
        except Exception:
            pass
    return False


def discord_running():
    return process_running(DISCORD_PROCS)


def backend_online():
    try:
        # The bridge is reached directly over the private network: a system proxy
        # on this machine would break the request, so force no proxy.
        response = requests.get(BRIDGE_URL, timeout=TIMEOUT, proxies={"http": None, "https": None})
        return bool(response.json().get("backend_online"))
    except Exception:
        return False


def connect_rpc():
    rpc = Presence(CLIENT_ID)
    rpc.connect()
    return rpc


def main():
    load_env_file(ENV_FILE)
    require(REQUIRED)
    load_config()
    log(f"[joni] companion start client={CLIENT_ID} bridge={BRIDGE_URL} dry={DRY_RUN}")
    rpc = None
    offline_streak = 0
    try:
        while True:
            active = backend_online()

            if DRY_RUN:
                log(f"[dry] discord={discord_running()} backend={active} -> presence='joni' (no details)")
                time.sleep(POLL)
                continue

            # Discord closed: drop IPC so the next loop reconnects cleanly
            # instead of holding a dead pipe.
            if not discord_running():
                if rpc is not None:
                    try:
                        rpc.close()
                    except Exception:
                        pass
                    rpc = None
                time.sleep(POLL)
                continue

            if rpc is None:
                try:
                    rpc = connect_rpc()
                    log("[joni] connected to local Discord")
                except Exception as e:
                    log(f"[joni] connect failed ({e}); retrying next loop")
                    time.sleep(POLL)
                    continue

            if active:
                if offline_streak:
                    log(f"[joni] backend online again after {offline_streak} offline poll(s)")
                offline_streak = 0
                try:
                    # Assets only: Discord then shows the application name alone.
                    rpc.update(large_image="joni")
                except Exception as e:
                    log(f"[joni] update failed ({e}); reconnecting")
                    try:
                        rpc.close()
                    except Exception:
                        pass
                    rpc = None
            else:
                # Keep presence through short backend blips; clear only after
                # CLEAR_AFTER consecutive offline polls.
                offline_streak += 1
                if offline_streak == 1:
                    log(f"[joni] backend offline; keeping presence ({offline_streak}/{CLEAR_AFTER})")
                if offline_streak >= CLEAR_AFTER:
                    log(f"[joni] backend offline x{offline_streak}; clearing presence")
                    try:
                        rpc.clear()
                    except Exception:
                        pass

            time.sleep(POLL)
    except KeyboardInterrupt:
        pass
    finally:
        if rpc and not DRY_RUN:
            try:
                rpc.clear()
            except Exception:
                pass
            try:
                rpc.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
