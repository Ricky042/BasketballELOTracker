import pandas as pd
import numpy as np

# ---------------------------
# Config / Hyperparameters
# ---------------------------
BASE_ELO = 1500           # league average
K_PLAYER = 30             # learning rate (larger -> faster movement)
ELO_SCALE = 400.0         # used for converting ELO -> expected distribution (classic: 400)
FOUL_PENALTY = 0.1        # subtract this * fouls from points to compute perf
WIN_BONUS_PCT = 0.15      # multiply perf by (1 + WIN_BONUS_PCT) for players on the winning team
MIN_PERF = 0.01           # floor for a player's perf so nobody gets zero or negative
VERBOSE = False           # set True for per-player debug prints

# ---------------------------
# Load data
# ---------------------------
df_games = pd.read_csv("data/full_season.csv")
df_players = pd.read_csv("data/player_stats.csv")

# ensure columns
if 'forfeit' not in df_games.columns:
    df_games['forfeit'] = False

df_games['date'] = pd.to_datetime(df_games['date'])
df_players['game_date'] = pd.to_datetime(df_players['game_date'])
df_games = df_games.sort_values(by='date')

# ---------------------------
# Helpers
# ---------------------------
def expected_distribution(elos, scale=ELO_SCALE):
    """Given list/array of elos, return vector E_i = 10^(elo/scale) / sum(...)"""
    # use 10 ** (elo/scale) (same idea as 10^(rating/400) used in multi-player expectation)
    exps = np.power(10.0, np.array(elos) / scale)
    denom = exps.sum()
    if denom == 0:
        # fallback to uniform
        return np.ones_like(exps) / len(exps)
    return exps / denom

# ---------------------------
# Initialize storage
# ---------------------------
player_elo = {}   # name -> elo
team_id_to_name = {}

for _, row in df_games.iterrows():
    team_id_to_name[row['home_team_id']] = row['home_team']
    team_id_to_name[row['away_team_id']] = row['away_team']

print("Running player-centric ELO calculation...\n")

# ---------------------------
# Main loop (per game)
# ---------------------------
for _, game in df_games.iterrows():
    if game['forfeit']:
        continue

    home_team_id = game['home_team_id']
    away_team_id = game['away_team_id']
    home_score = game.get('home_score', 0)
    away_score = game.get('away_score', 0)

    # players who played in this game (filter by date & team)
    players_in_game = df_players[
        (df_players['game_date'].dt.date == game['date'].date()) &
        (df_players['team'].isin([home_team_id, away_team_id]))
    ].copy()

    if players_in_game.empty:
        # no player rows for this game, skip
        continue

    # GROUP rows by player (in case duplicates), summing numeric stats
    agg_cols = {}
    for col in ['points', '1PM', '2PM', '3PM', 'fouls']:
        if col in players_in_game.columns:
            agg_cols[col] = 'sum'
    if agg_cols:
        players_in_game = players_in_game.groupby(['player_name', 'team'], as_index=False).agg(agg_cols)
    else:
        # at least keep unique player_name/team rows
        players_in_game = players_in_game[['player_name', 'team']].drop_duplicates()

    # compute raw performance PER PLAYER
    # NOTE: we use points primarily (don't double-count makes). Adjust if you'd rather weight makes explicitly.
    def compute_raw_perf(row):
        pts = float(row.get('points', 0.0))
        fouls = float(row.get('fouls', 0.0))
        raw = pts - FOUL_PENALTY * fouls
        # floor small or negative values
        if raw < MIN_PERF:
            raw = MIN_PERF
        return raw

    players_in_game['raw_perf'] = players_in_game.apply(compute_raw_perf, axis=1)

    # determine winner and apply win bonus (multiplicative)
    if home_score > away_score:
        winning_team_id = home_team_id
    elif away_score > home_score:
        winning_team_id = away_team_id
    else:
        winning_team_id = None

    if winning_team_id is not None and WIN_BONUS_PCT != 0:
        mask_win = players_in_game['team'] == winning_team_id
        players_in_game.loc[mask_win, 'raw_perf'] = players_in_game.loc[mask_win, 'raw_perf'] * (1.0 + WIN_BONUS_PCT)

    # ensure all raw_perf positive (after bonus)
    players_in_game['raw_perf'] = players_in_game['raw_perf'].clip(lower=MIN_PERF)

    # S_i = performance share across ALL players in the game
    total_perf = players_in_game['raw_perf'].sum()
    if total_perf <= 0:
        # fallback to uniform
        players_in_game['S'] = 1.0 / len(players_in_game)
    else:
        players_in_game['S'] = players_in_game['raw_perf'] / total_perf

    # Build E_i distribution from current player ELOs
    # ensure all players have an existing elo (initialize to BASE_ELO if new)
    for pname in players_in_game['player_name']:
        if pname not in player_elo:
            player_elo[pname] = BASE_ELO

    elos_list = [player_elo[pname] for pname in players_in_game['player_name']]
    E_dist = expected_distribution(elos_list, scale=ELO_SCALE)  # sums to 1

    # Update ELOs: Δ = K * (S - E)
    for idx, row in players_in_game.reset_index(drop=True).iterrows():
        pname = row['player_name']
        S_i = float(row['S'])
        E_i = float(E_dist[idx])
        old = player_elo.get(pname, BASE_ELO)
        delta = K_PLAYER * (S_i - E_i)
        player_elo[pname] = old + delta

        if VERBOSE:
            print(f"GAME {game['date'].date()} | {pname} | team {row['team']} | raw_perf {row['raw_perf']:.2f} | S {S_i:.3f} | E {E_i:.3f} | Δ {delta:.2f} | new {player_elo[pname]:.1f}")

# ---------------------------
# Compute team ELOs from final player ELOs
# ---------------------------
all_team_ids = pd.concat([df_games['home_team_id'], df_games['away_team_id']]).unique()
team_elo = {}
for team_id in all_team_ids:
    # players currently (or historically) assigned to team in df_players
    roster = df_players[df_players['team'] == team_id]['player_name'].unique()
    if len(roster) == 0:
        team_elo[team_id] = BASE_ELO
    else:
        team_elo[team_id] = float(np.mean([player_elo.get(pname, BASE_ELO) for pname in roster]))

# ---------------------------
# Output & Save
# ---------------------------

# Build a DataFrame with player_name, team_id, team_name, ELO
player_rows = []
for pname, elo in player_elo.items():
    trows = df_players[df_players['player_name'] == pname]
    if not trows.empty:
        team_id = trows.iloc[-1]['team']  # last team they played for
    else:
        team_id = None
    team_name = team_id_to_name.get(team_id, "Unknown")
    player_rows.append({"player_name": pname, "team_id": team_id, "team_name": team_name, "ELO": elo})

df_player_elos = pd.DataFrame(player_rows)

print("\nTop 25 player ELOs:")
top_players = df_player_elos.sort_values("ELO", ascending=False).head(25)
for _, row in top_players.iterrows():
    print(f"{row['player_name']} ({row['team_name']}): {row['ELO']:.1f}")

print("\nTeam ELOs (derived from players):")
for team_id, elo in sorted(team_elo.items(), key=lambda x: x[1], reverse=True):
    print(f"{team_id_to_name.get(team_id, team_id)} ({team_id}): {elo:.1f}")

# Save CSVs
df_player_elos.to_csv("data/player_elo.csv", index=False)
pd.DataFrame([
    {"team_id": tid, "team_name": team_id_to_name.get(tid, tid), "ELO": elo}
    for tid, elo in team_elo.items()
]).to_csv("data/team_elo.csv", index=False)

print("\nELO calculation complete. CSVs saved.")

