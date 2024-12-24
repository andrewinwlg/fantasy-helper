import argparse
import sqlite3
import time
import traceback
from datetime import datetime

import pandas as pd
from unidecode import unidecode

# Map from basketball reference names to nba.com names
NAME_MAPPINGS = {
    'Alex Sarr': 'Alexandre Sarr',
    'Robert Williams': 'Robert Williams III',
    'Ron Holland': 'Ronald Holland II',
    'Xavier Tillman Sr.': 'Xavier Tillman',
    'Ronald Holland' : 'Ronald Holland II',
    'Tristan Da Silva' : 'Tristan da Silva',
    'KJ Martin' : 'Kenyon Martin Jr.',
    'Craig Porter Jr.' : 'Craig Porter',
    'Cui Yongxi' : 'Yongxi Cui',
    'KJ Simpson' : 'K.J. Simpson'
}

def normalize_player_name(name):
    """Normalize player names to match between data sources"""
    # Remove accents and convert to ASCII
    name = unidecode(name)
    
    # Check direct mapping first
    if name in NAME_MAPPINGS:
        return NAME_MAPPINGS[name]
    
    return name.strip()

def scrape_nba_players():
    try:
        # URL of the NBA stats page
        url = "https://www.basketball-reference.com/leagues/NBA_2025_per_game.html"
        
        # Read HTML tables from the webpage with links
        df_with_links = pd.read_html(url, extract_links="body")[0]
        
        # Extract the data and links separately
        df = pd.DataFrame()
        # Process each column in the dataframe that was scraped from basketball-reference.com
        for column in df_with_links.columns:
            # Some columns contain tuples of (display_text, href_link) from the HTML table
            # For example, Player column has ("LeBron James", "/players/j/jamesle01.html")
            if isinstance(df_with_links[column].iloc[0], tuple):
                # For all tuple columns, take just the display text [0] as the column value
                df[column] = df_with_links[column].apply(lambda x: unidecode(x[0]))  # Convert to ASCII
                
                # For the Player column specifically, also save the URL [1] to a new player_url column
                # This URL will be used later to scrape individual player game logs
                if column == 'Player':  
                    # Normalize the player names
                    df[column] = df_with_links[column].apply(lambda x: normalize_player_name(x[0]))
                    df['player_url'] = df_with_links[column].apply(lambda x: x[1])
            else:
                # For regular columns that don't have links (like points, rebounds etc)
                # Just copy the values directly
                df[column] = df_with_links[column]
        
        # Clean the data
        df = df[df['Rk'].notna()]
        df = df.drop('Rk', axis=1)
        
        # Remove non-player rows
        df = df[~df['Player'].isin(['League Average'])]
        
        # Handle traded players
        print("\nHandling traded players...")
        players_with_multiple_teams = df[df.duplicated(['Player'], keep=False)]['Player'].unique()
        print(f"Found {len(players_with_multiple_teams)} players with multiple entries:")

        for player in players_with_multiple_teams:
            player_rows = df[df['Player'] == player]
            print(f"\nProcessing {player}:")
            print(f"Teams: {player_rows['Team'].tolist()}")
            
            # Check if any row contains '2TM' or '3TM'
            multi_team_mask = player_rows['Team'].str.contains('TM', na=False)
            if any(multi_team_mask):
                print(f"Found multi-team entry for {player}")
                # Get the player's URL
                player_url = player_rows.iloc[0]['player_url']
                # Get their most recent team from game logs
                last_team = get_last_team_from_logs(player_url)
                if last_team:
                    print(f"Got last team from logs: {last_team}")
                    # Get the combined stats row
                    combined_stats = player_rows[multi_team_mask].iloc[0]
                    # Update the team in the combined stats
                    combined_stats['Team'] = last_team
                    # Remove all rows for this player
                    df = df[df['Player'] != player]
                    # Add back the combined stats with correct team
                    df = pd.concat([df, pd.DataFrame([combined_stats])], ignore_index=True)
                    print(f"Updated {player} with team {last_team}")
                else:
                    print(f"Failed to get last team for {player}")
            else:
                print(f"No multi-team entry found for {player}")
        
        # Clean column names and add timestamp
        df.columns = df.columns.str.replace('%', 'Pct')
        df.columns = df.columns.str.replace(' ', '_')
        df.columns = df.columns.str.replace('/', '_')
        df['timestamp'] = datetime.now()
        
        return df
        
    except Exception as e:
        print(f"Error message: {str(e)}")
        print(f"Full stack trace:\n{traceback.format_exc()}")
        return None

def get_existing_player_urls():
    try:
        conn = sqlite3.connect('nba_stats.db')
        query = "SELECT DISTINCT player_url FROM player_game_logs"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return set(df['player_url'].tolist())
    except:
        return set()  # Return empty set if table doesn't exist

def scrape_player_game_log(player_url):
    try:
        base_url = "https://www.basketball-reference.com"
        game_log_url = player_url.replace('.html', '/gamelog/2025')
        full_url = base_url + game_log_url
        
        # Add 2-second delay before each request
        time.sleep(2)
        
        game_log = pd.read_html(full_url)[7]  # Index 7 typically contains regular season game log
        
        # Clean the data
        game_log = game_log[game_log['Date'] != 'Date']  # Remove header rows
        game_log = game_log[game_log['Rk'].notna()]     # Remove separator rows
        
        # Clean column names
        game_log.columns = game_log.columns.str.replace('%', 'Pct')
        game_log.columns = game_log.columns.str.replace(' ', '_')
        game_log.columns = game_log.columns.str.replace('/', '_')
        
        # Add metadata
        game_log['player_url'] = player_url
        game_log['timestamp'] = datetime.now()
        
        return game_log
    
    except Exception as e:
        print(f"Error message: {str(e)}")
        print(f"Full stack trace:\n{traceback.format_exc()}")
        return None

def save_to_database(df, table_name, if_exists='replace'):
    try:
        conn = sqlite3.connect('nba_stats.db')
        df.to_sql(table_name, conn, if_exists=if_exists, index=False)
        print(f"Data successfully saved to {table_name} table!")
        conn.close()
    except Exception as e:
        print(f"Error message: {str(e)}")
        print(f"Full stack trace:\n{traceback.format_exc()}")

def process_game_logs(df):
    # Get existing player URLs from database
    existing_urls = get_existing_player_urls()
    
    # Get total number of players
    total_players = len(df)
    processed_count = 0
    batch_count = 0
    
    # Process players in batches of 10
    for i in range(0, total_players, 10):
        batch = df.iloc[i:min(i+10, total_players)]
        batch_processed = 0
        
        for _, row in batch.iterrows():
            if pd.notna(row['player_url']):
                # Skip if player already exists in database
                if row['player_url'] in existing_urls:
                    print(f"Skipping {row['Player']} - data already exists")
                    continue
                
                game_log = scrape_player_game_log(row['player_url'])
                if game_log is not None:
                    save_to_database(game_log, 'player_game_logs', 'append')
                    processed_count += 1
                    batch_processed += 1
        
        # Print progress message after each batch
        players_processed = min(i+10, total_players)
        print(f"Successfully processed {players_processed} out of {total_players} players")
        
        batch_count += 1
        if batch_count % 10 == 0:
            print("Taking a 10-second break...")
            time.sleep(10)  # 10-second break every 10 batches
        elif batch_processed > 0:  # Only delay if we actually processed players
            print("Taking a 2-second break...")
            time.sleep(2)  # 2-second break between batches

def get_last_team_from_logs(player_url):
    """Get a player's most recent team from their game logs"""
    try:
        base_url = "https://www.basketball-reference.com"
        game_log_url = player_url.replace('.html', '/gamelog/2025')
        full_url = base_url + game_log_url
        
        # Get game logs and sort by date
        game_log = pd.read_html(full_url)[7]
        
        # Print columns for debugging
        print(f"Game log columns: {game_log.columns.tolist()}")
        
        game_log = game_log[game_log['Date'] != 'Date']  # Remove header rows
        game_log = game_log.sort_values('Date', ascending=False)
        
        # Get team from most recent game using 'Tm' column
        last_team = game_log.iloc[0]['Tm']
            
        print(f"Found last team: {last_team}")
        return last_team
        
    except Exception as e:
        print(f"Error getting last team for {player_url}: {str(e)}")
        print(f"Full URL: {full_url}")
        print(f"Full stack trace:\n{traceback.format_exc()}")
        return None

def main():
    parser = argparse.ArgumentParser(description='NBA Stats Scraper')
    parser.add_argument('--players', action='store_true', help='Scrape only player stats')
    parser.add_argument('--logs', action='store_true', help='Scrape only game logs')
    parser.add_argument('--all', action='store_true', help='Scrape everything (default)')
    
    args = parser.parse_args()
    
    # If no args specified, default to --all
    if not (args.players or args.logs or args.all):
        args.all = True
    
    print(f"\nStarting NBA scraper at {datetime.now()}")
    
    if args.all or args.players:
        print("\nScraping player stats...")
        df = scrape_nba_players()

        if df is not None:
            print(f"Successfully scraped data for {len(df)} players")
            save_to_database(df, 'player_stats')
        else:
            print("Failed to scrape data")    
    
    if args.all or args.logs:
        # Now process game logs
        print("\nStarting to scrape individual player game logs...")
        # Get player data from database since df may not be defined if only --logs flag is used
        df = pd.read_sql('SELECT * FROM player_stats', sqlite3.connect('nba_stats.db'))
        process_game_logs(df)
        print("\nCompleted scraping all player game logs!")
    
    print(f"\nFinished at {datetime.now()}")

if __name__ == "__main__":
    main()