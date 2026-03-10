"""Discord webhook notification. Best-effort, never crashes on failure."""
import os
import requests


def notify_discord(message: str, webhook_url: str = None) -> bool:
    """Send a message to Discord via webhook. Returns True on success."""
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False

    try:
        resp = requests.post(url, json={"content": message}, timeout=10)
        return resp.status_code < 300
    except Exception:
        return False
