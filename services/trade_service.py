# services/trade_service.py
from services.solana_client import client, wallet
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solana.rpc.types import TxOpts
from solders.pubkey import Pubkey

async def buy_token(to_address: str, amount: float):
    to_pubkey = Pubkey.from_string(to_address)

    tx = Transaction().add(
        transfer(
            TransferParams(
                from_pubkey=wallet.pubkey(),
                to_pubkey=to_pubkey,
                lamports=int(amount)
            )
        )
    )

    result = await client.send_transaction(tx, wallet, opts=TxOpts(skip_preflight=True))
    return result.value

async def sell_token(to_address: str, amount: float):
    # فعلاً مثل buy، بعداً می‌تونی لاجیک فروش واقعی اضافه کنی
    return await buy_token(to_address, amount)
