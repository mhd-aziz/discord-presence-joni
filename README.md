# discord-presence-joni

Shows Hermes as active on the Discord profile `joni` and keeps one status
message updated in a private channel — fully automatic, no manual step.

## Why it is split across two machines

Rich Presence can only be set from the machine running the Discord **desktop
client** logged in as `joni` (local IPC, `SET_ACTIVITY` over
`\\.\pipe\discord-ipc-{n}`). There is no server-side API for pushing presence
to a profile. So:

- `.12` (Windows laptop, Discord client) **must** run the companion.
- `.19` (headless homelab) cannot set presence; it only serves health.
- `.19` also runs the channel status bot, which keeps working while `.12` is off.

## Components

```
.12 (Windows, Discord client "joni")
  companion.py --IPC--> Discord client --> profile
        |  polls over Tailscale
        v
.19 (homelab)
  bridge.py  :1919   Hermes health, bound to Tailscale + localhost
  bot.py             edits one message in a private channel
```

| Path | Runs on | Purpose |
| --- | --- | --- |
| `bridge/bridge.py` | .19 | stdlib HTTP server exposing Hermes health on `127.0.0.1:1919` and the Tailscale IP |
| `bot/bot.py` | .19 | posts and edits a status message in a private Discord channel |
| `companion/companion.py` | .12 | sets Rich Presence through the local Discord client |

## Deploy: bridge and bot (.19)

Both run as **systemd user units** (not `/etc/systemd/system`); the installed
copies live in `~/.config/systemd/user/`. Edit those, then reload and restart.
The templates in `deploy/systemd/` use absolute paths — adjust them to the
checkout location before copying.

```bash
python3 bridge/bridge.py                 # stdlib only, no venv
curl http://127.0.0.1:1919/              # {"ok": true, "backend_online": true, ...}

cd bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt
sudo install -m 600 -o "$USER" -g "$USER" /dev/null /etc/joni/secrets.env
#   JONI_BOT_TOKEN=<bot token>
#   JONI_BOT_CHANNEL=<private channel id>

cp deploy/systemd/joni-status-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now joni-status-bridge joni-status-bot
journalctl --user -u joni-status-bot -f
```

Invite the bot to the private server with the OAuth2 URL generator (scope
`bot`, permission `Send Messages`).

## Deploy: companion (.12, Windows)

```powershell
cd companion
pip install -r requirements.txt
$env:JONI_DRY_RUN="1"; python companion.py   # print only, no Discord connection
```

For unattended start, register a Scheduled Task that launches the interpreter
with `companion.py` (see `deploy/windows/launch.bat`). The task must run as the
Windows user logged into the Discord desktop client.

Two machine facts the companion depends on:

- The bridge is reached over Tailscale, **never** through the system proxy —
  `.12` runs a proxy for Camofox that would break the request.
- `large_image="joni"` must exist as an Art Asset in the Discord Developer
  Portal, otherwise `update` fails.

## Presence rendering

Discord decides which field is emphasized:

| Field | Where it shows |
| --- | --- |
| Application Name (Developer Portal) | small grey line under the username, with the activity icon |
| `details` / `state` from `update()` | the bold line in the Friends "Active Now" card |
| `large_image` | card thumbnail |

This companion sends assets only, so the card shows the application name alone.

## Configuration

All settings are `JONI_*` environment variables with defaults hardcoded at the
top of each script. No config file parser. No secrets in the repository —
`*.env` is gitignored; see `companion/config.env.example` for the companion's
variables.

## CI

`.github/workflows/ci.yml` runs on every push and pull request:

- **lint** — `ruff check` over `bridge/`, `bot/`, `companion/`
- **smoke** — bridge started on a spare port and its JSON asserted, companion run
  with `JONI_DRY_RUN=1`, `bot/bot.py` imported without a token
- **audit** — `pip-audit` against both requirements files

CI needs no repository secrets.
