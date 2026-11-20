# discord-presence-joni

Shows the agent as active on a Discord profile and keeps one status message
updated in a private channel — automatic, no manual step.

## Why it is split across two machines

Rich Presence can only be set from the machine running the Discord **desktop
client** of the account you want to decorate (local IPC, `SET_ACTIVITY` over
`\\.\pipe\discord-ipc-{n}`). There is no server-side API for pushing presence
to a profile. So:

- the machine with the Discord client **must** run the companion;
- a headless machine cannot set presence; it only serves health;
- the same headless machine can run the channel status bot, which keeps working
  while the companion host is off.

## Components

```
host A (Discord client desktop)
  companion.py --IPC--> Discord client --> profile
        |  polls over the private network
        v
host B (headless)
  bridge.py          health endpoint the companion reads
  bot.py             edits one message in a private channel
```

| Path | Purpose |
| --- | --- |
| `bridge/bridge.py` | stdlib HTTP server exposing backend health on the configured hosts |
| `bot/bot.py` | posts and edits a status message in a private Discord channel |
| `companion/companion.py` | sets Rich Presence through the local Discord client |

## Configuration

Every script reads `JONI_*` environment variables and has **no hardcoded
values**: variables without a default are required, and the script exits with
`[config] missing required env: ...` when one is absent. Each component ships a
`.env.example` with empty values — copy it to `.env` next to the script and fill
it in, or export the variables (exported values win over the file). Blank values
count as unset, so an untouched copy is harmless.

`*.env` and `.env` are gitignored; a `.env` holding a bot token must never be
committed.

| Component | Required | Optional (default in script) |
| --- | --- | --- |
| `bridge` | `JONI_BRIDGE_HOST`, `JONI_BRIDGE_PORT` | `JONI_BRIDGE_TIMEOUT` |
| `bot` | `JONI_BOT_TOKEN`, `JONI_BOT_CHANNEL`, `JONI_BRIDGE_URL` | `JONI_BOT_POLL`, `JONI_BOT_RETRY_MAX` |
| `companion` | `JONI_CLIENT_ID`, `JONI_BRIDGE_URL` | `JONI_POLL`, `JONI_TIMEOUT`, `JONI_DISCORD_PROC`, `JONI_CLEAR_AFTER`, `JONI_LOG`, `JONI_DRY_RUN` |

`JONI_BRIDGE_HOST` is a comma separated list of addresses the bridge binds, for
example `127.0.0.1,<private-ip>` — localhost plus the address the companion host
can reach. `JONI_CLIENT_ID` is the Application ID from the Developer Portal
(public, not a secret).

## Deploy: bridge and bot

Both run as **systemd user units** (not `/etc/systemd/system`); the installed
copies live in `~/.config/systemd/user/`. Copy the templates from
`deploy/systemd/`, replace `/path/to/discord-presence-joni` with the real
checkout path, then reload and restart.

```bash
# bridge (stdlib only, no venv needed)
sudo install -m 600 -o "$USER" -g "$USER" /dev/null /etc/joni/bridge.env
#   JONI_BRIDGE_HOST=127.0.0.1,<private-ip>
#   JONI_BRIDGE_PORT=1919
python3 bridge/bridge.py                 # or let the unit run it
curl http://127.0.0.1:1919/              # {"ok": true, "backend_online": true, ...}

# bot
cd bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt
sudo install -m 600 -o "$USER" -g "$USER" /dev/null /etc/joni/secrets.env
#   JONI_BOT_TOKEN=<bot token>
sudo install -m 600 -o "$USER" -g "$USER" /dev/null /etc/joni/bot.env
#   JONI_BOT_CHANNEL=<private channel id>
#   JONI_BRIDGE_URL=http://127.0.0.1:1919/

cp deploy/systemd/joni-status-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now joni-status-bridge joni-status-bot
journalctl --user -u joni-status-bot -f
```

Invite the bot to the private server with the OAuth2 URL generator (scope
`bot`, permission `Send Messages`).

## Deploy: companion (Windows)

```powershell
cd companion
copy .env.example .env      # then fill JONI_CLIENT_ID and JONI_BRIDGE_URL
pip install -r requirements.txt
python companion.py         # or deploy/windows/launch.bat
```

Set `JONI_DRY_RUN=1` to print the computed activity without connecting to
Discord. For unattended start, register a Scheduled Task that runs
`pythonw.exe -u companion.py` (or `launch.bat`) as the user logged into the
Discord desktop client.

Two facts the companion depends on:

- the bridge is reached directly over the private network, **never** through a
  system proxy, which would break the request;
- the `large_image` asset key must exist as an Art Asset in the Developer Portal,
  otherwise `update` fails.

## Presence rendering

Discord decides which field is emphasized:

| Field | Where it shows |
| --- | --- |
| Application Name (Developer Portal) | small grey line under the username, with the activity icon |
| `details` / `state` from `update()` | the bold line in the Friends "Active Now" card |
| `large_image` | card thumbnail |

This companion sends assets only, so the card shows the application name alone.

## CI

`.github/workflows/ci.yml` runs on every push and pull request:

- **lint** — `ruff check` over `bridge/`, `bot/`, `companion/`
- **smoke** — bridge started on a spare port with its JSON asserted, companion
  run with `JONI_DRY_RUN=1`, `bot/bot.py` imported without a token, and each
  script checked to fail fast when required variables are missing
- **audit** — `pip-audit` against both requirements files

CI needs no repository secrets.
