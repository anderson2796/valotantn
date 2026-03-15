from curl_cffi import requests as c_requests
import json

def test_fetch(name, tag, segment_type):
    url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{name}%23{tag}/segments/{segment_type}?playlist=competitive"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://tracker.gg/valorant/profile/riot/{name}%23{tag}/overview',
        'Origin': 'https://tracker.gg'
    }
    print(f"Fetching {segment_type} for {name}#{tag}...")
    resp = c_requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        filename = f"test_{segment_type}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"SUCCESS! Saved to {filename}")
        # Print first agent stats for inspection
        if data.get('data'):
            first = data['data'][0]
            print(f"First {segment_type}: {first.get('metadata', {}).get('name')}")
            # print(json.dumps(first.get('stats', {}), indent=2))
    else:
        print(f"FAILED: {resp.status_code}")

if __name__ == "__main__":
    test_fetch("Kaizen", "7586", "agent")
    test_fetch("Kaizen", "7586", "map")
