import asyncio
import json
import time
import requests
from datetime import datetime, timedelta, timezone

from solana.rpc.api import Client
# We will use the generic 'websockets' library directly, so no need for SolanaWsClient import
# from solana.rpc.websocket_api import SolanaWsClient, logs_subscribe # REMOVE THIS LINE
from solana.publickey import PublicKey
from solana.exceptions import SolanaRpcException

# Import the direct websockets library
import websockets

# For decoding Anchor program logs and instructions (requires 'anchorpy')
# pip install anchorpy
from anchorpy import Program, Provider, Idl

# --- Configuration ---
# Your Helius RPC and WebSocket endpoints
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=cd59e7df-1e1e-4275-b64a-6f0f5ee78fce"
WS_URL = "wss://mainnet.helius-rpc.com/?api-key=cd59e7df-1e1e-4275-b64a-6f0f5ee78fce"


# Meteora v2 DAMM Program ID (Mainnet-beta)
METEORA_DAMM_V2_PROGRAM_ID = PublicKey("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG")

# Path to Meteora v2 DAMM IDL file (you downloaded this manually)
METEORA_DAMM_V2_IDL_PATH = "damm_v2_idl.json" # Make sure this file exists in your project directory!

# List to store newly detected pools for tracking
active_pools = {} # {pool_address: {'creation_time': ..., 'metrics': {...}}}

# --- Helper Functions (will be expanded in later steps) ---

async def load_idl(file_path: str) -> Idl:
    """Loads Anchor IDL from a JSON file."""
    with open(file_path, 'r') as f:
        return Idl.from_json(json.load(f))

async def get_jupiter_price(mint_address: str) -> float | None:
    """Fetches real-time price from Jupiter Aggregator API."""
    url = f"https://price.jup.ag/v4/price?ids={mint_address}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        if data and 'data' in data and mint_address in data['data']:
            return data['data'][mint_address]['price']
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching price from Jupiter for {mint_address}: {e}")
        return None

async def get_pool_tvl(http_client: Client, pool_address: PublicKey, token_mints: dict, token_prices: dict) -> float:
    """
    Calculates pool TVL in USDT.
    This is a conceptual placeholder and will require detailed Meteora v2 pool account parsing.
    `token_mints` should be like {'token_a': PublicKey, 'token_b': PublicKey}
    `token_prices` should be like {'token_a_mint_str': price_usd, 'token_b_mint_str': price_usd}
    """
    try:
        # Placeholder balances (you will replace this with actual on-chain fetches)
        token_a_amount = 2000 
        token_b_amount = 3000 
        
        # Fetch actual decimals for token A and B mints
        token_a_mint_info = http_client.get_mint_info(token_mints['token_a']).value
        token_b_mint_info = http_client.get_mint_info(token_mints['token_b']).value
        
        token_a_ui_amount = token_a_amount / (10 ** token_a_mint_info.decimals)
        token_b_ui_amount = token_b_amount / (10 ** token_b_mint_info.decimals)

        token_a_price = token_prices.get(str(token_mints['token_a']), 0)
        token_b_price = token_prices.get(str(token_mints['token_b']), 0)

        tvl_usd = (token_a_ui_amount * token_a_price) + (token_b_ui_amount * token_b_price)
        return tvl_usd
    except Exception as e:
        print(f"Error calculating TVL for {pool_address}: {e}")
        return 0.0

# --- Main Listener Function ---

async def main():
    http_client = Client(RPC_URL)
    
    # Use websockets.connect directly
    try:
        async with websockets.connect(WS_URL) as websocket:
            print(f"Connected to RPC: {RPC_URL}")
            print(f"Connected to WS: {WS_URL}")

            # Load Meteora v2 DAMM IDL
            try:
                damm_v2_idl = await load_idl(METEORA_DAMM_V2_IDL_PATH)
                # Initialize an AnchorPy Program instance. This allows decoding of instructions/accounts.
                provider = Provider(http_client._provider, None) 
                damm_v2_program = Program(damm_v2_idl, METEORA_DAMM_V2_PROGRAM_ID, provider)
                print("Meteora v2 DAMM IDL loaded successfully.")
            except FileNotFoundError:
                print(f"Error: IDL file not found at {METEora_DAMM_V2_IDL_PATH}. Please ensure it's in the same directory.")
                return
            except Exception as e:
                print(f"Error loading or initializing AnchorPy Program: {e}")
                return

            # Manually send logsSubscribe JSON-RPC request
            subscribe_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [str(METEORA_DAMM_V2_PROGRAM_ID)]},
                    {"commitment": "finalized"}
                ]
            }
            await websocket.send(json.dumps(subscribe_request))
            
            # Receive subscription confirmation
            subscription_response = await websocket.recv()
            subscription_data = json.loads(subscription_response)
            if 'result' in subscription_data:
                subscription_id = subscription_data['result']
                print(f"Subscribed to logs with ID: {subscription_id}")
            else:
                print(f"Failed to subscribe to logs: {subscription_data.get('error', 'Unknown error')}")
                return # Exit if subscription fails

            print("Listening for new Meteora v2 pool creations and activities...")

            try:
                # Loop to receive and process messages
                async for message in websocket:
                    msg = json.loads(message)
                    if 'params' in msg and 'result' in msg['params'] and 'value' in msg['params']['result']:
                        log_data = msg['params']['result']['value']
                        signature = log_data['signature']
                        logs = log_data['logs']
                        slot = msg['params']['result']['context']['slot']

                        # --- Pool Creation Detection Logic ---
                        is_new_pool = False
                        new_pool_address = None
                        pool_creation_timestamp = None

                        # Check for "invoke" line by our target program
                        target_program_invoked = False
                        for log_line in logs:
                            if f"Program {METEORA_DAMM_V2_PROGRAM_ID} invoke" in log_line:
                                target_program_invoked = True
                                break

                        if target_program_invoked:
                            try:
                                # Fetch the full transaction details
                                txn_resp = http_client.get_transaction(signature, 'jsonParsed')
                                
                                if txn_resp.value is None or txn_resp.value.transaction is None:
                                    continue

                                transaction = txn_resp.value.transaction
                                block_time_unix = txn_resp.value.block_time
                                if block_time_unix:
                                    pool_creation_timestamp = datetime.fromtimestamp(block_time_unix, tz=timezone.utc)
                                    if datetime.now(timezone.utc) - pool_creation_timestamp > timedelta(hours=1):
                                        continue

                                # Iterate through instructions to find the 'createPool' instruction
                                for instruction in transaction.message.instructions:
                                    if hasattr(instruction, 'program_id') and instruction.program_id == METEORA_DAMM_V2_PROGRAM_ID:
                                        if hasattr(instruction, 'parsed') and instruction.parsed and \
                                           hasattr(instruction.parsed, 'type') and instruction.parsed.type == 'createPool': 
                                            
                                            if hasattr(instruction.parsed, 'info') and hasattr(instruction.parsed.info, 'pool'):
                                                new_pool_address = PublicKey(instruction.parsed.info.pool)
                                            elif hasattr(instruction, 'accounts') and len(instruction.accounts) > 0:
                                                new_pool_address = instruction.accounts[0] 
                                            
                                            if new_pool_address:
                                                print(f"--- POTENTIAL NEW METEORA POOL DETECTED ---")
                                                print(f"Signature: {signature}")
                                                print(f"Pool Address: {new_pool_address}")
                                                print(f"Creation Time: {pool_creation_timestamp.isoformat()}")

                                                # Placeholder: Get token mints for the new pool.
                                                token_a_mint = PublicKey("EPjFWdd5AufqSSqeM2qN1xzybapTVGEmkNqA6gsYxRWA") # Example: USDC Mainnet
                                                token_b_mint = PublicKey("So11111111111111111111111111111111111111112") # Example: SOL Mainnet

                                                # Fetch token prices
                                                prices = {
                                                    str(token_a_mint): await get_jupiter_price(str(token_a_mint)),
                                                    str(token_b_mint): await get_jupiter_price(str(token_b_mint))
                                                }

                                                # Calculate initial TVL
                                                initial_tvl = await get_pool_tvl(
                                                    http_client, 
                                                    new_pool_address, 
                                                    {'token_a': token_a_mint, 'token_b': token_b_mint}, 
                                                    prices
                                                )
                                                print(f"Initial TVL: {initial_tvl:.2f} USDT")

                                                # Filter by TVL
                                                if initial_tvl < 5000:
                                                    print(f"Added {new_pool_address} to active tracking (TVL < 5000 USDT).")
                                                    active_pools[str(new_pool_address)] = {
                                                        'creation_time': pool_creation_timestamp,
                                                        'token_a_mint': token_a_mint,
                                                        'token_b_mint': token_b_mint,
                                                        'tvl': initial_tvl,
                                                        'signature': signature,
                                                        'metrics': {} 
                                                    }
                                                    
                                                else:
                                                    print(f"Ignored {new_pool_address} (TVL >= 5000 USDT).")
                                            break 
                            except SolanaRpcException as e:
                                if "Transaction simulation failed: Blockhash not found" in str(e):
                                    pass
                                else:
                                    print(f"Error fetching/parsing transaction {signature}: {e}")
                            except Exception as e:
                                print(f"Unexpected error during transaction parsing for {signature}: {e}")
                        
                        # --- Periodically clean up old pools from active_pools ---
                        current_time_utc = datetime.now(timezone.utc)
                        pools_to_remove = []
                        for pool_addr_str, pool_data in active_pools.items():
                            if current_time_utc - pool_data['creation_time'] > timedelta(hours=1):
                                pools_to_remove.append(pool_addr_str)
                        
                        for pool_addr_str in pools_to_remove:
                            print(f"Removing old pool from tracking: {pool_addr_str}")
                            del active_pools[pool_addr_str]

                        # --- Placeholder for Dashboard Update Logic ---
                        # print(f"Currently tracking {len(active_pools)} pools.")

            except asyncio.CancelledError:
                print("Stopping WebSocket listener.")
            except Exception as e:
                print(f"An unexpected error occurred in websocket message loop: {e}")
    except websockets.exceptions.ConnectionClosedOK:
        print("WebSocket connection closed normally.")
    except Exception as e:
        print(f"An error occurred establishing or maintaining WebSocket connection: {e}")


if __name__ == "__main__":
    asyncio.run(main())
