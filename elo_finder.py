import pandas as pd
import numpy as np

# --- Load season data ---
df_games = pd.read_csv("data/full_season.csv")
df_players = pd.read_csv("data/player_stats.csv")

# Ensure 'forfeit' exists
if 'forfeit' not in df_games.columns:
    df_games['forfeit'] = False

# Convert dates to datetime
df_games['date'] = pd.to_datetime(df_games['date'])
df_players['game_date'] = pd.to_datetime(df_players['game_date'])

# Sort games chronologically
df_games = df_games.sort_values(by='date')

# --- Initialize ELOs ---
BASE_ELO = 1500
K_TEAM = 20
K_PLAYER = 15
FOUL_PENALTY = 0.05  # almost negligible
SMOOTHING_C = 5      # for dynamic K scaling

team_elo = {}
player_elo = {}
player_games = {}

# Map team_id to team name
team_id_to_name = {}
for _, row in df_games.iterrows():
    team_id_to_name[row['home_team_id']] = row['home_team']
    team_id_to_name[row['away_team_id']] = row['away_team']

# Helper: expected score
def expected_score(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a)/400))

print("Calculating team and player ELOs...\n")

# --- Process each game ---
for _, game in df_games.iterrows():
    if game['forfeit']:
        continue

    home_team_id = game['home_team_id']
    away_team_id = game['away_team_id']
    home_score = game['home_score']
    away_score = game['away_score']

    # Initialize team ELOs
    for team_id in [home_team_id, away_team_id]:
        if team_id not in team_elo:
            team_elo[team_id] = BASE_ELO

    R_home = team_elo[home_team_id]
    R_away = team_elo[away_team_id]

    # Expected scores
    E_home = expected_score(R_home, R_away)
    E_away = expected_score(R_away, R_home)

    # Actual scores
    if home_score > away_score:
        S_home, S_away = 1, 0
    elif home_score < away_score:
        S_home, S_away = 0, 1
    else:
        S_home, S_away = 0.5, 0.5

    # Update team ELO
    team_elo[home_team_id] += K_TEAM * (S_home - E_home)
    team_elo[away_team_id] += K_TEAM * (S_away - E_away)

    # --- Filter player stats for this game ---
    players_in_game = df_players[
        (df_players['game_date'].dt.date == game['date'].date()) &
        (df_players['team'].isin([home_team_id, away_team_id]))
    ]

    # --- Update player ELOs ---
    for _, player in players_in_game.iterrows():
        pname = player['player_name']
        team_id = player['team']
        opponent_team_id = away_team_id if team_id == home_team_id else home_team_id

        # Performance metric
        perf = player['1PM'] + player['2PM']*2 + player['3PM']*3 - FOUL_PENALTY*player['fouls']

        # Initialize player ELO and game count
        if pname not in player_elo:
            player_elo[pname] = BASE_ELO
            player_games[pname] = 0
        player_games[pname] += 1

        # Normalize vs teammates
        team_perf_total = players_in_game[players_in_game['team']==team_id].apply(
            lambda x: x['1PM'] + x['2PM']*2 + x['3PM']*3 - FOUL_PENALTY*x['fouls'], axis=1
        ).sum()
        if team_perf_total == 0:
            team_perf_total = 1

        S_player = perf / team_perf_total
        E_player = expected_score(player_elo[pname], team_elo[opponent_team_id])

        # Dynamic K scaling
        effective_K = K_PLAYER * (player_games[pname] / (player_games[pname] + SMOOTHING_C))

        # Update ELO
        player_elo[pname] += effective_K * (S_player - E_player)

# --- Output final ELOs ---
print("\nFinal team ELOs:")
for team_id, elo in sorted(team_elo.items(), key=lambda x: x[1], reverse=True):
    print(f"{team_id_to_name[team_id]} ({team_id}): {elo:.1f}")

print("\nTop 20 player ELOs:")
top_players = sorted(player_elo.items(), key=lambda x: x[1], reverse=True)[:20]
for pname, elo in top_players:
    team_id = df_players[df_players['player_name']==pname].iloc[-1]['team']
    print(f"{pname} ({team_id_to_name[team_id]}): {elo:.1f}")

# --- Save CSVs ---
pd.DataFrame([
    {"team_id": tid, "team_name": team_id_to_name[tid], "ELO": elo} for tid, elo in team_elo.items()
]).to_csv("data/team_elo.csv", index=False)

pd.DataFrame([
    {"player_name": pname,
     "team_name": team_id_to_name[df_players[df_players['player_name']==pname].iloc[-1]['team']],
     "ELO": elo} for pname, elo in player_elo.items()
]).to_csv("data/player_elo.csv", index=False)

print("\nELO calculation complete. CSVs saved.")
