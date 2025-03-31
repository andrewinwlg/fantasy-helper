"""
Test script to run incremental update on a single player
"""
import sqlite3
import time
from incremental_update import get_latest_games, process_new_games
from calc_fpts import calculate_fantasy_points

def main():
    # Connect to the database with a longer timeout
    conn = None
    try:
        # Set a 120-second timeout for database operations
        conn = sqlite3.connect('nba_stats.db', timeout=120.0)
        
        # Test with Jordan Poole's URL
        player_urls = ["/players/p/poolejo01.html"]
        
        print(f"Testing get_latest_games with URL: {player_urls[0]}")
        
        # Get and store new games
        new_games, inactive_players = get_latest_games(conn, player_urls)
        print(f"Added {new_games} new games to the database")
        
        # Process new games only if we found any
        if new_games > 0:
            # Close connection before processing to avoid locks
            if conn:
                conn.close()
                conn = None
                time.sleep(2)  # Give time for the connection to fully close
            
            # Run fantasy point calculations directly with a small batch size
            # This avoids the process_new_games intermediary
            print("Running calculate_fantasy_points with small batch size...")
            calculate_fantasy_points(batch_size=100)  # Process in batches of 100 rows
            
            # Create a new connection for additional processing if needed
            conn = sqlite3.connect('nba_stats.db', timeout=120.0)
            print("Fantasy point calculations complete!")
        else:
            print("No new games found, skipping processing step")
    
    finally:
        # Ensure the connection is closed
        if conn:
            conn.close()
            print("Database connection closed")

if __name__ == "__main__":
    main() 