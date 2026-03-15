# Valorant Stats Backend

This Python Flask server fetches accurate career statistics from Tracker.gg and exposes them via localhost API.

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the server**:
   ```bash
   python server.py
   ```

3. **Server will start on**: `http://localhost:5000`

## Endpoints

### GET `/api/profile/<name>/<tag>`
Fetches complete career statistics for a single account.

Example: `http://localhost:5000/api/profile/Kaizen/4977`

### POST `/api/aggregate`
Aggregates stats from multiple accounts.

Body:
```json
{
  "accounts": [
    {"name": "Player1", "tag": "1234", "account_level": 100},
    {"name": "Player2", "tag": "5678", "account_level": 200}
  ]
}
```

## Notes

- The server uses the Tracker.gg API with the configured API key
- All requests are made server-side, bypassing CORS restrictions
- Career statistics include wins, kills, deaths, K/D, win rate, and more
