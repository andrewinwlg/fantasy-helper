import sqlite3
import pandas as pd
from incremental_update import get_latest_games

def test_get_latest_games():
    """
    Test the get_latest_games function with a limited set of player URLs.
    """
    # Connect to the database
    conn = sqlite3.connect('nba_stats.db')
    
    # Use a small set of player URLs
    player_urls = [
        '/players/a/anthoco01.html',  # Cole Anthony
        '/players/b/beaslma01.html'    # Malik Beasley
    ]
    
    print("Testing get_latest_games with a small set of players...")
    
    # Call the function
    try:
        new_games_count, inactive_players = get_latest_games(conn, player_urls)
        
        print(f"\nTest results:")
        print(f"New games added: {new_games_count}")
        print(f"Inactive players: {len(inactive_players)}")
        
        if inactive_players:
            print("Inactive players:")
            for name, url in inactive_players:
                print(f"  - {name} ({url})")
        
        # Verify that the data was inserted correctly
        if new_games_count > 0:
            for url in player_urls:
                # Get player name
                player_name = pd.read_sql_query(
                    "SELECT DISTINCT Player FROM player_stats WHERE player_url = ?",
                    conn, params=[url]
                ).iloc[0]['Player'] if not pd.read_sql_query(
                    "SELECT DISTINCT Player FROM player_stats WHERE player_url = ?",
                    conn, params=[url]
                ).empty else "Unknown"
                
                # Get game count
                game_count = pd.read_sql_query(
                    "SELECT COUNT(*) as count FROM player_game_logs WHERE player_url = ?",
                    conn, params=[url]
                ).iloc[0]['count']
                
                print(f"{player_name}: {game_count} games in database")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {str(e)}")
        import traceback
        print(f"Full stack trace:\n{traceback.format_exc()}")
    finally:
        conn.close()

if __name__ == "__main__":
    test_get_latest_games() 