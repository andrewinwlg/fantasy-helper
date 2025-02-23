#!/bin/bash -u

if [ -z "$NBA_LOGIN" ] || [ -z "$NBA_PWD" ]; then
    echo "Error: NBA_LOGIN and NBA_PWD environment variables must be set"
    exit 1
fi

# Ensure the /tmp/logs directory exists
mkdir -p /tmp/logs

# Define log file with the current date (e.g., /tmp/logs/20250125.log)
LOG_FILE="/tmp/logs/$(date '+%Y%m%d_%H%M%S').log"

# Redirect all output (stdout and stderr) with no buffering
exec > >(stdbuf -oL tee -a "$LOG_FILE") 2>&1

echo "NBA scraper script started at $(date)"

echo "Scraping team roster"
python3 team_scraper.py

echo "Scraping injury news"
python3 injury_scraper.py

echo "Updating team roster file"
python3 utils.py --update $NBA_LOGIN

cd /mnt/c/BUILD/git_build/fantasy-helper
python3 incremental_update.py
python3 salary_scraper.py

python3 optimize_roster.py --salary-cap 101.3 --transactions 2 --exclude "Keaton Wallace"
python3 utils.py --print-team

if grep -q "error" "$LOG_FILE"; then
    echo "Check the log file for error messages."
else
    echo "No errors found."
fi

echo "NBA scraper script finished at $(date)"
