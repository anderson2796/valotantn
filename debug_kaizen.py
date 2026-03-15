import requests
import json

# Config
API_KEY = 'HDEV-9fa87590-5b88-4101-90ed-fe98a917f908'
BASE_URL = 'https://api.henrikdev.xyz/valorant'
HEADERS = {
    'Authorization': API_KEY,
    'User-Agent': 'DebugScript/1.0'
}

def fetch(endpoint):
    url = f"{BASE_URL}{endpoint}"
    print(f"GET {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        print(f"Status: {resp.status_code}")
        return resp.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

def run_debug():
    name = "Kaizen"
    tag = "7586"
    
    print(f"--- Debugging {name}#{tag} ---")
    
    # 1. Account Details (Region, Level)
    print("\n1. Fetching Account Details...")
    acc = fetch(f"/v1/account/{name}/{tag}")
    if not acc or 'data' not in acc:
        print("Failed to get account info.")
        return
    
    data = acc['data']
    region = data.get('region')
    level = data.get('account_level')
    puuid = data.get('puuid')
    print(f"Region: {region}")
    print(f"Level: {level}")
    print(f"PUUID: {puuid}")
    
    # 2. Fetch Matches (Batch 1)
    print("\n2. Fetching recent competitive matches (size=100)...")
    matches_resp = fetch(f"/v3/matches/{region}/{name}/{tag}?mode=competitive&size=100")
    if matches_resp and 'data' in matches_resp:
        matches = matches_resp['data']
        print(f"Count: {len(matches)}")
        if len(matches) > 0:
            print(f"Newest Match: {matches[0]['metadata']['cluster']} - {matches[0]['metadata']['game_start_patched']}")
            print(f"Oldest Match: {matches[-1]['metadata']['cluster']} - {matches[-1]['metadata']['game_start_patched']}")
    else:
        print("Failed to fetch matches.")

    # 3. Test MMR History (Does this contain stats?)
    print("\n3. Fetching MMR History...")
    mmr_hist = fetch(f"/v1/mmr-history/{region}/{name}/{tag}")
    if mmr_hist and 'data' in mmr_hist:
        print(f"MMR History Count: {len(mmr_hist['data'])}")
    
    # 4. Check 'Lifetime' Matches Endpoint via POST (Unofficial V2)
    # Some older endpoints might exist.
    # But usually V3 is best. 
    # Is there a lifetime stats endpoint?
    # /v1/by-puuid/lifetime/matches... No.
    
    print("\n--- End Debug ---")

if __name__ == "__main__":
    run_debug()
