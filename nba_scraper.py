import argparse
import sqlite3
import time
from datetime import datetime

import pandas as pd
from unidecode import unidecode


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
                    df['player_url'] = df_with_links[column].apply(lambda x: x[1])
            else:
                # For regular columns that don't have links (like points, rebounds etc)
                # Just copy the values directly
                df[column] = df_with_links[column]
        
        # Clean the data
        df = df[df['Rk'].notna()]
        df = df.drop('Rk', axis=1)
        
        # Clean column names
        df.columns = df.columns.str.replace('%', 'Pct')
        df.columns = df.columns.str.replace(' ', '_')
        df.columns = df.columns.str.replace('/', '_')
        
        # Add timestamp
        df['timestamp'] = datetime.now()
        
        return df
    
    except Exception as e:
        print(f"Error scraping data: {str(e)}")
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
        print(f"Error scraping game log for {player_url}: {str(e)}")
        return None

def save_to_database(df, table_name, if_exists='replace'):
    try:
        conn = sqlite3.connect('nba_stats.db')
        df.to_sql(table_name, conn, if_exists=if_exists, index=False)
        print(f"Data successfully saved to {table_name} table!")
        conn.close()
    except Exception as e:
        print(f"Error saving to database: {str(e)}")

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
        scrape_nba_players()

        if df is not None:
            print(f"Successfully scraped data for {len(df)} players")
            save_to_database(df, 'player_stats')
        else:
            print("Failed to scrape data")    
    
    if args.all or args.logs:
        # Now process game logs
        print("\nStarting to scrape individual player game logs...")
        process_game_logs(df)
        print("\nCompleted scraping all player game logs!")
    
    print(f"\nFinished at {datetime.now()}")

if __name__ == "__main__":
    main()