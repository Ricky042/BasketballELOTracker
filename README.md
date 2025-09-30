# Basketball Player & Team ELO Tracker

A Python-based scraper and ELO calculator for basketball leagues using [PlayHQ](https://www.playhq.com). This project scrapes game and player statistics, calculates **player-centric ELO ratings**, and derives team ELOs based on top-performing players.

---

## Features

- **Web Scraping**: Automatically collects games and player stats from PlayHQ.
- **Player-Centric ELO**: Calculates ELO ratings based on individual performances, adjusted for fouls and wins.
- **Grade-Aware Initialization**: Players in higher grades start with higher base ratings.
- **Team ELO Calculation**: Computes team ratings as the average of the top 5 all-time ELO players.
- **Threaded Scraping**: Efficiently scrapes multiple grades in parallel.
- **CSV Outputs**: Saves results to `player_elo.csv`, `team_elo.csv`, and raw scraped data.

---

## Installation

1. Clone this repository:

```bash
git clone https://github.com/your-username/basketball-elo-tracker.git
cd basketball-elo-tracker
```

2. Create a Python virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install required packages:

```bash
pip install -r requirements.txt
```

---

## Usage

1. Update the START_PAGE URL in full_scaper.py to your league page on PlayHQ.
2. Run scraper

```bash
python full_scraper.py
```

3. Outputs will be saved to the data/ directory

---

## Player ELO Calculation

Player ELO ratings are calculated in a **player-centric way**, taking into account individual performance, fouls, and game outcomes. Here’s how it works:

### 1. Base Rating by Grade

- Players are initialized with different starting ELOs based on their **grade**.
- The **highest grade** starts with a base of 1500 (Grade 1 / A Grade), and each subsequent lower grade starts **25 points lower**.
- The grade order is automatically determined from the league page, so it works regardless of whether grades are labeled `A`, `B`, `C` or `Grade 1`, `Grade 2`, etc.

### 2. Compute Raw Performance per Player

\[
\text{raw\_perf} = \text{points} - 0.1 \times \text{fouls}
\]

- Fouls are penalized to reduce performance impact.
- Performance is floored to **0.01** to avoid negative or zero values.
- Players on the **winning team** get a **15% multiplicative bonus**.

### 3. Expected Distribution

\[
E_i = \frac{10^{R_i / 400}}{\sum_j 10^{R_j / 400}}
\]

- Converts player ELO (`R_i`) into a share of expected performance in the game.
- Division by **400** scales differences, so a 400-point rating difference corresponds roughly to a 10× expected advantage.
- Ensures stronger players contribute more to the expectation.

### 4. Actual Performance Share

\[
S_i = \frac{\text{raw\_perf}_i}{\sum_j \text{raw\_perf}_j}
\]

- Each player's **actual contribution** relative to all players in the game.

### 5. Update ELO

\[
\Delta_i = K \cdot (S_i - E_i)
\]

- `K` is the learning rate (default: 30).
- Player ELO **increases** if actual performance exceeds expectation (`S_i > E_i`) and **decreases** otherwise.
- Updated ELO:

\[
R_i' = R_i + \Delta_i
\]

---

This approach ensures that ELO is **dynamic**, reflects individual contributions, and adapts across grades and over time.
