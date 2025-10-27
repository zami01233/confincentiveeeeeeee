import requests
import time
import sys
from datetime import datetime

# ================= CONFIG =================
CHAIN_CONFIGS = {
    "incentiv": {
        "id": 28802,
        "rpc": "https://rpc2.testnet.incentiv.io/"
    },
    "monad": {
        "id": 10143,
        "rpc": "https://testnet-rpc.monad.xyz/"
    }
}

def load_config(filename="akun.txt"):
    cfg = {}
    try:
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f"[ERROR] File {filename} tidak ditemukan.")
        sys.exit(1)
    return cfg

cfg = load_config()
COOKIE_HEADER = cfg.get("COOKIE_HEADER", "")
RETRY_INTERVAL_SECONDS = int(cfg.get("RETRY_INTERVAL_SECONDS", 4200))
LOOP_FOREVER = cfg.get("LOOP_FOREVER", "True").lower() == "true"

# ===========================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def build_session(cookie_header: str):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/140.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://conft.app",
        "Referer": "https://conft.app/faucets",
    })
    if cookie_header:
        s.headers.update({"Cookie": cookie_header})
    return s

def eth_get_balance(rpc_url: str, address: str):
    if not address:
        return None
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBalance",
        "params": [address, "latest"]
    }
    try:
        r = requests.post(rpc_url, json=payload, timeout=15)
        r.raise_for_status()
        j = r.json()
        if "result" in j and j["result"]:
            return int(j["result"], 16)
        return None
    except Exception as e:
        print(f"[{now()}] Error get balance: {e}")
        return None

def get_faucet_page(session: requests.Session, chain_id: int):
    url = f"https://conft.app/faucets/{chain_id}?_data=routes%2Ffaucets_.%24chainId"
    try:
        resp = session.get(url, timeout=15)
        return resp.json()
    except Exception:
        return None

def claim_faucet(session: requests.Session, chain_id: int):
    claim_url = f"https://conft.app/chains/{chain_id}/faucets/claim?_data=routes%2F_api.chains.%24chainId.faucets.claim"
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
    try:
        resp = session.post(claim_url, headers=headers, data="", timeout=20)
        try:
            result = resp.json()
        except:
            result = resp.text
        return resp.status_code, result
    except Exception as e:
        return None, str(e)

def process_chain(session, name, cfg_chain):
    chain_id = cfg_chain["id"]
    rpc_url = cfg_chain["rpc"]
    print(f"\n[{now()}] === Processing chain: {name} (ID {chain_id}) ===")
    
    page = get_faucet_page(session, chain_id)
    user_addr = None
    if page:
        user_addr = page.get("userAddress") or page.get("address") or cfg.get("WALLET_ADDRESS")
        print(f"[{now()}] userAddress from page: {user_addr}")
    else:
        user_addr = cfg.get("WALLET_ADDRESS")
        print(f"[{now()}] Failed to fetch page JSON; using WALLET_ADDRESS from config: {user_addr}")
    
    if user_addr:
        bal_before = eth_get_balance(rpc_url, user_addr)
        if bal_before is not None:
            print(f"[{now()}] Balance before claim: {bal_before} wei ({bal_before/1e18:.6f})")

    print(f"[{now()}] Sending claim POST...")
    status_code, result = claim_faucet(session, chain_id)
    print(f"[{now()}] Response status: {status_code}")
    print(f"[{now()}] Response body: {result}")

    text_result = str(result).lower()
    if isinstance(result, dict):
        if result.get("status") == "success" or "tx" in result:
            print(f"[{now()}] Claim success!")
        elif result.get("message") and "already claimed" in result.get("message").lower():
            print(f"[{now()}] Faucet already claimed (JSON).")
        else:
            print(f"[{now()}] JSON response not recognized.")
    elif "already claimed" in text_result:
        print(f"[{now()}] Faucet already claimed (text).")
    else:
        print(f"[{now()}] Unhandled response. Might retry next loop.")

    if user_addr:
        bal_after = eth_get_balance(rpc_url, user_addr)
        if bal_after is not None:
            print(f"[{now()}] Balance after claim: {bal_after} wei ({bal_after/1e18:.6f})")

# ================= MAIN LOOP =================
def main():
    print(f"[{now()}] Starting multi-chain auto-claim bot...")
    if not COOKIE_HEADER:
        print(f"[{now()}] No cookie header provided. Claims might fail if session needed.")
    
    session = build_session(COOKIE_HEADER)
    attempt = 0
    
    while True:
        attempt += 1
        print(f"\n[{now()}] --- Attempt #{attempt} ---")
        for name, chain in CHAIN_CONFIGS.items():
            process_chain(session, name, chain)
        if not LOOP_FOREVER:
            print(f"[{now()}] Done (one-shot). Exiting.")
            break
        print(f"[{now()}] Sleeping {RETRY_INTERVAL_SECONDS} seconds before next attempt...")
        time.sleep(RETRY_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
