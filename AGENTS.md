# AGENTS.md

Repo guide for `discord-presence-joni`. Three small standalone Python 3 scripts:
no framework, no build step. Stdlib plus three small dependencies.

## Layout

- `bridge/bridge.py` — runs on .19 (homelab). stdlib HTTP server on port 1919,
  binds `127.0.0.1` plus the Tailscale IP, probes `http://127.0.0.1:9119/api/health`.
- `bot/bot.py` — runs on .19. discord.py client that edits one status message in a
  private channel, polling the bridge every 60s. venv: `bot/venv/` (Python 3.14).
  When `client.run()` fails it retries in-process with backoff and a fresh client
  per attempt (the same instance cannot be run twice).
- `companion/companion.py` — runs on .12 (Windows). Sets Rich Presence over IPC to
  the Discord desktop client logged in as `joni`. pypresence + psutil + requests.
  Log: `C:\Users\muham\joni-companion\companion.log`.
- `deploy/systemd/*.service` — user-unit templates, absolute paths to this checkout.
- `deploy/windows/launch.bat` — launcher used by the Windows Scheduled Task.
- `.github/workflows/ci.yml` — lint, smoke, dependency audit.

## Commands

Bridge (stdlib only, no venv):

```bash
python3 bridge/bridge.py
curl http://127.0.0.1:1919/        # {"backend_online": true, ...}
```

Bot (.19):

```bash
cd bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python bot.py             # needs JONI_BOT_TOKEN + JONI_BOT_CHANNEL
```

Companion (.12 / Windows):

```powershell
cd companion
pip install -r requirements.txt
$env:JONI_DRY_RUN="1"; python companion.py   # dry-run: print, no Discord connect
```

Deploy systemd (.19) — the active units are **user units**, not the copies in
`/etc/systemd/system/` (those are unused):

```bash
systemctl --user daemon-reload
systemctl --user restart joni-status-bridge joni-status-bot
journalctl --user -u joni-status-bot -f
```

Lint/test: `ruff check bridge bot companion`; CI also smoke-tests the bridge
(`curl` plus JSON assertions) and the companion dry-run. Local verification is a
manual run plus `curl http://127.0.0.1:1919/`, or `JONI_DRY_RUN=1` for the
companion.

## Conventions

- All configuration via `JONI_*` environment variables, defaults hardcoded at
  module top level. No config file parser.
- Every script runs standalone: `if __name__ == "__main__":`.
- Logging is `print()` with a `[bridge]` / `[bot]` / `[joni]` / `[dry]` prefix.
  No `logging`.
- Error handling is broad `except Exception` with `return False` / reconnect
  loops — deliberate, so a brief Discord or Hermes outage does not kill the
  service. Do not convert to `raise`.
- Comments explain what bit us before, not what the code does. Keep them, and
  keep them short.
- Code, comments, docs, filenames and Discord-facing text are English.

## Pitfalls

- **`.gitignore` blocks every `*.env`** — `companion/config.env` and
  `bot/bot.env` are never committed. Never commit a secret and never weaken
  this rule.
- **Bridge and companion force `proxies={"http": None, "https": None}`** — .12
  runs a system proxy (Camofox) that corrupts requests to the Tailscale IP. Do
  not remove those arguments.
- **The bridge binds a Tailscale IP that may not exist at boot** — hence the
  infinite 3s to 30s bind retry. Do not replace it with a fixed retry budget.
- **Presence needs the Discord desktop client logged in as `joni` on .12**;
  bridge and bot on .19 cannot push presence.
- **`large_image="joni"` must match an Art Asset in the Discord portal** or
  `update` fails.
- `companion/config.env.example` documents `JONI_DISCORD_PROC`, the variable the
  code actually reads.
- Dependency upgrades: `pip install --upgrade` does not bump transitive
  dependencies on its own — use `--upgrade-strategy eager`.
