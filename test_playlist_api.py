from curl_cffi import requests as c_requests
import json

def test():
    name = "Kaizen"
    tag = "7586"
    # New endpoint discovered: segments/playlist
    url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{name}%23{tag}/segments/playlist?playlist=competitive"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://tracker.gg/valorant/profile/riot/{name}%23{tag}/overview',
        'Origin': 'https://tracker.gg'
    }
    
    print(f"Fetching from: {url}")
    try:
        resp = c_requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            with open('tracker_lifetime.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            print("Success! Saved to tracker_lifetime.json")
            
            # Look for ANY segment with lots of kills
            segments = data.get('data', [])
            for s in segments:
                kills = s.get('stats', {}).get('kills', {}).get('value', 0)
                matches = s.get('stats', {}).get('matchesPlayed', {}).get('value', 0)
                print(f"Segment '{s.get('metadata', {}).get('name')}': {matches} games, {kills} kills")
        else:
            print(f"Failed with status {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
