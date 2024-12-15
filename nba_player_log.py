import pandas as pd
import sqlite3
from datetime import datetime
import time

def scrape_player_game_log(player_url, season_year=2025):
    try:
        # Convert player URL to game log URL by appending /gamelog/2025
        game_log_url = player_url.replace('.html', f'/gamelog/{season_year}')
        
        # Read the game log table
        df = pd.read_html(game_log_url)[7] # Game log is typically the 7th table
        
        # Clean the data
        # Remove rows where 'Date' is 'Date' (header rows that repeat)
        df = df[df['Date'] != 'Date']
        
        # Remove rows where 'Rk' is NaN (these are usually section separators)
        df = df[df['Rk'].notna()]
        
        # Clean column names
        df.columns = df.columns.str.replace('%', 'Pct')
        df.columns = df.columns.str.replace(' ', '_')
        df.columns = df.columns.str.replace('/', '_')
        
        # Add timestamp and player URL for reference
        df['timestamp'] = datetime.now()
        df['player_url'] = player_url
        
        return df
    
    except Exception as e:
        print(f"Error scraping game log: {str(e)}")
        return None

def save_game_logs_to_database(df):
    try:
        # Create a SQLite database connection
        conn = sqlite3.connect('nba_stats.db')
        
        # Save the dataframe to SQL
        # Append to the table if it exists
        df.to_sql('player_game_log', conn, if_exists='append', index=False)
        
        print("Game log data successfully saved to database!")
        
        conn.close()
        
    except Exception as e:
        print(f"Error saving game logs to database: {str(e)}")

def main():
    # First get the main player stats
    print("Scraping NBA stats...")
    df = scrape_nba_stats()
    
    if df is not None:
        print(f"Successfully scraped data for {len(df)} players")
        save_to_database(df)
        
        # Now scrape game logs for each player
        print("Scraping individual player game logs...")
        for idx, row in df.iterrows():
            # Get player URL from the player name column
            # You'll need to modify this based on how the URLs are structured
            player_name = row['Player']
            # Add logic here to construct proper player URL
            
            # Scrape game log
            game_log_df = scrape_player_game_log(player_url)
            
            if game_log_df is not None:
                save_game_logs_to_database(game_log_df)
            
            # Add a small delay to avoid overwhelming the server
            time.sleep(1)
    else:
        print("Failed to scrape data")

if __name__ == "__main__":
    main()