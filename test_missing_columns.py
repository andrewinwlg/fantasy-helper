import sqlite3
import pandas as pd
import copy
import traceback
from incremental_update import get_latest_games

def test_missing_columns():
    """
    Test to simulate a situation where important statistical columns are renamed or missing.
    """
    # Connect to the database
    conn = sqlite3.connect('nba_stats.db')
    
    # Create a mock function to replace the original scrape_player_game_log function
    # This will simulate a case where column names have changed on the website
    def mock_scrape_player_game_log(player_url):
        # Import the original function just for testing
        from nba_scraper import scrape_player_game_log
        
        # Get actual game logs first
        original_game_logs = scrape_player_game_log(player_url)
        
        if original_game_logs is None or original_game_logs.empty:
            return None
            
        # Create a copy to modify
        modified_game_logs = copy.deepcopy(original_game_logs)
        
        # Simulate column name changes
        column_changes = {
            'PTS': 'Points', 
            'BLK': 'Blocks',
            'STL': 'Steals',
            'AST': 'Assists'
        }
        
        # Rename columns
        for old_col, new_col in column_changes.items():
            if old_col in modified_game_logs.columns:
                modified_game_logs = modified_game_logs.rename(columns={old_col: new_col})
        
        print("\nSimulated column changes:")
        for old_col, new_col in column_changes.items():
            print(f"  {old_col} -> {new_col}")
            
        return modified_game_logs
    
    # Patch the function for testing
    import incremental_update
    # Save original function
    original_scrape = incremental_update.scrape_player_game_log
    # Replace with mock function
    incremental_update.scrape_player_game_log = mock_scrape_player_game_log
    
    try:
        # Use a small set of player URLs for testing
        player_urls = ['/players/a/anthoco01.html']  # Just Cole Anthony
        
        print("Testing get_latest_games with simulated column changes...")
        print("Expected behavior: Script should fail with error about missing columns")
        
        success = False
        try:
            new_games_count, inactive_players = get_latest_games(conn, player_urls)
            print("\nUnexpected result: Function completed without error")
            
        except ValueError as e:
            print("\nTest PASSED: Function correctly failed with ValueError:")
            print(f"Error: {str(e)}")
            success = True
            
        except Exception as e:
            print(f"\nUnexpected error type: {type(e).__name__}")
            print(f"Error: {str(e)}")
            traceback.print_exc()
        
        if success:
            print("\nSuccessfully verified that the function fails when critical columns are missing.")
        else:
            print("\nTest FAILED: Function did not raise an error for missing columns.")
    
    finally:
        # Restore the original function
        incremental_update.scrape_player_game_log = original_scrape
        conn.close()

if __name__ == "__main__":
    test_missing_columns() 