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

# -----------------------
# Configuration
# -----------------------
BASE = "https://www.playhq.com"
START_PAGE = "https://www.playhq.com/basketball-victoria/org/balwyn-blazers-basketball-association-senior-competition/open-age-mens-thursday-night-winter-2025/b9a20da8"

# Selenium setup
options = Options()
options.headless = True
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

all_games = []
all_players = []

# -----------------------
# Step 1: Collect all grades
# -----------------------
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

# Include current grade if first one is active and skipped
if not grades_info:
    active_grade_el = driver.find_element(By.CSS_SELECTOR, "h2 span")
    grade_name = active_grade_el.text.strip()
    grade_url = driver.current_url
    grades_info.append((grade_name, grade_url))

print(f"Found grades: {[g[0] for g in grades_info]}")

# -----------------------
# Step 2: Collect all rounds per grade
# -----------------------
for grade_name, grade_url in grades_info:
    print(f"\nScraping grade: {grade_name}")
    driver.get(grade_url)
    time.sleep(2)

    # Detect rounds dynamically
    round_elements = driver.find_elements(By.CSS_SELECTOR, "ul.sc-1odi71i-0 li a[data-testid^='page-']")
    round_urls = [el.get_attribute("href") for el in round_elements]
    round_names = [el.text.strip() for el in round_elements]

    # Ensure R1 first
    if "R1" not in [r.split("/")[-1] for r in round_urls]:
        round_urls.insert(0, grade_url + "/R1")
        round_names.insert(0, "R1")

    print(f"Rounds detected: {round_names}")

    # -----------------------
    # Step 3: Collect all games (fixtures) first
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

        try:
            grade_header = driver.find_element(By.TAG_NAME, "h2").text.strip()
        except:
            grade_header = grade_name

        try:
            round_header = driver.find_element(By.TAG_NAME, "h3").text.strip()
        except:
            round_header = r_name

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

                    all_games.append({
                        "grade": grade_header,
                        "round": round_header,
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

# -----------------------
# Step 4: Scrape all player stats
# -----------------------
for game in all_games:
    print(f"\nScraping players for game: {game['home_team']} vs {game['away_team']} ({game['round']})")
    driver.get(game['box_score_link'])
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)

    # Toggle "Show advanced stats"
    try:
        adv_button = driver.find_element(By.XPATH, "//button[.//span[text()='Show advanced stats']]")
        span_class = adv_button.find_element(By.TAG_NAME, "span").get_attribute("class")
        if "hIyAxi" in span_class:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", adv_button)
            time.sleep(0.5)
            adv_button.click()
            time.sleep(2)
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", adv_button)
        time.sleep(2)
    except Exception:
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

                all_players.append({
                    "grade": game['grade'],          # Added grade
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

# -----------------------
# Step 5: Save CSVs
# -----------------------
df_games = pd.DataFrame(all_games)
df_games.to_csv("data/full_season.csv", index=False)

df_players = pd.DataFrame(all_players)
df_players.to_csv("data/player_stats.csv", index=False)

print(f"\nScraping complete! {len(df_games)} games and {len(df_players)} player records saved.")
