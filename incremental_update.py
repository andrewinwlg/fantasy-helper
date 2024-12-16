import pandas as pd
import sqlite3
from datetime import datetime
import time
from nba_scraper import scrape_player_game_log, get_existing_player_urls
from post_scraper import clean_player_game_logs
from calc_fpts import calculate_fantasy_points

def get_latest_games(conn, player_urls):
    """
    Fetches only new games for each player and adds them to the database.
    Returns the number of new games added.
    """
    new_games_count = 0
    
    # Get player names from the database for each URL
    for url in player_urls:
        # Get player name from the database
        player_query = """
        SELECT DISTINCT Player FROM player_stats 
        WHERE player_url = ?
        """
        player_df = pd.read_sql_query(player_query, conn, params=[url])
        if player_df.empty:
            print(f"Could not find player name for URL: {url}")
            continue
            
        player_name = player_df.iloc[0]['Player']
        print(f"Checking for new games for {player_name}...")
        
        # Get existing games for this player
        existing_games = pd.read_sql_query(
            """
            SELECT DISTINCT G 
            FROM player_game_logs 
            WHERE player_url = ?
            """,
            conn,
            params=[url]
        )
        
        # Get current games from website
        try:
            current_games = scrape_player_game_log(url)
            if current_games is None or current_games.empty:
                continue
            
            # Clean up the current games data
            current_games = current_games[current_games['G'].notna()]   # Remove any rows without G
            current_games = current_games[current_games['Rk'].notna()]  # Remove rows where player didn't play
            current_games = current_games[current_games['Date'] != 'Date']  # Remove header rows
            
            # Convert both to integers for comparison
            existing_game_numbers = set(pd.to_numeric(existing_games['G'], errors='coerce').dropna().astype(int))
            current_game_numbers = pd.to_numeric(current_games['G'], errors='coerce')
            
            print(f"Existing games: {len(existing_game_numbers)}")
            print(f"Current games: {len(current_games)}")
            
            # Find new games by comparing game numbers
            new_games = current_games[~current_game_numbers.isin(existing_game_numbers)]
            
            if not new_games.empty:
                print(f"Found {len(new_games)} new games for {player_name}")
                print(f"New game numbers: {new_games['G'].tolist()}")
                new_games.to_sql('player_game_logs', conn, if_exists='append', index=False)
                new_games_count += len(new_games)
            else:
                print(f"No new games found for {player_name}")
            
            # Don't overwhelm the website
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing {player_name}: {str(e)}")
            continue
    
    return new_games_count

def process_new_games(conn):
    """
    Processes newly added games through post_scraper and calc_fpts logic
    """
    # First, clean all game logs (including new ones)
    clean_player_game_logs()
    
    # Then calculate fantasy points for all games
    calculate_fantasy_points()
    
    # Count how many new games were processed by comparing the counts
    before_count = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM fantasy_points", 
        conn
    ).iloc[0]['count']
    
    after_count = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM clean_game_logs", 
        conn
    ).iloc[0]['count']
    
    return after_count - before_count

def main():
    print(f"Starting incremental update at {datetime.now()}")
    
    # Connect to database - change from fantasy.db to nba_stats.db
    conn = sqlite3.connect('nba_stats.db')
    
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