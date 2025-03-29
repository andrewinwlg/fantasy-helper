import sqlite3
from nba_scraper import scrape_player_game_log

def test_scrape_cole_anthony():
    """
    Test scraping Cole Anthony's game logs with the updated function.
    """
    # Cole Anthony's player URL
    player_url = '/players/a/anthoco01.html'
    
    print(f"Testing scrape_player_game_log for Cole Anthony ({player_url})...")
    
    # Scrape the game logs
    game_logs = scrape_player_game_log(player_url)
    
    if game_logs is None:
        print("Failed to scrape game logs!")
        return False
    
    print(f"Successfully scraped {len(game_logs)} game logs!")
    print("\nSample data (first 5 rows):")
    print(game_logs.head(5))
    
    # Test inserting into the database
    print("\nTesting database insertion...")
    conn = None
    try:
        conn = sqlite3.connect('nba_stats.db')
        cursor = conn.cursor()
        
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        # Save to database
        game_logs.to_sql('test_game_logs', conn, if_exists='replace', index=False)
        
        # Query to confirm
        cursor.execute("SELECT COUNT(*) FROM test_game_logs")
        count = cursor.fetchone()[0]
        print(f"Successfully inserted {count} rows into test_game_logs table")
        
        # Commit the transaction
        conn.commit()
        
        # Clean up
        cursor.execute("DROP TABLE test_game_logs")
        conn.commit()
        
        print("Test completed successfully!")
        return True
    except Exception as e:
        print(f"Error during database test: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    test_scrape_cole_anthony() 