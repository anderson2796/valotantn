import requests
import json

def test_profile():
    url = "http://localhost:5000/api/profile/KAIZEN/7586"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            print(f"Name: {data.get('name')}#{data.get('tag')}")
            print(f"Agents count: {len(data.get('agents', []))}")
            if data.get('agents'):
                print("First agent:", data['agents'][0])
            else:
                print("AGENTS LIST IS EMPTY")
        else:
            print(f"Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    test_profile()
