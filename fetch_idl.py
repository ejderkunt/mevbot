import asyncio
import json
from solana.rpc.api import Client
from solana.publickey import PublicKey
from solana_program_idls import program_idls

# --- Configuration ---
# Your Helius RPC endpoint (provided by you)
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=cd59e7df-1e1e-4275-b64a-6f0f5ee78fce"

# Meteora v2 DAMM Program ID (Mainnet-beta)
METEORA_DAMM_V2_PROGRAM_ID_STR = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"

# Output file name for the IDL
OUTPUT_IDL_FILE = "damm_v2_idl.json"

async def fetch_and_save_idl():
    print(f"Connecting to RPC: {RPC_URL}")
    client = Client(RPC_URL)
    program_id = PublicKey(METEORA_DAMM_V2_PROGRAM_ID_STR)

    try:
        print(f"Attempting to fetch IDL for program: {METEORA_DAMM_V2_PROGRAM_ID_STR} from chain...")
        # Fetch the IDL from the deployed program
        idl = await program_idls.fetch_idl(client, program_id)

        if idl:
            # Convert the fetched IDL object to a JSON dictionary
            idl_json = idl.to_json()
            
            with open(OUTPUT_IDL_FILE, 'w') as f:
                json.dump(idl_json, f, indent=2) # indent=2 for pretty printing
            print(f"Successfully fetched IDL and saved to {OUTPUT_IDL_FILE}")
        else:
            print(f"Failed to fetch IDL for {METEORA_DAMM_V2_PROGRAM_ID_STR}.")
            print("This could mean the IDL is not stored on-chain for this program, or there's a connectivity issue.")
    except Exception as e:
        print(f"An error occurred while fetching or saving the IDL: {e}")
        # For more detailed debugging, you could uncomment the line below:
        # import traceback
        # traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fetch_and_save_idl())
