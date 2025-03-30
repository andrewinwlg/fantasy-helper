import argparse
import sqlite3
import time
import traceback
import os
import requests
from bs4 import BeautifulSoup
import io
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
        query = "SELECT DISTINCT player_url FROM player_game_logs" #TODO what about injured players first game of the season?
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
        
        print(f"Fetching game log from: {full_url}")
        
        # Add 2-second delay before each request
        time.sleep(2)
        
        try:
            # First, try to save the HTML content for debugging
            if not os.path.exists("debug"):
                os.makedirs("debug")
                
            # Get the player ID from the URL
            player_id = player_url.split('/')[-1].replace('.html', '')
            
            # Fetch the page content
            response = requests.get(full_url)
            if response.status_code != 200:
                print(f"Failed to fetch page: {response.status_code}")
                return None
                
            html_content = response.text
            
            # Save the HTML for debugging
            debug_file = os.path.join("debug", f"{player_id}_gamelog.html")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Parse with BeautifulSoup first to locate the table
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for the game log table - it's usually the one with id containing 'pgl_basic'
            game_log_table = None
            for table in soup.find_all('table'):
                if table.get('id') and 'pgl_basic' in table.get('id'):
                    game_log_table = table
                    break
            
            # If we found the table directly, use pandas to parse just that table
            if game_log_table:
                print(f"Found game log table with id: {game_log_table.get('id')}")
                # Use pandas to read just this table
                game_log_html = str(game_log_table)
                game_log = pd.read_html(io.StringIO(game_log_html))[0]
            else:
                # Fallback: Try reading all tables and find the one that looks like a game log
                print("Game log table not found by ID, trying to read all tables...")
                tables = pd.read_html(full_url)
                
                # Look for a table that has the expected columns for a game log
                for i, table in enumerate(tables):
                    if 'Rk' in table.columns and 'Date' in table.columns:
                        print(f"Found game log in table {i}")
                        game_log = table
                        break
                else:
                    # If we didn't find a table with the right columns, try another approach
                    # Look for rows with game stats in the HTML
                    print("No suitable table found, trying to extract from HTML...")
                    
                    # Extract data manually from the HTML
                    rows = []
                    for tr in soup.find_all('tr'):
                        if 'data-stat' in str(tr):
                            row_data = {}
                            
                            # Check if this row has date and other key columns
                            date_td = tr.find('td', {'data-stat': 'date'})
                            if date_td and date_td.find('a'):
                                row_data['Date'] = date_td.text.strip()
                                
                                # Get other important columns
                                for td in tr.find_all('td'):
                                    stat_name = td.get('data-stat')
                                    if stat_name:
                                        row_data[stat_name] = td.text.strip()
                                
                                # If we have enough data, add this row
                                if len(row_data) > 5:  # Arbitrary threshold
                                    rows.append(row_data)
                    
                    if rows:
                        game_log = pd.DataFrame(rows)
                        print(f"Manually extracted {len(rows)} game log rows")
                    else:
                        print(f"Could not find game log data in HTML: {player_url}")
                        return None
            
            # Verify this is actually a game log by checking for key columns
            required_columns = ['Rk', 'Date', 'Tm', 'Opp']  # Changed 'Team' to 'Tm' which is more common in BR
            missing_columns = [col for col in required_columns if col not in game_log.columns]
            
            if missing_columns:
                print(f"Table is missing required columns: {missing_columns}")
                print(f"Available columns: {game_log.columns.tolist()}")
                
                # Try to map columns if possible
                column_mappings = {
                    'team_name_abbr': 'Tm',
                    'opp_name_abbr': 'Opp',
                    'ranker': 'Rk',
                    'team_game_num_season': 'Gtm',
                    'Team': 'Tm'  # Add this mapping for the specific case we're seeing
                }
                
                for old_col, new_col in column_mappings.items():
                    if old_col in game_log.columns and new_col not in game_log.columns:
                        game_log = game_log.rename(columns={old_col: new_col})
                        print(f"Mapped column {old_col} to {new_col}")
                
                # Check again after mapping
                missing_columns = [col for col in required_columns if col not in game_log.columns]
                if missing_columns:
                    print(f"Still missing required columns after mapping: {missing_columns}")
                    return None
            
            # Clean the data
            game_log = game_log[game_log['Date'] != 'Date']  # Remove header rows
            game_log = game_log[game_log['Rk'].notna()]     # Remove separator rows
            
            # Remove rows with "Did Not Play" - adjust column if needed
            did_not_play_column = 'MP' if 'MP' in game_log.columns else 'mp'
            if did_not_play_column in game_log.columns:
                did_not_play_mask = game_log[did_not_play_column].astype(str).str.contains('Did Not Play', na=False)
                if did_not_play_mask.any():
                    game_log = game_log[~did_not_play_mask]
            
            # Ensure 'Gtm' column exists (team game number)
            if 'Gtm' not in game_log.columns and 'team_game_num_season' in game_log.columns:
                game_log['Gtm'] = game_log['team_game_num_season']
            elif 'G' in game_log.columns and 'Gtm' not in game_log.columns:
                game_log['Gtm'] = game_log['G']
            
            # Clean column names
            game_log.columns = game_log.columns.str.replace('%', 'Pct')
            game_log.columns = game_log.columns.str.replace(' ', '_')
            game_log.columns = game_log.columns.str.replace('/', '_')
            
            # Add metadata
            game_log['player_url'] = player_url
            game_log['timestamp'] = datetime.now()
            
            # For debugging
            print(f"Successfully scraped game log for {player_url} with {len(game_log)} rows")
            print(f"Final columns: {', '.join(game_log.columns[:10])}... (showing first 10)")
            
            return game_log
            
        except ValueError as e:
            if "No tables found" in str(e):
                print(f"Player page doesn't exist or has no tables: {player_url}")
            else:
                print(f"Error parsing tables for {player_url}: {str(e)}")
            return None
        except IndexError as e:
            print(f"Player page exists but doesn't have the expected table structure: {player_url}")
            print(f"Error: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error for {player_url}: {str(e)}")
            print(f"Full stack trace:\n{traceback.format_exc()}")
            return None
    
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