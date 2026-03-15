import requests
import json

# Test API endpoints to understand data structure
API_KEY = "HDEV-9fa87590-5b88-4101-90ed-fe98a917f908"
BASE_URL = "https://api.henrikdev.xyz/valorant"

headers = {"Authorization": API_KEY}

# Test account
name = "Kaizen"
tag = "4977"
region = "na"

print("=" * 80)
print("TESTING MMR ENDPOINT - All Competitive Seasons")
print("=" * 80)

try:
    # Get MMR data
    mmr_url = f"{BASE_URL}/v2/mmr/{region}/{name}/{tag}"
    mmr_response = requests.get(mmr_url, headers=headers)
    mmr_data = mmr_response.json()
    
    if mmr_data.get('status') == 200:
        data = mmr_data['data']
        print(f"\nCurrent Rank: {data.get('current_data', {}).get('currenttierpatched', 'N/A')}")
        print(f"\nSeasons available: {len(data.get('by_season', {}))}")
        
        total_wins = 0
        total_games = 0
        
        print("\nPer Season Breakdown:")
        print("-" * 80)
        for season_id, season_data in data.get('by_season', {}).items():
            wins = season_data.get('wins', 0)
            games = season_data.get('number_of_games', 0)
            rank = season_data.get('final_rank_patched', 'Unranked')
            
            total_wins += wins
            total_games += games
            
            print(f"Season: {season_id}")
            print(f"  Rank: {rank}")
            print(f"  Wins: {wins}")
            print(f"  Games: {games}")
            print(f"  Win Rate: {(wins/games*100 if games > 0 else 0):.1f}%")
            print()
        
        print("=" * 80)
        print(f"TOTAL ACROSS ALL SEASONS:")
        print(f"  Total Wins: {total_wins}")
        print(f"  Total Games: {total_games}")
        print(f"  Overall Win Rate: {(total_wins/total_games*100 if total_games > 0 else 0):.1f}%")
        print("=" * 80)
        
except Exception as e:
    print(f"Error with MMR endpoint: {e}")

print("\n\n")
print("=" * 80)
print("TESTING MATCHES ENDPOINT - Competitive Only")
print("=" * 80)

try:
    # Get match data
    matches_url = f"{BASE_URL}/v3/matches/{region}/{name}/{tag}?filter=competitive"
    matches_response = requests.get(matches_url, headers=headers)
    matches_data = matches_response.json()
    
    if matches_data.get('status') == 200:
        matches = matches_data['data']
        print(f"\nTotal competitive matches returned: {len(matches)}")
        
        # Aggregate stats
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_score = 0
        total_damage = 0
        total_rounds = 0
        total_headshots = 0
        total_bodyshots = 0
        total_legshots = 0
        
        # Find player PUUID first
        if len(matches) > 0:
            first_match = matches[0]
            for player in first_match['players']['all_players']:
                if player['name'].lower() == name.lower() and player['tag'].lower() == tag.lower():
                    puuid = player['puuid']
                    print(f"Player PUUID: {puuid}")
                    break
        
        for match in matches:
            # Find player in match
            player_stats = None
            for player in match['players']['all_players']:
                if player['puuid'] == puuid:
                    player_stats = player
                    break
            
            if player_stats:
                stats = player_stats['stats']
                total_kills += stats.get('kills', 0)
                total_deaths += stats.get('deaths', 0)
                total_assists += stats.get('assists', 0)
                total_score += stats.get('score', 0)
                total_damage += stats.get('damage', {}).get('made', 0)
                total_rounds += match['metadata'].get('rounds_played', 0)
                total_headshots += stats.get('headshots', 0)
                total_bodyshots += stats.get('bodyshots', 0)
                total_legshots += stats.get('legshots', 0)
        
        print("\n" + "=" * 80)
        print("AGGREGATED STATS FROM RECENT COMPETITIVE MATCHES:")
        print("=" * 80)
        print(f"Kills: {total_kills:,}")
        print(f"Deaths: {total_deaths:,}")
        print(f"Assists: {total_assists:,}")
        print(f"K/D Ratio: {(total_kills/total_deaths if total_deaths > 0 else 0):.2f}")
        print(f"KAD Ratio: {((total_kills+total_assists)/total_deaths if total_deaths > 0 else 0):.2f}")
        print(f"\nScore: {total_score:,}")
        print(f"Damage: {total_damage:,}")
        print(f"Rounds: {total_rounds:,}")
        print(f"\nADR: {(total_damage/total_rounds if total_rounds > 0 else 0):.1f}")
        print(f"ACS: {(total_score/total_rounds if total_rounds > 0 else 0):.1f}")
        print(f"Kills/Round: {(total_kills/total_rounds if total_rounds > 0 else 0):.2f}")
        print(f"\nHeadshots: {total_headshots:,}")
        print(f"Bodyshots: {total_bodyshots:,}")
        print(f"Legshots: {total_legshots:,}")
        total_shots = total_headshots + total_bodyshots + total_legshots
        print(f"Total Shots: {total_shots:,}")
        print(f"Headshot %: {(total_headshots/total_shots*100 if total_shots > 0 else 0):.1f}%")
        print("=" * 80)
        
        print(f"\nNOTE: This endpoint returns only the most recent matches (usually ~20-50)")
        print(f"For complete historical data, we need to use the lifetime endpoint or aggregate from seasons")
        
except Exception as e:
    print(f"Error with matches endpoint: {e}")
