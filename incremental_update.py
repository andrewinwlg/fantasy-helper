import sqlite3
import time
from datetime import datetime, timedelta
import argparse
import requests
from bs4 import BeautifulSoup
import pytz

import pandas as pd

from calc_fpts import calculate_fantasy_points
from nba_scraper import get_existing_player_urls, scrape_player_game_log
from post_scraper import clean_player_game_logs


def get_latest_games(conn, player_urls, max_retries=3, timeout=10):
    """
    Fetches only new games for each player and adds them to the database.
    Returns the number of new games added.
    
    Note on column mapping:
    - 'Gtm' from the scraped data represents the team game number for the current season
    - This is mapped to 'G' in the database schema
    
    The function will fail with an error if important statistical columns are missing,
    to prevent operating on partial data.
    """
    new_games_count = 0
    total_players = len(player_urls)
    current_player = 0
    inactive_players = []  # Track players without current season data
    
    # Get player names from the database for each URL
    for url in player_urls:
        current_player += 1
        cursor = None
        try:
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
            
            # Get database table schema to know which columns we can use
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(player_game_logs)")
            db_columns = [row[1] for row in cursor.fetchall()]
            print(f"Database columns: {', '.join(db_columns[:5])}... (showing first 5)")
            
            # The database uses 'G' column for game number
            db_game_col = 'G'
            
            # Get existing games for this player
            existing_games_query = f"""
            SELECT DISTINCT {db_game_col} 
            FROM player_game_logs 
            WHERE player_url = ?
            """
            existing_games = pd.read_sql_query(existing_games_query, conn, params=[url])
            
            # Retry mechanism for scraping current games
            for attempt in range(max_retries):
                try:
                    current_games = scrape_player_game_log(url)
                    if current_games is None or current_games.empty:
                        print(f"No current games found for {player_name}. Skipping player.")
                        inactive_players.append((player_name, url))  # Add to inactive players list
                        time.sleep(1)  # Brief pause before moving to next player
                        break  # Exit the retry loop and move to next player
                    
                    # Print the columns in the scraped data
                    print(f"Scraped columns: {', '.join(current_games.columns[:5])}... (showing first 5)")
                    
                    # We specifically want 'Gtm' from the scraped data - team game number for current season
                    scraped_game_col = 'Gtm'
                    if scraped_game_col not in current_games.columns:
                        # Try to find similar column
                        possible_alternatives = ['G', 'team_game_num_season']
                        found_alternative = False
                        for alt_col in possible_alternatives:
                            if alt_col in current_games.columns:
                                print(f"Using {alt_col} as alternative to {scraped_game_col}")
                                current_games = current_games.rename(columns={alt_col: scraped_game_col})
                                found_alternative = True
                                break
                        
                        if not found_alternative:
                            error_msg = f"ERROR: Could not find '{scraped_game_col}' column in scraped data for {player_name}"
                            print(error_msg)
                            raise ValueError(error_msg)
                    
                    # Clean up the current games data
                    current_games = current_games[current_games[scraped_game_col].notna()]   # Remove any rows without game number
                    current_games = current_games[current_games['Rk'].notna()]  # Remove rows where player didn't play
                    current_games = current_games[current_games['Date'] != 'Date']  # Remove header rows
                    
                    # Convert both to integers for comparison
                    existing_game_numbers = set()
                    if not existing_games.empty:
                        existing_game_numbers = set(pd.to_numeric(existing_games[db_game_col], errors='coerce').dropna().astype(int))
                    
                    current_game_numbers = pd.to_numeric(current_games[scraped_game_col], errors='coerce')
                    
                    print(f"Existing games: {len(existing_game_numbers)}")
                    print(f"Current games: {len(current_games)}")
                    
                    # Find new games by comparing game numbers
                    new_games = current_games[~current_game_numbers.isin(existing_game_numbers)]
                    
                    if not new_games.empty:
                        print(f"Found {len(new_games)} new games for {player_name}")
                        print(f"New game numbers: {new_games[scraped_game_col].tolist()}")
                        
                        # Use a transaction for inserting new games
                        cursor = conn.cursor()
                        conn.execute("BEGIN TRANSACTION")
                        
                        # Make sure we only include columns that exist in the database schema
                        # This prevents errors about missing columns
                        column_filter = [col for col in new_games.columns if col in db_columns]
                        filtered_games = new_games[column_filter].copy()
                        
                        # Check for important statistical columns that might have been renamed
                        # These columns are critical for the application, so we fail if any are missing
                        important_columns = ['PTS', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'FG', 'FGA', '3P', '3PA', 'FT', 'FTA']
                        missing_columns = [col for col in important_columns if col not in filtered_games.columns]
                        if missing_columns:
                            # Roll back any pending transaction
                            if cursor:
                                try:
                                    conn.rollback()
                                except Exception as rollback_error:
                                    print(f"Error during rollback: {str(rollback_error)}")
                            
                            error_msg = f"ERROR: Missing critical statistical columns in scraped data: {', '.join(missing_columns)}"
                            print(error_msg)
                            print("Basketball Reference may have changed their column names.")
                            
                            # Try to identify potential renamed columns to help with debugging
                            current_cols = current_games.columns.tolist()
                            for missing_col in missing_columns:
                                # Look for columns that might be the renamed version (contain the missing column name)
                                potential_matches = [col for col in current_cols if missing_col.lower() in col.lower()]
                                if potential_matches:
                                    print(f"  Possible matches for {missing_col}: {', '.join(potential_matches)}")
                            
                            # Fail immediately to prevent operating on partial data
                            raise ValueError(error_msg + " Script aborted to prevent operating on partial data.")
                        
                        # Map 'Gtm' from scraped data to 'G' in the database
                        # This ensures we're storing the team game number (current season) in the database
                        if scraped_game_col in filtered_games.columns and scraped_game_col != db_game_col:
                            filtered_games = filtered_games.rename(columns={scraped_game_col: db_game_col})
                        
                        # Print the columns being inserted
                        print(f"Inserting with columns: {', '.join(filtered_games.columns[:5])}... (showing first 5)")
                        
                        filtered_games.to_sql('player_game_logs', conn, if_exists='append', index=False)
                        conn.commit()
                        new_games_count += len(filtered_games)
                    else:
                        print(f"No new games found for {player_name}")
                    
                    print(f"Progress: {current_player}/{total_players} players checked")
                    
                    # Don't overwhelm the website
                    time.sleep(1)
                    break  # Exit the retry loop if successful
                
                except Exception as e:
                    print(f"Error fetching games for {player_name} on attempt {attempt + 1}: {str(e)}")
                    # If we have an active transaction, roll it back
                    if cursor:
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            print(f"Error during rollback: {str(rollback_error)}")
                    
                    if attempt < max_retries - 1:
                        print("Retrying...")
                        time.sleep(timeout)  # Wait before retrying
                    else:
                        print(f"Failed to fetch games for {player_name} after {max_retries} attempts.")
                        # For critical errors like missing columns, we want to propagate the error
                        if "Missing critical statistical columns" in str(e) or "Could not find 'Gtm' column" in str(e):
                            raise
        
        except Exception as e:
            print(f"Unexpected error processing {url}: {str(e)}")
            # If we have an active transaction, roll it back
            if cursor:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    print(f"Error during rollback: {str(rollback_error)}")
            
            # Propagate critical errors to stop the entire process
            if "Missing critical statistical columns" in str(e) or "Could not find 'Gtm' column" in str(e):
                raise
    
    return new_games_count, inactive_players

def process_new_games(conn, batch_size=1000):
    """
    Processes newly added games through post_scraper and calc_fpts logic
    
    Args:
        conn: Database connection
        batch_size: Batch size for fantasy point calculations
    """
    # Store connection parameters
    conn_path = 'nba_stats.db'
    
    try:
        # Get count before processing
        before_count = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM clean_game_logs", 
            conn
        ).iloc[0]['count']
    except pd.io.sql.DatabaseError:
        # If clean_game_logs doesn't exist yet, start count at 0
        before_count = 0
    
    try:
        # Close the existing connection to avoid locks
        conn.close()
        
        print("Starting clean_player_game_logs with incremental=True...")
        # First, clean all game logs (including new ones)
        # Pass incremental=True to only process new games
        clean_player_game_logs(incremental=True)
        print("Finished clean_player_game_logs")
        
        print(f"Starting calculate_fantasy_points with batch_size={batch_size}...")
        # Then calculate fantasy points for all games with specified batch size
        calculate_fantasy_points(batch_size=batch_size)
        print("Finished calculate_fantasy_points")
        
        # Reconnect to get the after count
        new_conn = sqlite3.connect(conn_path, timeout=60.0)
        
        # Get count after processing
        after_count = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM clean_game_logs", 
            new_conn
        ).iloc[0]['count']
        
        new_conn.close()
        
        return after_count - before_count
    except Exception as e:
        print(f"Error during process_new_games: {str(e)}")
        import traceback
        print(f"Full stack trace:\n{traceback.format_exc()}")
        return 0

def remove_inactive_players(conn, inactive_players):
    """
    Remove inactive players from the database.
    
    Args:
        conn: Database connection
        inactive_players: List of tuples (player_name, player_url) to remove
    
    Returns:
        int: Number of players removed
    """
    if not inactive_players:
        return 0
        
    cursor = conn.cursor()
    removed_count = 0
    
    for _, player_url in inactive_players:
        try:
            # Remove from player_game_logs
            cursor.execute("DELETE FROM player_game_logs WHERE player_url = ?", (player_url,))
            game_logs_removed = cursor.rowcount
            
            # Remove from clean_game_logs
            cursor.execute("DELETE FROM clean_game_logs WHERE player_url = ?", (player_url,))
            clean_logs_removed = cursor.rowcount
            
            # Remove from player_stats
            cursor.execute("DELETE FROM player_stats WHERE player_url = ?", (player_url,))
            stats_removed = cursor.rowcount
            
            if game_logs_removed > 0 or clean_logs_removed > 0 or stats_removed > 0:
                removed_count += 1
                print(f"Removed player {player_url} from database")
                print(f"  - {game_logs_removed} rows from player_game_logs")
                print(f"  - {clean_logs_removed} rows from clean_game_logs")
                print(f"  - {stats_removed} rows from player_stats")
        except Exception as e:
            print(f"Error removing player {player_url}: {str(e)}")
    
    conn.commit()
    return removed_count

def get_latest_game_date(conn):
    """
    Get the most recent game date from the database.
    
    Args:
        conn: Database connection
        
    Returns:
        datetime: The most recent game date, or None if no games found
    """
    try:
        # Try to get the latest date from clean_game_logs first
        query = "SELECT MAX(Date) FROM clean_game_logs"
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()[0]
        
        if result:
            # Convert string date to datetime
            return datetime.strptime(result.split()[0], '%Y-%m-%d')
        
        # If clean_game_logs is empty, try player_game_logs
        query = "SELECT MAX(Date) FROM player_game_logs"
        cursor.execute(query)
        result = cursor.fetchone()[0]
        
        if result:
            # Convert string date to datetime
            return datetime.strptime(result.split()[0], '%Y-%m-%d')
            
        return None
    except Exception as e:
        print(f"Error getting latest game date: {str(e)}")
        return None

def get_us_pacific_time():
    """
    Get the current time in US Pacific time zone.
    
    Returns:
        datetime: Current time in US Pacific time zone
    """
    # Get current UTC time
    utc_now = datetime.now(pytz.utc)
    
    # Convert to US Pacific time
    pacific_tz = pytz.timezone('America/Los_Angeles')
    pacific_now = utc_now.astimezone(pacific_tz)
    
    return pacific_now

def get_recent_games(conn):
    """
    Get teams that have played games since the last recorded game.
    
    Args:
        conn: Database connection
        
    Returns:
        set: Set of team abbreviations that have played recently
    """
    teams_played = set()
    
    # Get the latest game date from the database
    latest_game_date = get_latest_game_date(conn)
    if not latest_game_date:
        print("No existing games found in database. Checking all teams.")
        return teams_played
    
    # Get current date in US Pacific time
    pacific_now = get_us_pacific_time()
    current_date = pacific_now.replace(tzinfo=None)  # Remove timezone info for comparison
    
    print(f"Latest game date in database: {latest_game_date.strftime('%Y-%m-%d')}")
    print(f"Current date (US Pacific): {current_date.strftime('%Y-%m-%d')}")
    
    # Add one day to latest game date to start checking from the next day
    check_date = latest_game_date + timedelta(days=1)
    
    # Check each day from the day after the latest game to yesterday
    while check_date < current_date:
        # URL for the boxscores page for this date
        url = f"https://www.basketball-reference.com/boxscores/?month={check_date.month}&day={check_date.day}&year={check_date.year}"
        
        try:
            print(f"Checking games for {check_date.strftime('%Y-%m-%d')} at URL: {url}")
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"Error: Got status code {response.status_code} for {url}")
                check_date += timedelta(days=1)
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find game summaries
            game_summaries = soup.find_all('div', class_='game_summary')
            
            if not game_summaries:
                print(f"No game summaries found for {check_date.strftime('%Y-%m-%d')}")
                
                # Try an alternative approach - look for the schedule table
                schedule_table = soup.find('table', id='schedule')
                if schedule_table:
                    print("Found schedule table, extracting teams...")
                    rows = schedule_table.find_all('tr')
                    for row in rows[1:]:  # Skip header row
                        visitor_td = row.find('td', attrs={'data-stat': 'visitor_team_name'})
                        home_td = row.find('td', attrs={'data-stat': 'home_team_name'})
                        
                        if visitor_td and home_td:
                            visitor = visitor_td.find('a')
                            home = home_td.find('a')
                            
                            if visitor:
                                teams_played.add(visitor.text.strip())
                            if home:
                                teams_played.add(home.text.strip())
                
                check_date += timedelta(days=1)
                continue
                
            # Extract team abbreviations from each game
            for game in game_summaries:
                teams = game.find_all('tr')
                for team_row in teams:
                    team_abbr = team_row.find('a')
                    if team_abbr:
                        team_text = team_abbr.text.strip()
                        teams_played.add(team_text)
            
            print(f"Found {len(game_summaries)} games with teams: {', '.join(sorted(teams_played))}")
            
            # Add a delay to avoid overwhelming the server
            time.sleep(1)
            
        except Exception as e:
            print(f"Error fetching games for {check_date.strftime('%Y-%m-%d')}: {str(e)}")
        
        # Move to the next day
        check_date += timedelta(days=1)
    
    # If we didn't find any teams, try a fallback approach
    if not teams_played:
        print("No teams found using game summaries, trying fallback approach...")
        try:
            # Try to get teams from the standings page
            url = "https://www.basketball-reference.com/leagues/NBA_2025_standings.html"
            print(f"Checking standings at URL: {url}")
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find team links in the standings tables
                team_links = soup.select('table#confs_standings_E a, table#confs_standings_W a')
                
                for link in team_links:
                    team_name = link.text.strip()
                    if team_name and len(team_name) <= 3:  # Team abbreviations are usually 3 chars or less
                        teams_played.add(team_name)
                
                print(f"Found {len(teams_played)} teams from standings page")
        except Exception as e:
            print(f"Error fetching standings: {str(e)}")
    
    return teams_played

def filter_players_by_recent_teams(conn, player_urls, recent_teams):
    """
    Filter player URLs to only include players from teams that have played recently.
    
    Args:
        conn: Database connection
        player_urls: Set of player URLs to filter
        recent_teams: Set of team abbreviations that have played recently
        
    Returns:
        set: Filtered set of player URLs
    """
    if not recent_teams:
        print("No recent teams found, checking all players")
        return player_urls
        
    # Query to get players from recent teams
    query = """
    SELECT DISTINCT ps.player_url
    FROM player_stats ps
    WHERE ps.Team IN ({})
    """.format(','.join(['?'] * len(recent_teams)))
    
    cursor = conn.cursor()
    cursor.execute(query, list(recent_teams))
    recent_player_urls = {row[0] for row in cursor.fetchall()}
    
    # Intersect with the provided player_urls
    filtered_urls = player_urls.intersection(recent_player_urls)
    
    print(f"Filtered from {len(player_urls)} to {len(filtered_urls)} players based on recent games")
    return filtered_urls

def check_database_setup(conn):
    """
    Check if the necessary tables exist and have data.
    
    Args:
        conn: Database connection
        
    Returns:
        bool: True if the database is properly set up, False otherwise
    """
    cursor = conn.cursor()
    
    # Check if tables exist
    tables_to_check = ['player_stats', 'player_game_logs']
    missing_tables = []
    
    for table in tables_to_check:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cursor.fetchone():
            missing_tables.append(table)
    
    if missing_tables:
        print("\nERROR: The following tables are missing from the database:")
        for table in missing_tables:
            print(f"  - {table}")
        print("\nYou need to run the initial scraping process first:")
        print("  python nba_scraper.py")
        print("  python post_scraper.py")
        print("  python calc_fpts.py")
        return False
    
    # Check if tables have data
    empty_tables = []
    for table in tables_to_check:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        if count == 0:
            empty_tables.append(table)
    
    if empty_tables:
        print("\nERROR: The following tables exist but have no data:")
        for table in empty_tables:
            print(f"  - {table}")
        print("\nYou need to run the initial scraping process first:")
        print("  python nba_scraper.py")
        print("  python post_scraper.py")
        print("  python calc_fpts.py")
        return False
    
    return True

def check_games_today():
    """
    Check if there are any NBA games scheduled for today.
    
    Returns:
        tuple: (bool, str) - Whether games are scheduled and a message
    """
    # Get current date in US Pacific time
    pacific_now = get_us_pacific_time()
    today = pacific_now.replace(tzinfo=None)  # Remove timezone info
    
    url = f"https://www.basketball-reference.com/boxscores/?month={today.month}&day={today.day}&year={today.year}"
    
    try:
        print(f"Checking for games today (US Pacific: {today.strftime('%Y-%m-%d')}) at URL: {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return False, f"Error: Got status code {response.status_code} for {url}"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for game summaries or schedule table
        game_summaries = soup.find_all('div', class_='game_summary')
        schedule_table = soup.find('table', id='schedule')
        
        if game_summaries:
            games_count = len(game_summaries)
            return True, f"Found {games_count} games scheduled for today (US Pacific: {today.strftime('%Y-%m-%d')})"
        elif schedule_table:
            rows = schedule_table.find_all('tr')
            games_count = len(rows) - 1  # Subtract header row
            if games_count > 0:
                return True, f"Found {games_count} games scheduled for today (US Pacific: {today.strftime('%Y-%m-%d')})"
        
        # Check if there's a message about no games
        no_games_msg = soup.find(string=lambda text: 'no games' in text.lower() if text else False)
        if no_games_msg:
            return False, f"No games scheduled for today (US Pacific: {today.strftime('%Y-%m-%d')})"
            
        return False, f"No games found for today (US Pacific: {today.strftime('%Y-%m-%d')})"
        
    except Exception as e:
        return False, f"Error checking for games today: {str(e)}"

def main():
    # Add command-line arguments
    parser = argparse.ArgumentParser(description='NBA Incremental Update')
    parser.add_argument('--remove-inactive', action='store_true', 
                        help='Remove inactive players from the database')
    parser.add_argument('--check-all', action='store_true',
                        help='Check all players, not just those from teams with recent games')
    parser.add_argument('--force', action='store_true',
                        help='Force update even if no games are scheduled for today')
    parser.add_argument('--batch-size', type=int, default=500,
                        help='Batch size for processing fantasy points (default: 500)')
    args = parser.parse_args()
    
    start_time = datetime.now()
    print(f"Starting incremental update at {start_time}")
    
    # Check if there are games today
    if not args.force:
        games_today, message = check_games_today()
        print(message)
        
        if not games_today:
            print("\nNo games scheduled for today. If you want to run the update anyway, use --force")
            print("Exiting...")
            return
    
    # Connect to database with timeout to prevent locking issues
    conn = None
    try:
        # Set a 60-second timeout for database operations
        conn = sqlite3.connect('nba_stats.db', timeout=60.0)
        
        # Check if database is properly set up
        if not check_database_setup(conn):
            return
        
        # Get all player URLs
        all_player_urls = get_existing_player_urls()
        print(f"Got {len(all_player_urls)} existing player URLs at {datetime.now()}")
        
        # Filter players by teams with recent games, unless --check-all is specified
        player_urls = all_player_urls
        if not args.check_all:
            recent_teams = get_recent_games(conn)
            player_urls = filter_players_by_recent_teams(conn, all_player_urls, recent_teams)
        
        # Get and store new games
        new_games, inactive_players = get_latest_games(conn, player_urls)
        print(f"Added {new_games} new games to the database at {datetime.now()}")

        # Process new games only if we found any
        if new_games > 0:
            print(f"Processing new games with batch size of {args.batch_size}...")
            processed_games = process_new_games(conn, batch_size=args.batch_size)
            print(f"Processed {processed_games} new games at {datetime.now()}")
        else:
            print("No new games found, skipping processing step")
        
        # Report inactive players
        if inactive_players:
            print("\nThe following players don't have current season data:")
            for player_name, url in inactive_players:
                print(f"- {player_name} ({url})")
            
            # Remove inactive players if requested
            if args.remove_inactive:
                print("\nRemoving inactive players from database...")
                removed_count = remove_inactive_players(conn, inactive_players)
                print(f"Removed {removed_count} inactive players from database")
            else:
                print("\nYou may want to consider removing these players from your database or updating their URLs.")
                print("Run with --remove-inactive to automatically remove them.")
    
    except Exception as e:
        print(f"Error in incremental update: {str(e)}")
        import traceback
        print(f"Full stack trace:\n{traceback.format_exc()}")
    finally:
        if conn:
            conn.close()
    
    elapsed_time = datetime.now() - start_time
    print(f"Total elapsed time: {elapsed_time}")
    print(f"Completed incremental update at {datetime.now()}")

if __name__ == "__main__":
    main() 