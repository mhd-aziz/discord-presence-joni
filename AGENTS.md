# AGENTS.md

Repo guide for `discord-presence-joni`. Three small standalone Python 3 scripts:
no framework, no build step. Stdlib plus three small dependencies.

## Layout

- `bridge/bridge.py` — stdlib HTTP server exposing backend health on the hosts
  listed in `JONI_BRIDGE_HOST`, probing `http://127.0.0.1:9119/api/health`.
- `bot/bot.py` — discord.py client that edits one status message in a private
  channel. venv: `bot/venv/` (Python 3.14). When `client.run()` fails it retries
  in-process with backoff and a fresh client per attempt (the same instance
  cannot be run twice).
- `companion/companion.py` — sets Rich Presence over IPC to the Discord desktop
  client running on the same machine. pypresence + psutil + requests.
- `deploy/systemd/*.service` — user-unit templates; replace the placeholder
  checkout path before copying.
- `deploy/windows/launch.bat` — manual Windows launcher, reads `.env` then starts
  `pythonw.exe companion.py`.
- `.github/workflows/ci.yml` — lint, smoke, dependency audit.

## Commands

Bridge (stdlib only, no venv):

```bash
JONI_BRIDGE_HOST=127.0.0.1 JONI_BRIDGE_PORT=1919 python3 bridge/bridge.py
curl http://127.0.0.1:1919/        # {"ok": true, "backend_online": true, ...}
```

Bot:

```bash
cd bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env               # fill JONI_BOT_TOKEN, JONI_BOT_CHANNEL, JONI_BRIDGE_URL
venv/bin/python bot.py
```

Companion (Windows):

```powershell
cd companion
copy .env.example .env             # fill JONI_CLIENT_ID, JONI_BRIDGE_URL
pip install -r requirements.txt
python companion.py                # JONI_DRY_RUN=1 prints without connecting
```

Deploy systemd — the active units are **user units**, not the copies in
`/etc/systemd/system/` (those are unused):

```bash
systemctl --user daemon-reload
systemctl --user restart joni-status-bridge joni-status-bot
journalctl --user -u joni-status-bot -f
```

Lint/test: `ruff check --line-length 110 --select E,F,W,I bridge bot companion`.
CI also smoke-tests the bridge (curl plus JSON assertions), the companion
dry-run, and that every script exits with `[config] missing required env` when
its required variables are absent. Local verification is a manual run plus
`curl http://127.0.0.1:1919/`, or `JONI_DRY_RUN=1` for the companion.

## Conventions

- No hardcoded configuration. Each script loads `JONI_*` variables from the
  environment and, if present, from `.env` next to the script — exported values
  win, blank values count as unset. Variables without a default are required and
  verified by `require()` with a `[config] missing required env: ...` message.
- Every script runs standalone: `if __name__ == "__main__":`.
- Logging is `print()` with a `[config]` / `[bridge]` / `[bot]` / `[joni]` /
  `[dry]` prefix. No `logging`.
- Error handling is broad `except Exception` with `return False` / reconnect
  loops — deliberate, so a brief Discord or backend outage does not kill the
  service. Do not convert to `raise`.
- Comments explain what bit us before, not what the code does. Keep them, and
  keep them short.
- Code, comments, docs, filenames and Discord-facing text are English.
- `.env.example` files carry empty values only: they are templates for other
  users, never a place for real configuration.

## Pitfalls

- **`.gitignore` blocks every `*.env` / `.env` / `.env.*`** — only
  `.env.example` is tracked (explicit `!` negation). Never commit a secret and
  never weaken this rule.
- **Bridge and companion force `proxies={"http": None, "https": None}`** — a
  system proxy on the companion host would corrupt requests to the bridge. Do
  not remove those arguments.
- **The bridge binds an address that may not exist at boot** (private network
  interface coming up) — hence the infinite 3s to 30s bind retry. Do not replace
  it with a fixed retry budget.
- **Presence needs the Discord desktop client on the same machine as the
  companion**; the bridge and bot cannot push presence.
- **The `large_image` asset key must match an Art Asset in the Discord portal**
  or `update` fails.
- Dependency upgrades: `pip install --upgrade` does not bump transitive
  dependencies on its own — use `--upgrade-strategy eager`.
