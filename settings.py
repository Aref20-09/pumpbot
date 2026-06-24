# settings.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("RPC_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN تنظیم نشده است.")
