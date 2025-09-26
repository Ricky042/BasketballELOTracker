import pandas as pd
import math

# -----------------------
# Config
# -----------------------
K = 32                # Elo factor, can tune later
START_ELO = 1200      # Default starting Elo

# -----------------------
# Load data
# -----------------------
games = pd.read_csv("data/full_season.csv")
players = pd.read_csv("data/player_stats.csv")

# Parse dates to ensure chronological updates
games["date"] = pd.to_datetime(games["date"], errors="coerce")
players["game_date"] = pd.to_datetime(players["game_date"], errors="coerce")

# -----------------------
# Elo store
# -----------------------
player_elos = {}

def get_player_elo(pid):
    return player_elos.get(pid, START_ELO)

def set_player_elo(pid, new_elo):
    player_elos[pid] = new_elo

# -----------------------
# Elo update function
# -----------------------
def update_player_elo(player_id, player_points, team_points, team_elo, opp_elo, team_result):
    # Expected team result
    expected = 1 / (1 + 10 ** ((opp_elo - team_elo) / 400))
    
    # Share of team scoring
    perf_share = player_points / max(1, team_points)
    
    # Defense factor
    defense_factor = opp_elo / 1200  # 1200 = league avg baseline
    
    # Log scaling (diminishing returns)
    perf_factor = math.log(1 + player_points) * defense_factor
    
    # Elo delta
    delta = K * (team_result - expected) * perf_share * perf_factor
    
    old_elo = get_player_elo(player_id)
    new_elo = old_elo + delta
    
    set_player_elo(player_id, new_elo)
    return delta

# -----------------------
# Process all games in order
# -----------------------
games = games.sort_values("date")

for _, game in games.iterrows():
    if game["forfeit"]:
        continue  # skip forfeits

    home_id = game["home_team_id"]
    away_id = game["away_team_id"]
    home_score = game["home_score"]
    away_score = game["away_score"]

    # Get all players from this game
    home_players = players[(players["team"] == home_id) & (players["game_date"] == game["date"])]
    away_players = players[(players["team"] == away_id) & (players["game_date"] == game["date"])]

    if home_players.empty or away_players.empty:
        continue

    # Compute team Elos as avg of players
    home_elo = home_players["player_id"].apply(get_player_elo).mean()
    away_elo = away_players["player_id"].apply(get_player_elo).mean()

    # Results
    if home_score > away_score:
        home_result, away_result = 1, 0
    elif away_score > home_score:
        home_result, away_result = 0, 1
    else:
        home_result, away_result = 0.5, 0.5  # handle ties

    # Update all players
    for _, row in home_players.iterrows():
        update_player_elo(row["player_id"], row["points"], home_score, home_elo, away_elo, home_result)

    for _, row in away_players.iterrows():
        update_player_elo(row["player_id"], row["points"], away_score, away_elo, home_elo, away_result)

# -----------------------
# Save results
# -----------------------
final_elos = pd.DataFrame([
    {"player_id": pid, "final_elo": elo}
    for pid, elo in player_elos.items()
])

# Join player names for readability
final_elos = final_elos.merge(players[["player_id", "player_name"]].drop_duplicates(), on="player_id", how="left")

final_elos.to_csv("data/final_player_elos.csv", index=False)
print("Elo calculation complete! Saved to data/final_player_elos.csv")
