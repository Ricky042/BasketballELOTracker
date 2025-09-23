import pandas as pd

# Load the season data
df = pd.read_csv("data/full_season.csv")

# Make sure 'forfeit' exists
if 'forfeit' not in df.columns:
    df['forfeit'] = False

# Initialize ELO ratings
BASE_ELO = 1500
K = 20  # Adjust K-factor as needed
elo_ratings = {}

# Sort by date so ELOs are updated chronologically
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by='date')

print("Calculating ELOs...\n")

for idx, row in df.iterrows():
    if row['forfeit']:
        continue  # Skip forfeited games

    home = row['home_team']
    away = row['away_team']
    home_score = row['home_score']
    away_score = row['away_score']

    # Initialize ELOs if team not yet seen
    for team in [home, away]:
        if team not in elo_ratings:
            elo_ratings[team] = BASE_ELO

    R_home = elo_ratings[home]
    R_away = elo_ratings[away]

    # Expected scores
    E_home = 1 / (1 + 10 ** ((R_away - R_home) / 400))
    E_away = 1 / (1 + 10 ** ((R_home - R_away) / 400))

    # Actual scores
    if home_score > away_score:
        S_home, S_away = 1, 0
    elif home_score < away_score:
        S_home, S_away = 0, 1
    else:
        S_home, S_away = 0.5, 0.5

    # Update ratings
    R_home_new = R_home + K * (S_home - E_home)
    R_away_new = R_away + K * (S_away - E_away)

    # Save updated ratings
    elo_ratings[home] = R_home_new
    elo_ratings[away] = R_away_new

    print(f"Game: {home} ({home_score}) vs {away} ({away_score})")
    print(f"  ELO change: {home}: {R_home:.1f} -> {R_home_new:.1f}, {away}: {R_away:.1f} -> {R_away_new:.1f}\n")

# Final standings
print("Final ELO ratings at end of season:")
for team, rating in sorted(elo_ratings.items(), key=lambda x: x[1], reverse=True):
    print(f"{team}: {rating:.1f}")
