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

# Function to handle errors
handle_error() {
    echo "Error occurred on line $1"
    # Close any potential lingering database connections
    # This will kill sqlite processes associated with this session
    for pid in $(pgrep -f "sqlite.*nba_stats.db"); do
        echo "Killing SQLite process $pid"
        kill -9 $pid 2>/dev/null || true
    done
    exit 1
}

# Set up trap to catch errors
trap 'handle_error $LINENO' ERR

echo "Scraping team roster"
python3 team_scraper.py || handle_error $LINENO

echo "Scraping injury news"
python3 injury_scraper.py || handle_error $LINENO

echo "Updating team roster file"
python3 utils.py --update $NBA_LOGIN || handle_error $LINENO

cd /mnt/c/BUILD/git_build/fantasy-helper
python3 incremental_update.py --force --check-all || handle_error $LINENO
python3 salary_scraper.py || handle_error $LINENO

python3 optimize_roster.py --salary-cap 101.3 --transactions 2 || handle_error $LINENO
python3 utils.py --print-team || handle_error $LINENO

if grep -q "error" "$LOG_FILE"; then
    echo "Check the log file for error messages."
else
    echo "No errors found."
fi

echo "NBA scraper script finished at $(date)"
