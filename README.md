# NBA Fantasy Helper

Tools for scraping and analyzing NBA fantasy basketball data.

## Setup

1. Install Python requirements:
```bash
pip install -r requirements.txt
```

2. Install Chrome and chromedriver:
```bash
# On Ubuntu/Debian:
sudo apt install google-chrome-stable
sudo apt install chromium-chromedriver

# On Windows:
# Download and install Chrome from https://www.google.com/chrome/
# Download chromedriver from https://chromedriver.chromium.org/
```

## Usage

1. Scrape current NBA player stats:
```bash
python nba_scraper.py
python post_scraper.py
python calc_fpts.py
```
Note: This may take up to an hour to run completely.

2. Scrape NBA salary cap data:
```bash
# On Linux:
python salary_scraper.py

# On Windows:
python salary_scraper_win.py
```

3. Create database views:
```bash
python create_view.py
```

4. Run predictions for player performance:
```bash
python predict_performance.py
```

5. To update with new data only:
```bash
python incremental_update.py
```

## Features

- Scrapes player stats from basketball-reference.com
- Scrapes salary data from NBA fantasy
- Calculates fantasy points for different scoring systems
- Predicts future player performance using machine learning
- Creates useful database views for analysis

## Data Sources

- Player stats: basketball-reference.com
- Salary data: nbafantasy.nba.com

## Viewing the Data

You can download any SQLite viewer like [DB Browser for SQLite](https://sqlitebrowser.org/dl/) to view the data in a graphical layout, export to excel, etc.

## Development Setup

### 1. Install Dependencies
```bash
# Install all required packages including development dependencies
pip install -r requirements.txt
```

### 2. Setup Pre-commit Hooks
```bash
# Install pre-commit
pre-commit install
```

This will install hooks that run before each commit to check:
- Valid YAML files
- Valid Python syntax
- No large files being committed
- Basic pylint checks

### 3. IDE Setup (VS Code)
1. Install the Python extension in VS Code
2. The repository includes settings in `.vscode/settings.json` that will:
    - Enable pylint
    - Use our custom pylint configuration
    - Run linting on save

### 4. Running Checks Manually
```bash
# Run pylint on all Python files
pylint $(git ls-files '*.py')

# Run pre-commit checks without committing
pre-commit run --all-files
```

### 5. Understanding Checks
- The project uses pylint with custom rules defined in `pylintrc`
- GitHub Actions will run these checks on push/PR
- Checks must pass (score > 7/10) for PR to be merged
- Some style checks are disabled to maintain existing code style

## TODOs for this project

- [x] An incremental data fetcher that only gets new data since the last time it was run
- [x] Fix error at the end: pandas.errors.DatabaseError: Execution failed on sql 'SELECT COUNT(*) as count FROM fantasy_points': no such table: fantasy_points
- [X] Setup basic linting and gitgub status checks
- [X] Scrape salary data
- [X] Check names match across 2 different scrapers
- [ ] Final fantasy points calculation took too long to run, so I need to speed it up -- says it was running for 12501 new games, but couldn't have been more than 300 or so
- [ ] The incremental update seems to do too much clean up that's already been done in the nba_scraper.py
- [?] Present the data in a webpage
- [ ] Do some basic data science to evaluate who are valuable players
- [ ] Load your own fantasy team into the database for analysis
- [ ] Load your whole fantasy league into the database for analysis
- [ ] Secure storage of fantasy league credentials
- [ ] Build an AI agent that can translate English language requests into recommendations, e.g. "who should I consider trading with?" "what free agent shows the most promise?" etc
- [ ] Setup pipeline for automatic builds
- [ ] Setup status checks for merges
- [ ] Make the whole thing multi-tenant so different users can login and see only their own fantasy league/team
- [ ] Package the whole thing up in deployable containers
- [ ] Web interface for some simple use-cases
- [ ] Speed up the incremental update
- [ ] Add more fantasy scoring systems
- [ ] Add support for DraftKings scoring
- [ ] Add support for FanDuel scoring
- [ ] Add player injury status tracking
- [ ] Add team schedule tracking
- [ ] Add player news/updates tracking
- [ ] Add player consistency metrics
- [ ] Add player correlation analysis
- [ ] Add player stacking recommendations
- [ ] Add lineup optimization
- [ ] Add player ownership projections
- [ ] Add bankroll management recommendations
- [ ] Add contest selection recommendations
- [ ] Add player props predictions
- [ ] Add player matchup analysis
- [ ] Add team defense vs position stats
- [ ] Add pace of play analysis
- [ ] Add vegas odds integration
- [ ] Add historical ownership data
- [ ] Add ROI tracking and analysis

## Implementation Notes

### Incremental update notes

this process could be sped up if the incremental_update checked 1) the date of the last game played and recorded in the sqlite database, then 2) checked the scores page @https://www.basketball-reference.com/boxscores/  to see what teams have played since that date, and only check players who play for teams that have had games played.  This is a little tricky in that you have to check today's date, and see if it is greater than the last saved game, and you may have to step back day by day until you get to the last saved day, if it has been more than one day since the games were last saved.  The "a.button2.prev" element has the href that will take you to the previous day.

### Status checks for builds and PRs

1. **Code Linting (Flake8)**: Enforces PEP 8 standards and catches style or syntax issues.
2. **Unit Testing (Pytest)**: Runs automated tests to verify code functionality.
3. **Dependency Vulnerability Check (Safety)**: Detects known security issues in dependencies.
4. **Type Checking (MyPy)**: Validates type annotations for correctness and consistency.
5. **Code Formatting (Black)**: Ensures consistent code style through automatic formatting.
6. **Optional Enhancements**:

   - Code Coverage: Use pytest-cov to measure test coverage.
   - Security Checks: Add tools like bandit for static security analysis.
   - Build Automation: Use tools like tox for testing across Python versions.

## Setting up ChromeDriver on WSL

1. Install Chrome:
```bash
# Add Chrome's repository key
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -

# Add Chrome's repository
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update and install Chrome
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

2. Install ChromeDriver matching your Chrome version:
```bash
# Get Chrome version
CHROME_VERSION=$(google-chrome --version | cut -d " " -f3)
echo "Chrome version: $CHROME_VERSION"

# Create directory for ChromeDriver
mkdir -p ~/webdrivers
cd ~/webdrivers

# Download matching ChromeDriver
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/$CHROME_VERSION/linux64/chromedriver-linux64.zip
unzip chromedriver-linux64.zip
sudo ln -s $HOME/webdrivers/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
```

3. Install required dependencies:
```bash
sudo apt-get install -y \
    libxss1 \
    libappindicator1 \
    libindicator7 \
    xvfb \
    unzip \
    libnss3 \
    libgconf-2-4 \
    libasound2
```

4. Verify installation:
```bash
# Check Chrome version
google-chrome --version

# Check ChromeDriver version
chromedriver --version
```

The versions should match. If they don't, repeat step 2 with the correct version number.
