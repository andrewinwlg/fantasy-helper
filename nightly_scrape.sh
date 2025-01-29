#!/bin/bash -u

# Ensure the /tmp/logs directory exists
mkdir -p /tmp/logs

# Define log file with the current date (e.g., /tmp/logs/20250125.log)
LOG_FILE="/tmp/logs/$(date '+%Y%m%d_%H%M%S').log"

# Redirect all output (stdout and stderr) with no buffering
exec > >(stdbuf -oL tee -a "$LOG_FILE") 2>&1

echo "NBA scraper script started at $(date)"

cd /mnt/c/BUILD/git_build/fantasy-helper
python3 incremental_update.py
python3 salary_scraper.py
python3 optimize_roster.py --salary-cap 101.3 --transactions 2 --exclude "Keaton Wallace"
python3 utils.py --print-team

echo "NBA scraper script finished at $(date)"
