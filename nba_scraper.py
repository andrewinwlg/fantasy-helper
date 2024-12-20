import pandas as pd
import sqlite3
from datetime import datetime
import time

def scrape_nba_stats():
    try:
        # URL of the NBA stats page
        url = "https://www.basketball-reference.com/leagues/NBA_2025_per_game.html"
        
        # Read HTML tables from the webpage with links
        df_with_links = pd.read_html(url, extract_links="body")[0]
        
        # Extract the data and links separately
        df = pd.DataFrame()
        for column in df_with_links.columns:
            # If the column contains tuples (data, link), separate them
            if isinstance(df_with_links[column].iloc[0], tuple):
                df[column] = df_with_links[column].apply(lambda x: x[0])  # Get the data
                if column == 'Player':  # Only keep URLs for the Player column
                    df['player_url'] = df_with_links[column].apply(lambda x: x[1])  # Get the link
            else:
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
    # First get the main player stats
    print("Scraping NBA stats...")
    df = scrape_nba_stats()
    
    if df is not None:
        print(f"Successfully scraped data for {len(df)} players")
        save_to_database(df, 'player_stats')
        
        # Now process game logs
        print("\nStarting to scrape individual player game logs...")
        process_game_logs(df)
        print("\nCompleted scraping all player game logs!")
    else:
        print("Failed to scrape data")

if __name__ == "__main__":
    main()