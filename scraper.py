from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time

# Base URL for the season
BASE = "https://www.playhq.com"
base_url = "https://www.playhq.com/basketball-victoria/org/balwyn-blazers-basketball-association-senior-competition/winter-2025/thursday-open-men-1/725dce49/"
round_ids = [f"R{i}" for i in range(1, 15)] + ["SF", "GF"]
round_urls = [base_url + r for r in round_ids]

# Selenium setup
options = Options()
options.headless = True
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

all_games = []
all_players = []

# --- Scrape game info ---
for round_url in round_urls:
    print(f"Scraping Round: {round_url.split('/')[-1]} -> {round_url}")
    driver.get(round_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='games-on-date']"))
        )
    except:
        print(f"Timeout loading {round_url}")
        continue

    try:
        grade = driver.find_element(By.TAG_NAME, "h2").text.strip()
    except:
        grade = "Unknown Grade"
    try:
        round_name = driver.find_element(By.TAG_NAME, "h3").text.strip()
    except:
        round_name = round_url.split("/")[-1]

    date_blocks = driver.find_elements(By.CSS_SELECTOR, "[data-testid='games-on-date']")
    for date_block in date_blocks:
        try:
            date_text = date_block.find_element(By.CSS_SELECTOR, "span").text.strip()
        except:
            date_text = "Unknown Date"

        games = date_block.find_elements(By.CSS_SELECTOR, "div.sc-1uurivg-5.iSzlTC")
        # --- inside the game scraping loop ---
        for game_div in games:
            try:
                teams = game_div.find_elements(By.CSS_SELECTOR, "a.sc-9jw1ry-3")
                scores = game_div.find_elements(By.CSS_SELECTOR, "span.sc-1uurivg-10")
                fixture_btn = game_div.find_element(By.CSS_SELECTOR, "a[data-testid^='fixture-button-']")
                box_score_link = fixture_btn.get_attribute("href")
                if not box_score_link.startswith("http"):
                    box_score_link = BASE + box_score_link

                # Get team names
                home_team = teams[0].text.strip()
                away_team = teams[1].text.strip()

                # Get team IDs from the href
                home_team_id = teams[0].get_attribute("href").split("/")[-2]
                away_team_id = teams[1].get_attribute("href").split("/")[-2]

                try:
                    home_score = int(scores[0].text.strip())
                    away_score = int(scores[1].text.strip())
                    forfeit = False
                except:
                    home_score = None
                    away_score = None
                    forfeit = True

                # Save game info including team IDs
                all_games.append({
                    "grade": grade,
                    "round": round_name,
                    "date": date_text,
                    "home_team": home_team,
                    "home_team_id": home_team_id,
                    "away_team": away_team,
                    "away_team_id": away_team_id,
                    "home_score": home_score,
                    "away_score": away_score,
                    "forfeit": forfeit,
                    "box_score_link": box_score_link
                })

            except Exception as e:
                print("Error parsing game:", e)


# --- Scrape player stats ---
for game in all_games:
    print(f"Scraping players for game: {game['home_team']} vs {game['away_team']}")
    driver.get(game['box_score_link'])
    time.sleep(2)  # wait for dynamic content

    # Scroll to bottom to render dynamic elements
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)  # give page time to render

    # Toggle "Show advanced stats" button if it's OFF
    try:
        adv_button = driver.find_element(
            By.XPATH, "//button[.//span[text()='Show advanced stats']]"
        )
        span_class = adv_button.find_element(By.TAG_NAME, "span").get_attribute("class")
        print(f"DEBUG: Current advanced stats span class = {span_class}")
        if "hIyAxi" in span_class:  # OFF
            print("DEBUG: Advanced stats currently OFF, clicking button...")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", adv_button)
            time.sleep(0.5)
            adv_button.click()
            time.sleep(2)
        else:
            print("DEBUG: Advanced stats already ON")
    except ElementClickInterceptedException:
        print("DEBUG: Click intercepted, trying JavaScript click")
        driver.execute_script("arguments[0].click();", adv_button)
        time.sleep(2)
    except Exception as e:
        print("DEBUG: Unexpected error toggling advanced stats:", e)

    # Parse tables
    tables = driver.find_elements(By.CSS_SELECTOR, "table[data-testid^='stats-']")
    for table in tables:
        team_id = table.get_attribute("data-testid").replace("stats-", "")
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                print(f"DEBUG: Found {len(cells)} cells -> {[c.text for c in cells]}")  # debug
                if len(cells) < 6:
                    print("DEBUG: Skipping row, not enough cells")
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

                all_players.append({
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
                    "fouls": fouls
                })
            except Exception as e:
                print("Error parsing player row:", e)

driver.quit()

# --- Save CSVs ---
df_games = pd.DataFrame(all_games)
df_games.to_csv("data/full_season.csv", index=False)

df_players = pd.DataFrame(all_players)
df_players.to_csv("data/player_stats.csv", index=False)

print(f"Scraping complete! {len(df_games)} games and {len(df_players)} player records saved.")
