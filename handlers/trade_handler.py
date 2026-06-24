# handlers/trade_handler.py
from telegram import Update
from telegram.ext import ContextTypes
from services.trade_service import buy_token, sell_token

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()

    if len(args) < 3:
        return await update.message.reply_text("فرمت درست:\n/buy آدرس مقدار")

    address = args[1]
    amount = float(args[2])

    tx_sig = await buy_token(address, amount)
    await update.message.reply_text(f"خرید انجام شد ✅\nTX: {tx_sig}")

async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()

    if len(args) < 3:
        return await update.message.reply_text("فرمت درست:\n/sell آدرس مقدار")

    address = args[1]
    amount = float(args[2])

    tx_sig = await sell_token(address, amount)
    await update.message.reply_text(f"فروش انجام شد ✅\nTX: {tx_sig}")
