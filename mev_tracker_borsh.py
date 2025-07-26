
import asyncio
import json
import time
import requests
from datetime import datetime, timedelta, timezone
import os
import logging
import traceback

from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.exceptions import SolanaRpcException

import websockets

from borsh_construct import CStruct, U64, U8
from construct import Bytes

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("mev_tracker.log"), 
                        logging.StreamHandler()
                    ])
logging.getLogger("httpx").setLevel(logging.WARNING)

# --- Configuration ---
HELIUS_API_API_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_API_API_KEY:
    logging.error("HELIUS_API_KEY environment variable not set.")
    exit("Exiting: HELIUS_API_KEY environment variable not set.") 

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key=cd59e7df-1e1e-4275-b64a-6f0f5ee78fce"
WS_URL = f"wss://mainnet.helius-rpc.com/?api-key=cd59e7df-1e1e-4275-b64a-6f0f5ee78fce"

METEORA_DAMM_V2_PROGRAM_ID = Pubkey.from_string("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG")

active_pools = {}

CP_MM_LAYOUT = CStruct(
    "is_initialized" / U8,
    "token_x_mint" / Bytes(32),
    "token_y_mint" / Bytes(32),
    "token_x_vault" / Bytes(32),
    "token_y_vault" / Bytes(32),
    "lp_mint" / Bytes(32),
    "token_x_decimals" / U8,
    "token_y_decimals" / U8,
    "amp_factor" / U64,
    "fees_owner" / Bytes(32),
    "fees_mint" / Bytes(32),
    "fees_vault" / Bytes(32),
    "fees_bps" / U64,
    "last_amp_update_ts" / U64,
    "last_lp_mint_ts" / U64,
    "bump" / U8
)

async def parse_cp_mm_account(client: AsyncClient, pool_address: Pubkey) -> dict:
    resp = await client.get_account_info(pool_address)
    if not resp.value or not resp.value.data:
        raise ValueError(f"Could not fetch account data for {pool_address}")

    raw_data = bytes(resp.value.data[0])
    parsed = CP_MM_LAYOUT.parse(raw_data)
    return {
        "token_x_mint": Pubkey.from_bytes(parsed.token_x_mint),
        "token_y_mint": Pubkey.from_bytes(parsed.token_y_mint),
        "token_x_vault": Pubkey.from_bytes(parsed.token_x_vault),
        "token_y_vault": Pubkey.from_bytes(parsed.token_y_vault),
    }

# Add your existing get_jupiter_price, get_pool_tvl, fetch_transaction_with_retry, cleanup_old_pools_task, and main logic here
# replacing the AnchorPy fetch logic with parse_cp_mm_account()
