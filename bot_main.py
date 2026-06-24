# bot_main.py
from telegram.ext import ApplicationBuilder, CommandHandler
from settings import BOT_TOKEN
from handlers.start_handler import start_command
from handlers.trade_handler import buy_command, sell_command

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("buy", buy_command))
app.add_handler(CommandHandler("sell", sell_command))

print("ربات روشن شد ✅")
app.run_polling()
