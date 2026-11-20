#!/usr/bin/env python3
"""Posts and edits one status message in a private Discord channel.

Reads the bridge over HTTP, so it keeps reporting while the machine running the
companion is off. Required env: JONI_BOT_TOKEN, JONI_BOT_CHANNEL,
JONI_BRIDGE_URL. Optional: JONI_BOT_POLL, JONI_BOT_RETRY_MAX.
"""
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

import discord

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
REQUIRED = ["JONI_BOT_TOKEN", "JONI_BOT_CHANNEL", "JONI_BRIDGE_URL"]

client = None
poll_task = None


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


def backend_online():
    try:
        with urllib.request.urlopen(env("JONI_BRIDGE_URL"), timeout=5) as response:
            return bool(json.load(response).get("backend_online"))
    except Exception:
        return False


async def poll_loop():
    channel = client.get_channel(int(env("JONI_BOT_CHANNEL")))
    if not channel:
        print("[bot] channel not found; check JONI_BOT_CHANNEL")
        return
    message = None
    async for candidate in channel.history(limit=20):
        if candidate.author == client.user:
            message = candidate
            break
    print(f"[bot] ready, posting to #{channel.name}")
    while not client.is_closed():
        online = backend_online()
        text = (
            "**assistant**\n"
            f"Status: {'🟢 ONLINE' if online else '🔴 OFFLINE'}\n"
            f"Last check: {time.strftime('%H:%M:%S %d/%m')}"
        )
        try:
            if message:
                await message.edit(content=text)
            else:
                message = await channel.send(text)
        except Exception as e:
            print(f"[bot] send/edit failed: {e}")
        await asyncio.sleep(int(env("JONI_BOT_POLL", "60")))


def build_client():
    global client, poll_task
    poll_task = None
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        # on_ready fires again on every gateway reconnect: start the poll loop once.
        global poll_task
        if poll_task is None or poll_task.done():
            poll_task = asyncio.create_task(poll_loop())

    return client


def main():
    load_env_file(ENV_FILE)
    require(REQUIRED)
    # A Client cannot be re-run after its session closes, so retry with a fresh one.
    delay = 5
    retry_max = float(env("JONI_BOT_RETRY_MAX", "300"))
    while True:
        build_client()
        try:
            client.run(env("JONI_BOT_TOKEN"))
            return
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(f"[bot] run failed ({type(e).__name__}: {str(e)[:160]}); retry in {int(delay)}s")
            time.sleep(delay)
            delay = min(delay * 2, retry_max)


if __name__ == "__main__":
    main()
