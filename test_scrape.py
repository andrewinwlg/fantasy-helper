"""
Test script to scrape a single player's game log
"""
from nba_scraper import scrape_player_game_log
import pandas as pd

def main():
    # Test with Jordan Poole's URL
    player_url = "/players/p/poolejo01.html"
    
    print(f"Testing scrape_player_game_log with URL: {player_url}")
    game_log = scrape_player_game_log(player_url)
    
    if game_log is not None:
        print(f"\nSuccessfully scraped {len(game_log)} rows")
        print(f"Columns: {game_log.columns.tolist()}")
        
        # Check if key columns are present
        key_columns = ['Rk', 'Date', 'Tm', 'Opp', 'PTS', 'TRB', 'AST']
        for col in key_columns:
            print(f"Column '{col}' present: {col in game_log.columns}")
        
        # Print first few rows
        print("\nFirst 3 rows:")
        print(game_log.head(3).to_string())
    else:
        print("Failed to scrape game log")

if __name__ == "__main__":
    main() 