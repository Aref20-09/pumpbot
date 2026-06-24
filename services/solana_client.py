# services/solana_client.py
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from settings import PRIVATE_KEY, RPC_URL
import json

if not PRIVATE_KEY or not RPC_URL:
    raise ValueError("PRIVATE_KEY یا RPC_URL تنظیم نشده است.")

client = AsyncClient(RPC_URL)

secret = json.loads(PRIVATE_KEY)
wallet = Keypair.from_bytes(bytes(secret))

async def get_balance():
    balance = await client.get_balance(wallet.pubkey())
    return balance.value
