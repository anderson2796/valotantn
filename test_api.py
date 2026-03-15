
import requests
import json

url = "https://api.henrikdev.xyz/valorant/v2/mmr/na/Kaizen/4977"
headers = {"Authorization": "HDEV-9fa87590-5b88-4101-90ed-fe98a917f908"}

try:
    response = requests.get(url, headers=headers)
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
