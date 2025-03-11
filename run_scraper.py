#!/usr/bin/env python3
"""
Script to run the team_scraper.py with credentials entered at runtime.
This way, credentials are not stored in the script or visible in the command history.
"""

import os
import subprocess
import getpass

def main():
    """Prompt for credentials and run the team_scraper.py script."""
    print("NBA Fantasy Team Scraper")
    print("-----------------------")
    
    # Prompt for credentials
    login = input("Enter your NBA Fantasy login email: ")
    password = getpass.getpass("Enter your password (input will be hidden): ")
    
    # Set environment variables for the subprocess
    env = os.environ.copy()
    env['NBA_LOGIN'] = login
    env['NBA_PWD'] = password
    
    # Run the team_scraper.py script
    print("\nRunning team_scraper.py...")
    try:
        result = subprocess.run(['python', 'team_scraper.py'], env=env, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running team_scraper.py: {e}")
        return e.returncode
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 