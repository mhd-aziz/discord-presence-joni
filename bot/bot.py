#!/usr/bin/env python3
"""Posts and edits one status message in a private Discord channel.

Runs on .19 and reads the bridge over localhost, so it keeps reporting while
.12 is off. Env: JONI_BOT_TOKEN, JONI_BOT_CHANNEL, JONI_BRIDGE_URL,
JONI_BOT_POLL, JONI_BOT_RETRY_MAX.
"""
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

import discord

TOKEN = os.environ.get("JONI_BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("JONI_BOT_CHANNEL", "0"))
BRIDGE_URL = os.environ.get("JONI_BRIDGE_URL", "http://127.0.0.1:1919/")
POLL = int(os.environ.get("JONI_BOT_POLL", "60"))
RETRY_MAX = float(os.environ.get("JONI_BOT_RETRY_MAX", "300"))

client = None
poll_task = None


def backend_online():
    try:
        with urllib.request.urlopen(BRIDGE_URL, timeout=5) as response:
            return bool(json.load(response).get("backend_online"))
    except Exception:
        return False


async def poll_loop():
    channel = client.get_channel(CHANNEL_ID)
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
        text = ("**assistant**\n"
                f"Status: {'🟢 ONLINE' if online else '🔴 OFFLINE'}\n"
                f"Last check: {time.strftime('%H:%M:%S %d/%m')}")
        try:
            if message:
                await message.edit(content=text)
            else:
                message = await channel.send(text)
        except Exception as e:
            print(f"[bot] send/edit failed: {e}")
        await asyncio.sleep(POLL)


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
    if not (TOKEN and CHANNEL_ID):
        print("[bot] set JONI_BOT_TOKEN and JONI_BOT_CHANNEL")
        return
    # A Client cannot be re-run after its session closes, so retry with a fresh one.
    delay = 5
    while True:
        build_client()
        try:
            client.run(TOKEN)
            return
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(
                f"[bot] run failed ({type(e).__name__}: {str(e)[:160]}); retry in {int(delay)}s"
            )
            time.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)


if __name__ == "__main__":
    main()
