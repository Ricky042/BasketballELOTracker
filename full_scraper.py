from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import numpy as np
import time
import threading

# -----------------------
# Configuration
# -----------------------
BASE = "https://www.playhq.com"
START_PAGE = "https://www.playhq.com/basketball-victoria/org/balwyn-blazers-basketball-association-senior-competition/winter-2025/b9a20da8"

BASE_ELO = 1500
K_PLAYER = 30
ELO_SCALE = 400.0
FOUL_PENALTY = 0.1
WIN_BONUS_PCT = 0.15
MIN_PERF = 0.01
VERBOSE = False

all_games = []
all_players = []
player_elo = {}
lock = threading.Lock()

# -----------------------
# Selenium driver factory
# -----------------------
def create_driver(headless=True):
    options = Options()
    options.headless = headless
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# -----------------------
# Step 1: Collect all grades
# -----------------------
driver = create_driver(headless=True)
driver.get(START_PAGE)
time.sleep(2)

grades_info = []
grade_elements = driver.find_elements(By.CSS_SELECTOR, "a[data-testid^='grade-']")
for grade_el in grade_elements:
    try:
        grade_name = grade_el.find_element(By.TAG_NAME, "span").text.strip()
        grade_url = grade_el.get_attribute("href")
        grades_info.append((grade_name, grade_url))
    except Exception as e:
        print("Error collecting grade info:", e)

if not grades_info:
    active_grade_el = driver.find_element(By.CSS_SELECTOR, "h2 span")
    grades_info.append((active_grade_el.text.strip(), driver.current_url))

# Rank grades by order on page (assumes top = highest grade)
grades_info = sorted(grades_info, key=lambda x: grades_info.index(x))
grade_offsets = {grade_name: BASE_ELO - 25*i for i, (grade_name, _) in enumerate(grades_info)}

print(f"Detected grades and offsets: {grade_offsets}")
driver.quit()

# -----------------------
# Helper: expected distribution for multiplayer ELO
# -----------------------
def expected_distribution(elos, scale=ELO_SCALE):
    exps = np.power(10.0, np.array(elos) / scale)
    denom = exps.sum()
    if denom == 0:
        return np.ones_like(exps) / len(exps)
    return exps / denom

# -----------------------
# Main scraping & ELO update per grade
# -----------------------
def scrape_grade_and_update_elo(grade_name, grade_url):
    driver = create_driver(headless=True)
    print(f"\nScraping grade: {grade_name}")
    driver.get(grade_url)
    time.sleep(2)

    # Detect rounds
    round_elements = driver.find_elements(By.CSS_SELECTOR, "ul.sc-1odi71i-0 li a[data-testid^='page-']")
    round_urls = [el.get_attribute("href") for el in round_elements]
    round_names = [el.text.strip() for el in round_elements]

    if "R1" not in [r.split("/")[-1] for r in round_urls]:
        round_urls.insert(0, grade_url + "/R1")
        round_names.insert(0, "R1")

    print(f"Rounds detected: {round_names}")

    # -----------------------
    # Scrape fixtures
    # -----------------------
    for r_name, r_url in zip(round_names, round_urls):
        print(f"Scraping fixtures for {grade_name} - {r_name}")
        driver.get(r_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='games-on-date']"))
            )
        except:
            print(f"Timeout loading {r_url}")
            continue

        date_blocks = driver.find_elements(By.CSS_SELECTOR, "[data-testid='games-on-date']")
        for date_block in date_blocks:
            try:
                date_text = date_block.find_element(By.CSS_SELECTOR, "span").text.strip()
            except:
                date_text = "Unknown Date"

            games = date_block.find_elements(By.CSS_SELECTOR, "div.sc-1uurivg-5.iSzlTC")
            for game_div in games:
                try:
                    teams = game_div.find_elements(By.CSS_SELECTOR, "a.sc-9jw1ry-3")
                    scores = game_div.find_elements(By.CSS_SELECTOR, "span.sc-1uurivg-10")
                    fixture_btn = game_div.find_element(By.CSS_SELECTOR, "a[data-testid^='fixture-button-']")
                    box_score_link = fixture_btn.get_attribute("href")
                    if not box_score_link.startswith("http"):
                        box_score_link = BASE + box_score_link

                    home_team = teams[0].text.strip()
                    away_team = teams[1].text.strip()
                    home_team_id = teams[0].get_attribute("href").split("/")[-1]
                    away_team_id = teams[1].get_attribute("href").split("/")[-1]

                    try:
                        home_score = int(scores[0].text.strip())
                        away_score = int(scores[1].text.strip())
                        forfeit = False
                    except:
                        home_score = None
                        away_score = None
                        forfeit = True

                    game_data = {
                        "grade": grade_name,
                        "round": r_name,
                        "date": date_text,
                        "home_team": home_team,
                        "home_team_id": home_team_id,
                        "away_team": away_team,
                        "away_team_id": away_team_id,
                        "home_score": home_score,
                        "away_score": away_score,
                        "forfeit": forfeit,
                        "box_score_link": box_score_link
                    }

                    with lock:
                        all_games.append(game_data)
                except Exception as e:
                    print("Error parsing game:", e)

    # -----------------------
    # Scrape players and update ELO
    # -----------------------
    for game in list(all_games):
        if game['grade'] != grade_name:
            continue

        print(f"\nScraping players for game: {game['home_team']} vs {game['away_team']} ({game['round']})")
        driver.get(game['box_score_link'])
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

        # Click advanced stats if exists
        try:
            adv_button = driver.find_element(By.XPATH, "//button[.//span[text()='Show advanced stats']]")
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", adv_button)
                adv_button.click()
                time.sleep(1)
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", adv_button)
                time.sleep(1)
        except:
            pass

        tables = driver.find_elements(By.CSS_SELECTOR, "table[data-testid^='stats-']")
        for table in tables:
            team_id = table.get_attribute("data-testid").replace("stats-", "")
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 6:
                        continue
                    jersey = cells[0].text.strip()
                    player_a_tag = cells[1].find_element(By.TAG_NAME, "a")
                    player_name = player_a_tag.text.strip()
                    player_id = player_a_tag.get_attribute("href").split("/")[-2]

                    points = int(cells[2].text.strip() or 0)
                    one_pm = int(cells[3].text.strip() or 0)
                    two_pm = int(cells[4].text.strip() or 0)
                    three_pm = int(cells[5].text.strip() or 0)
                    fouls = int(cells[6].text.strip() or 0) if len(cells) > 6 else 0

                    raw_perf = max(points - FOUL_PENALTY * fouls, MIN_PERF)

                    player_data = {
                        "grade": grade_name,
                        "game_date": game['date'],
                        "round": game['round'],
                        "team": team_id,
                        "player_id": player_id,
                        "player_name": player_name,
                        "jersey": jersey,
                        "points": points,
                        "1PM": one_pm,
                        "2PM": two_pm,
                        "3PM": three_pm,
                        "fouls": fouls,
                        "raw_perf": raw_perf
                    }

                    with lock:
                        all_players.append(player_data)
                except Exception as e:
                    print("Error parsing player row:", e)

        # -----------------------
        # Update player ELOs for this game
        # -----------------------
        game_players = [p for p in all_players if p['game_date']==game['date'] and p['team'] in [game['home_team_id'], game['away_team_id']]]
        if not game_players:
            continue

        # Determine winner for bonus
        if game['home_score'] is not None and game['away_score'] is not None:
            if game['home_score'] > game['away_score']:
                winning_team = game['home_team_id']
            elif game['away_score'] > game['home_score']:
                winning_team = game['away_team_id']
            else:
                winning_team = None
        else:
            winning_team = None

        for p in game_players:
            if winning_team and p['team'] == winning_team:
                p['raw_perf'] *= (1 + WIN_BONUS_PCT)
            p['raw_perf'] = max(p['raw_perf'], MIN_PERF)

        total_perf = sum(p['raw_perf'] for p in game_players)
        for p in game_players:
            p['S'] = p['raw_perf'] / total_perf if total_perf > 0 else 1.0 / len(game_players)
            if p['player_name'] not in player_elo:
                player_elo[p['player_name']] = grade_offsets.get(p['grade'], BASE_ELO)

        elos_list = [player_elo[p['player_name']] for p in game_players]
        E_dist = expected_distribution(elos_list)
        for idx, p in enumerate(game_players):
            S_i = p['S']
            E_i = E_dist[idx]
            old_elo = player_elo[p['player_name']]
            delta = K_PLAYER * (S_i - E_i)
            player_elo[p['player_name']] = old_elo + delta

    driver.quit()

# -----------------------
# Launch threads per grade
# -----------------------
threads = []
for grade_name, grade_url in grades_info:
    t = threading.Thread(target=scrape_grade_and_update_elo, args=(grade_name, grade_url))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

# -----------------------
# Compute team ELOs from top 5 all-time players
# -----------------------
all_team_ids = pd.unique([g['home_team_id'] for g in all_games] + [g['away_team_id'] for g in all_games])
team_elo = {}
for team_id in all_team_ids:
    roster = [p['player_name'] for p in all_players if p['team']==team_id]
    roster_elos = [player_elo.get(name, BASE_ELO) for name in set(roster)]
    top5_elos = sorted(roster_elos, reverse=True)[:5]
    team_elo[team_id] = float(np.mean(top5_elos)) if top5_elos else BASE_ELO

# -----------------------
# Save CSVs
# -----------------------
df_player_elos = pd.DataFrame([{
    "player_name": pname,
    "team_id": next((p['team'] for p in all_players if p['player_name']==pname), None),
    "ELO": elo
} for pname, elo in player_elo.items()])

df_team_elos = pd.DataFrame([{
    "team_id": tid,
    "team_name": next((g['home_team'] for g in all_games if g['home_team_id']==tid), tid),
    "ELO": elo
} for tid, elo in team_elo.items()])

pd.DataFrame(all_games).to_csv("data/full_season.csv", index=False)
pd.DataFrame(all_players).to_csv("data/player_stats.csv", index=False)
df_player_elos.to_csv("data/player_elo.csv", index=False)
df_team_elos.to_csv("data/team_elo.csv", index=False)

print(f"Scraping & ELO calculation complete! {len(all_games)} games and {len(all_players)} player records saved.")
print("Top 10 players by ELO:")
print(df_player_elos.sort_values("ELO", ascending=False).head(10))
print("Team ELOs:")
print(df_team_elos.sort_values("ELO", ascending=False))
