import os
import requests
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", timeout=10)
data = resp.json()

seen = set()
for update in data.get("result", []):
    for key in ("message", "channel_post", "my_chat_member"):
        msg = update.get(key, {})
        chat = msg.get("chat", {})
        cid = chat.get("id")
        title = chat.get("title", "")
        ctype = chat.get("type", "")
        if cid and cid not in seen:
            seen.add(cid)
            print(f"[{ctype}] {title}: {cid}")
