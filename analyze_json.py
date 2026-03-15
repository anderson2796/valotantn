import json

try:
    with open(r'c:\Users\Anderson\Desktop\Valorant html\backend\tracker_response.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('data', {}).get('segments', [])
    print(f"Total segments: {len(segments)}")

    for i, seg in enumerate(segments):
        t = seg.get('type')
        attrs = seg.get('attributes', {})
        meta = seg.get('metadata', {})
        name = meta.get('name')
        
        # Only print interesting ones (playlist, overview, or competitive related)
        # or just print all types briefly
        if t in ['playlist', 'overview']:
            print(f"[{i}] Type: {t}, Attrs: {attrs}, Name: {name}")
        elif 'competitive' in str(name).lower() or 'competitive' in str(attrs).lower():
             print(f"[{i}] Type: {t}, Attrs: {attrs}, Name: {name}")

except Exception as e:
    print(f"Error: {e}")
