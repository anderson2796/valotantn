from curl_cffi import requests as c_requests
import json

def test_fetch(name, tag, segment_type, agent_id=None):
    url = f"https://api.tracker.gg/api/v2/valorant/standard/profile/riot/{name}%23{tag}/segments/{segment_type}?playlist=competitive"
    if agent_id:
        url += f"&agent={agent_id}"
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://tracker.gg/valorant/profile/riot/{name}%23{tag}/overview',
        'Origin': 'https://tracker.gg'
    }
    print(f"Fetching {segment_type} (agent={agent_id}) for {name}#{tag}...")
    resp = c_requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        print(f"SUCCESS! Received {len(data.get('data', []))} segments.")
        if data.get('data'):
            top_map = data['data'][0]
            print(f"Top map for this agent: {top_map.get('metadata', {}).get('name')} ({top_map.get('stats', {}).get('matchesWinPct', {}).get('displayValue')})")
    else:
        print(f"FAILED: {resp.status_code}")

if __name__ == "__main__":
    # Test agent segment (gets all agents)
    # Reyna ID (found from common knowledge or other segments)
    reyna_id = "a3e5252d-4b76-ad54-a939-ef8bb2228836"
    test_fetch("Kaizen", "7586", "map", agent_id=reyna_id)
