import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from server import get_tracker_data, parse_tracker_data

def test():
    name = "Kaizen"
    tag = "4977"
    print(f"Testing Tracker.gg for {name}#{tag}...")
    s_data = get_tracker_data(name, tag)
    if s_data:
        print("Raw data fetched.")
        p_data = parse_tracker_data(s_data, name, tag)
        if p_data:
            print(f"Parsed Stats: {p_data.get('stats')}")
        else:
            print("Parsing failed.")
    else:
        print("Fetch failed.")

if __name__ == "__main__":
    test()
