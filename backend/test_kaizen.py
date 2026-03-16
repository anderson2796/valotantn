import requests
import json
import os

def test_account():
    name = "Kaizen"
    tag = "7586"
    # Try to grab HENRIK_API_KEY from environment if it exists
    api_key = os.environ.get('HENRIK_API_KEY', '')
    
    url = f"https://api.henrikdev.xyz/valorant/v1/account/{name}/{tag}"
    headers = {"Authorization": api_key} if api_key else {}
    
    print(f"Testing {name}#{tag}...")
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print("Data found:")
            print(json.dumps(data, indent=2))
        else:
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_account()
