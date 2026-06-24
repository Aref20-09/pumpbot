# handlers/start_handler.py
from telegram import Update
from telegram.ext import ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n"
        "ربات ترید پایتونی فعاله.\n"
        "دستورات:\n"
        "/buy آدرس مقدار\n"
        "/sell آدرس مقدار"
    )
