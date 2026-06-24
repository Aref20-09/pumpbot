"""
ربات تلگرامی مانیتورینگ و معامله‌ی شبیه‌سازی‌شده (Paper Trading) برای توکن‌های Pump.fun
نسخه 1 - فقط حالت شبیه‌سازی (بدون اتصال به کیف پول واقعی)
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("pump_bot")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"

STATE_FILE = "paper_state.json"

MIN_SCORE_TO_BUY = 6.0
VIRTUAL_BUY_AMOUNT_SOL = 0.1
TAKE_PROFIT_PCT = 100.0
STOP_LOSS_PCT = -40.0
MAX_OPEN_POSITIONS = 5


@dataclass
class Position:
    mint: str
    symbol: str
    entry_price: float
    amount_sol: float
    opened_at: float
    current_price: float = 0.0

    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class PaperState:
    virtual_balance_sol: float = 5.0
    open_positions: dict = field(default_factory=dict)
    closed_trades: list = field(default_factory=list)
    watch_count: int = 0

    def to_json(self):
        return {
            "virtual_balance_sol": self.virtual_balance_sol,
            "open_positions": {
                k: {
                    "mint": p.mint, "symbol": p.symbol, "entry_price": p.entry_price,
                    "amount_sol": p.amount_sol, "opened_at": p.opened_at,
                    "current_price": p.current_price,
                } for k, p in self.open_positions.items()
            },
            "closed_trades": self.closed_trades,
            "watch_count": self.watch_count,
        }

    @classmethod
    def from_json(cls, data):
        st = cls(
            virtual_balance_sol=data.get("virtual_balance_sol", 5.0),
            closed_trades=data.get("closed_trades", []),
            watch_count=data.get("watch_count", 0),
        )
        for k, p in data.get("open_positions", {}).items():
            st.open_positions[k] = Position(**p)
        return st


def load_state() -> PaperState:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return PaperState.from_json(json.load(f))
        except Exception as e:
            logger.warning(f"could not load state: {e}")
    return PaperState()


def save_state(state: PaperState):
    with open(STATE_FILE, "w") as f:
        json.dump(state.to_json(), f, indent=2)


state = load_state()
state_lock = asyncio.Lock()


def score_token(token_data: dict) -> float:
    score = 0.0

    initial_liquidity = token_data.get("initial_buy_sol", 0) or 0
    if initial_liquidity > 5:
        score += 2
    elif initial_liquidity > 1:
        score += 1

    symbol = (token_data.get("symbol") or "").strip()
    if 2 <= len(symbol) <= 10:
        score += 1

    vol_growth = token_data.get("volume_growth_1m", 0) or 0
    if vol_growth > 50:
        score += 3
    elif vol_growth > 10:
        score += 1.5

    unique_buyers = token_data.get("unique_buyers", 0) or 0
    if unique_buyers > 20:
        score += 2
    elif unique_buyers > 5:
        score += 1

    return round(score, 2)


async def maybe_open_position(token_data: dict, score: float):
    async with state_lock:
        mint = token_data.get("mint")
        if not mint or mint in state.open_positions:
            return
        if len(state.open_positions) >= MAX_OPEN_POSITIONS:
            return
        if state.virtual_balance_sol < VIRTUAL_BUY_AMOUNT_SOL:
            return

        price = token_data.get("price_sol", 0) or 0
        if price <= 0:
            return

        pos = Position(
            mint=mint,
            symbol=token_data.get("symbol", "?"),
            entry_price=price,
            amount_sol=VIRTUAL_BUY_AMOUNT_SOL,
            opened_at=time.time(),
            current_price=price,
        )
        state.open_positions[mint] = pos
        state.virtual_balance_sol -= VIRTUAL_BUY_AMOUNT_SOL
        save_state(state)
        logger.info(f"[PAPER BUY] {pos.symbol} ({mint}) @ {price} | score={score}")


async def update_position_price(mint: str, new_price: float):
    async with state_lock:
        pos = state.open_positions.get(mint)
        if not pos:
            return
        pos.current_price = new_price
        pnl = pos.pnl_pct()

        should_close = False
        reason = ""
        if pnl >= TAKE_PROFIT_PCT:
            should_close = True
            reason = "take_profit"
        elif pnl <= STOP_LOSS_PCT:
            should_close = True
            reason = "stop_loss"

        if should_close:
            proceeds = pos.amount_sol * (1 + pnl / 100)
            state.virtual_balance_sol += proceeds
            state.closed_trades.append({
                "symbol": pos.symbol, "mint": pos.mint,
                "entry_price": pos.entry_price, "exit_price": new_price,
                "pnl_pct": round(pnl, 2), "reason": reason,
                "closed_at": time.time(),
            })
            del state.open_positions[mint]
            logger.info(f"[PAPER SELL] {pos.symbol} pnl={pnl:.1f}% reason={reason}")

        save_state(state)


async def pumpportal_listener():
    while True:
        try:
            async with websockets.connect(PUMPPORTAL_WS_URL) as ws:
                logger.info("به PumpPortal وصل شد")
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": []}))

                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("txType") or msg.get("type")

                    if msg_type == "create":
                        score = score_token(msg)
                        async with state_lock:
                            state.watch_count += 1
                        if score >= MIN_SCORE_TO_BUY:
                            await maybe_open_position(msg, score)

                    elif msg_type in ("buy", "sell"):
                        mint = msg.get("mint")
                        price = msg.get("price_sol") or msg.get("price")
                        if mint and price:
                            await update_position_price(mint, float(price))

        except Exception as e:
            logger.warning(f"اتصال وب‌سوکت قطع شد، تلاش دوباره در 5 ثانیه: {e}")
            await asyncio.sleep(5)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من ربات مانیتورینگ پامپ‌فان هستم (حالت فعلی: شبیه‌سازی / Paper Trading).\n\n"
        "دستورات:\n"
        "/status - وضعیت کلی و موجودی شبیه‌سازی\n"
        "/positions - پوزیشن‌های باز فعلی\n"
        "/history - آخرین معاملات بسته‌شده\n"
        "/help - راهنما"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with state_lock:
        open_count = len(state.open_positions)
        balance = state.virtual_balance_sol
        watched = state.watch_count
        closed = len(state.closed_trades)
    await update.message.reply_text(
        f"موجودی شبیه‌سازی: {balance:.3f} SOL\n"
        f"پوزیشن باز: {open_count}\n"
        f"معاملات بسته‌شده: {closed}\n"
        f"توکن‌های بررسی‌شده: {watched}\n\n"
        f"حالت: PAPER TRADING (بدون پول واقعی)"
    )


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with state_lock:
        if not state.open_positions:
            await update.message.reply_text("هیچ پوزیشن بازی نیست.")
            return
        lines = []
        for pos in state.open_positions.values():
            lines.append(
                f"{pos.symbol}: ورود {pos.entry_price:.6f} | "
                f"فعلی {pos.current_price:.6f} | سود/ضرر {pos.pnl_pct():.1f}%"
            )
    await update.message.reply_text("\n".join(lines))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with state_lock:
        recent = state.closed_trades[-10:]
    if not recent:
        await update.message.reply_text("هنوز معامله‌ای بسته نشده.")
        return
    lines = [
        f"{t['symbol']}: {t['pnl_pct']:.1f}% ({t['reason']})"
        for t in recent
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def post_init(application: Application):
    asyncio.create_task(pumpportal_listener())


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده.\n"
            "اجرا کن: export TELEGRAM_BOT_TOKEN='توکن_تو'"
        )

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
