from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

# Base URL for the season
base_url = "https://www.playhq.com/basketball-victoria/org/balwyn-blazers-basketball-association-senior-competition/winter-2025/thursday-open-men-1/725dce49/"
round_ids = [f"R{i}" for i in range(1, 15)] + ["SF", "GF"]
round_urls = [base_url + r for r in round_ids]

# Selenium setup
options = Options()
options.headless = True
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

all_games = []

for round_url in round_urls:
    print(f"Scraping Round: {round_url.split('/')[-1]} -> {round_url}")
    driver.get(round_url)

    # Wait for fixture list to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='games-on-date']"))
        )
    except:
        print(f"Timeout loading {round_url}")
        continue

    # Get grade
    try:
        grade = driver.find_element(By.TAG_NAME, "h2").text.strip()
    except:
        grade = "Unknown Grade"

    # Get round name
    try:
        round_name = driver.find_element(By.TAG_NAME, "h3").text.strip()
    except:
        round_name = round_url.split("/")[-1]

    # Extract all date blocks
    date_blocks = driver.find_elements(By.CSS_SELECTOR, "[data-testid='games-on-date']")
    print(f"Found {len(date_blocks)} date blocks in this round")

    for date_block in date_blocks:
        try:
            date_text = date_block.find_element(By.CSS_SELECTOR, "span").text.strip()
        except:
            date_text = "Unknown Date"

        # Each game is in a sc-1uurivg-5.iSzlTC block inside the date block
        games = date_block.find_elements(By.CSS_SELECTOR, "div.sc-1uurivg-5.iSzlTC")
        print(f"  Found {len(games)} games on {date_text}")

        for game_div in games:
            try:
                teams = game_div.find_elements(By.CSS_SELECTOR, "a.sc-9jw1ry-3")
                scores = game_div.find_elements(By.CSS_SELECTOR, "span.sc-1uurivg-10")

                home_team = teams[0].text.strip()
                away_team = teams[1].text.strip()

                # Handle forfeits
                try:
                    home_score = int(scores[0].text.strip())
                    away_score = int(scores[1].text.strip())
                    forfeit = False
                except:
                    home_score = None
                    away_score = None
                    forfeit = True

                all_games.append({
                    "grade": grade,
                    "round": round_name,
                    "date": date_text,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score,
                    "forfeit": forfeit
                })

            except Exception as e:
                print("    Error parsing a game:", e)

driver.quit()

# Save to CSV
df = pd.DataFrame(all_games)
df.to_csv("data/full_season.csv", index=False)
print(f"Scraping complete! {len(df)} games saved to full_season.csv")
