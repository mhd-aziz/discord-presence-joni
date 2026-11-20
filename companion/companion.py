#!/usr/bin/env python3
"""Discord Rich Presence companion, runs on .12 (Windows) via pythonw.exe.

Connects to the local Discord client over IPC and keeps presence alive while
Discord is open, reconnecting when the client restarts. Env: JONI_CLIENT_ID,
JONI_BRIDGE_URL, JONI_POLL, JONI_TIMEOUT, JONI_DISCORD_PROC, JONI_CLEAR_AFTER,
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

CLIENT_ID = os.environ.get("JONI_CLIENT_ID", "1530105931482791956")
BRIDGE_URL = os.environ.get("JONI_BRIDGE_URL", "http://100.82.26.92:1919/")
POLL = int(os.environ.get("JONI_POLL", "10"))
TIMEOUT = int(os.environ.get("JONI_TIMEOUT", "4"))
DISCORD_PROCS = [
    name.strip()
    for name in os.environ.get("JONI_DISCORD_PROC", "Discord,discord").split(",")
    if name.strip()
]
CLEAR_AFTER = int(os.environ.get("JONI_CLEAR_AFTER", "3"))
DRY_RUN = os.environ.get("JONI_DRY_RUN", "0") == "1"
DEFAULT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "companion.log")
LOG_PATH = os.environ.get("JONI_LOG", DEFAULT_LOG)

log_file = None


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
        # The bridge lives on a private Tailscale IP: .12 runs a system proxy
        # (Camofox) that would break the request, so force no proxy.
        response = requests.get(BRIDGE_URL, timeout=TIMEOUT, proxies={"http": None, "https": None})
        return bool(response.json().get("backend_online"))
    except Exception:
        return False


def connect_rpc():
    rpc = Presence(CLIENT_ID)
    rpc.connect()
    return rpc


def main():
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
