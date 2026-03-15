import requests
import json

API_KEY = "f100b7fc-52cf-4347-b8c2-87a4a6078baf"
BASE_URL = "https://public-api.tracker.gg/v2/valorant/standard/profile"

def test_api(name, tag):
    platform = "riot"
    identity = f"{name}%23{tag}"
    url = f"{BASE_URL}/{platform}/{identity}"
    
    headers = {
        "TRN-Api-Key": API_KEY,
        "Accept": "application/json"
    }
    
    print(f"Testing URL: {url}")
    response = requests.get(url, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        with open("tracker_response_sample.json", "w") as f:
            json.dump(data, f, indent=4)
        print("Success! Response saved to tracker_response_sample.json")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    # Testing with a sample account
    test_api("Kaizen", "4977")
