import requests
import json

def test_tracker():
    # Target: Kaizen#7586
    # URL encoded: Kaizen%237586
    url = "https://api.tracker.gg/api/v2/valorant/standard/profile/riot/Kaizen%237586"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://tracker.gg/valorant/profile/riot/Kaizen%237586/overview',
        'Origin': 'https://tracker.gg'
    }

    print(f"Testing access to {url}...")
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            # print keys to see what we got
            print("Keys:", data.keys())
            if 'data' in data:
                stats = data['data'].get('segments', [])
                print(f"Found {len(stats)} segments.")
                # Look for "competitive" "all"
                for seg in stats:
                    if seg.get('type') == 'playlist' and seg.get('metadata', {}).get('name') == 'Competitive':
                        print("Found Competitive Stats!")
                        print(seg.get('stats', {}).keys())
                        return
            print("Data fetching successful but structure needs parsing.")
        else:
            print("Failed to fetch.")
            print(resp.text[:500])
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_tracker()
