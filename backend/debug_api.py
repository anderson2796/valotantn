import requests
import json

HENRIK_API_URL = 'https://api.henrikdev.xyz/valorant'
API_KEY = 'HDEV-9fa87590-5b88-4101-90ed-fe98a917f908'

def check_account(name, tag, region='latam'):
    url = f"{HENRIK_API_URL}/v2/mmr/{region}/{name}/{tag}"
    headers = {'Authorization': API_KEY}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get('data', {})
        print(f"Current Rank: {data.get('current_data', {}).get('currenttierpatched')}")
        highest = data.get('highest_rank', {})
        print(f"Peak Rank: {highest.get('patched_tier')} (Tier: {highest.get('tier')})")
        
        # Check competitive tiers content
        content_url = f"{HENRIK_API_URL}/v1/content"
        content_resp = requests.get(content_url, headers=headers)
        if content_resp.status_code == 200:
            tiers = content_resp.json().get('competitiveTiers', [])
            if tiers:
                print(f"Latest Tiers UUID: {tiers[-1].get('uuid')}")
    else:
        print(f"Failed: {resp.status_code}")

if __name__ == "__main__":
    # Test with a known account if possible, or just print structure
    print("Checking structure...")
    check_account('Anderson', '123') # Placeholder
