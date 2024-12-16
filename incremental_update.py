import pandas as pd
import sqlite3
from datetime import datetime
import time
from nba_scraper import scrape_player_game_log, get_existing_player_urls
from post_scraper import process_gamelog_row
from calc_fpts import calculate_fpts

def get_latest_games(conn, player_urls):
    """
    Fetches only new games for each player and adds them to the database.
    Returns the number of new games added.
    """
    new_games_count = 0
    
    for player_name, url in player_urls.items():
        print(f"Checking for new games for {player_name}...")
        
        # Get existing games for this player
        existing_games = pd.read_sql_query(
            "SELECT player_name, G FROM gamelogs WHERE player_name = ?",
            conn,
            params=[player_name]
        )
        
        # Get current games from website
        try:
            current_games = scrape_player_game_log(url)
            if current_games is None or current_games.empty:
                continue
                
            # Find new games by comparing game numbers
            existing_game_numbers = set(existing_games['G'].astype(str))
            new_games = current_games[~current_games['G'].astype(str).isin(existing_game_numbers)]
            
            if not new_games.empty:
                print(f"Found {len(new_games)} new games for {player_name}")
                new_games.to_sql('gamelogs', conn, if_exists='append', index=False)
                new_games_count += len(new_games)
            
            # Don't overwhelm the website
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing {player_name}: {str(e)}")
            continue
    
    return new_games_count

def process_new_games(conn):
    """
    Processes only the newly added games through post_scraper and calc_fpts logic
    """
    # Get games that haven't been processed yet (no fantasy points calculated)
    unprocessed_games = pd.read_sql_query(
        """
        SELECT * FROM gamelogs 
        WHERE NOT EXISTS (
            SELECT 1 FROM fantasy_points 
            WHERE fantasy_points.player_name = gamelogs.player_name 
            AND fantasy_points.G = gamelogs.G
        )
        """,
        conn
    )
    
    if unprocessed_games.empty:
        return 0
        
    print(f"Processing {len(unprocessed_games)} new games...")
    
    # Process each new game
    for _, row in unprocessed_games.iterrows():
        processed_row = process_gamelog_row(row)
        if processed_row is not None:
            fantasy_points = calculate_fpts(processed_row)
            
            # Insert into fantasy_points table
            fantasy_points.to_sql('fantasy_points', conn, if_exists='append', index=False)
    
    return len(unprocessed_games)

def main():
    print(f"Starting incremental update at {datetime.now()}")
    
    # Connect to database
    conn = sqlite3.connect('fantasy.db')
    
    # Get player URLs
    player_urls = get_existing_player_urls()
    
    # Get and store new games
    new_games = get_latest_games(conn, player_urls)
    print(f"Added {new_games} new games to the database")
    
    # Process new games
    processed_games = process_new_games(conn)
    print(f"Processed {processed_games} new games")
    
    conn.close()
    print(f"Completed incremental update at {datetime.now()}")

if __name__ == "__main__":
    main() 