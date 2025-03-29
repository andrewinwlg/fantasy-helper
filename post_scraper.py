import sqlite3
import sys

import pandas as pd


def clean_player_game_logs(incremental: bool = False) -> None:
    """
    Clean player game logs and save to database.
    
    Args:
        incremental: If True, only insert new rows. If False, replace entire table.
    """
    print(f"Starting clean_player_game_logs with incremental={incremental}...")
    
    # Set a timeout to prevent locking issues
    conn = sqlite3.connect('nba_stats.db', timeout=60.0)
    
    try:
        # Load raw game logs - use player_game_logs directly
        print("Loading raw game logs from database...")
        df = pd.read_sql('SELECT * FROM player_game_logs', conn)
        
        print(f"Loaded {len(df)} raw game logs")
        
        # Clean the data
        print("Cleaning game logs...")
        df = clean_game_logs(df)
        
        # Update clean_game_logs table
        print("Updating clean_game_logs table...")
        update_clean_game_logs(df, conn, incremental)
        
        # Create/update views
        print("Creating/updating analysis views...")
        create_analysis_views(conn)
        
        print("Finished clean_player_game_logs successfully")
        
    except Exception as e:
        print(f"Error in clean_player_game_logs: {str(e)}")
        import traceback
        print(f"Full stack trace:\n{traceback.format_exc()}")
    finally:
        conn.close()

def clean_game_logs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and transform the player_game_logs table data:
    - Convert numeric columns from TEXT to proper numeric types
    - Clean up the home/away indicator
    - Format dates consistently
    - Split game result into result and margin columns
    """
    # Convert numeric columns to proper types
    numeric_columns = ['PTS', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 
                      'FG', 'FGA', 'FGPct', '3P', '3PA', '3PPct',
                      'FT', 'FTA', 'FTPct', 'ORB', 'DRB', 'GmSc', '+_-']
    
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Clean up home/away indicator
    df['is_home'] = (df['Unnamed:_5'] != '@').astype(int)
    
    # Format dates
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Split game result into result and margin
    df['game_result'] = df['Unnamed:_7'].str[0]  # Get first character (W or L)
    # Extract number from parentheses and convert to int
    df['game_margin'] = df['Unnamed:_7'].str.extract(r'\(([+-]?\d+)\)').astype(float)
    # Make margin negative for losses
    df.loc[df['game_result'] == 'L', 'game_margin'] *= -1
    
    # Drop unnecessary columns
    columns_to_drop = ['Unnamed:_5', 'Unnamed:_7', 'Rk']
    df = df.drop(columns=columns_to_drop)
    
    return df

def update_clean_game_logs(df: pd.DataFrame, conn: sqlite3.Connection, incremental: bool = False) -> None:
    """
    Update clean_game_logs table with cleaned data.
    
    Args:
        df: DataFrame with cleaned game log data
        conn: Database connection
        incremental: If True, only insert new rows. If False, replace entire table.
    """
    if not incremental:
        # Full refresh - replace entire table
        df.to_sql('clean_game_logs', conn, if_exists='replace', index=False)
        print(f"Replaced clean_game_logs with {len(df)} rows")
        return
        
    # Incremental update - only insert new rows
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    df.head(0).to_sql('clean_game_logs', conn, if_exists='append', index=False)
    
    # More efficient way to get new rows using SQL
    print(f"Total rows in dataframe: {len(df)}")
    
    # Convert dates to strings for consistency
    if 'Date' in df.columns and pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    
    # Use a temporary table approach for better performance
    print("Creating temporary table...")
    temp_table = 'temp_new_game_logs'
    df.to_sql(temp_table, conn, if_exists='replace', index=False)
    
    # Use SQL to insert only the new rows
    print("Finding and inserting new rows...")
    insert_query = f"""
    INSERT INTO clean_game_logs
    SELECT t.*
    FROM {temp_table} t
    LEFT JOIN clean_game_logs c ON 
        c.player_url = t.player_url AND 
        c.Date = t.Date
    WHERE c.player_url IS NULL
    """
    cursor.execute(insert_query)
    inserted_count = cursor.rowcount
    
    # Drop the temporary table
    cursor.execute(f"DROP TABLE {temp_table}")
    
    # Commit changes
    conn.commit()
    
    print(f"Added {inserted_count} new rows to clean_game_logs")

def create_analysis_views(conn: sqlite3.Connection) -> None:
    """Create useful views for analysis."""
    # Player averages view
    conn.execute("""
    CREATE VIEW IF NOT EXISTS player_averages AS
    SELECT 
        ps.Player,
        ROUND(AVG(cgl.PTS), 1) as PPG,
        ROUND(AVG(cgl.TRB), 1) as RPG,
        ROUND(AVG(cgl.AST), 1) as APG,
        ROUND(AVG(cgl.STL), 1) as SPG,
        ROUND(AVG(cgl.BLK), 1) as BPG,
        ROUND(AVG(CASE WHEN game_result = 'W' THEN 1 ELSE 0 END) * 100, 1) as Win_Pct,
        ROUND(AVG(game_margin), 1) as Avg_Margin,
        COUNT(*) as Games_Played
    FROM clean_game_logs cgl
    JOIN player_stats ps ON ps.player_url = cgl.player_url
    GROUP BY ps.Player, cgl.player_url
    HAVING Games_Played >= 10
    """)
    
    # Home vs Away splits view
    conn.execute("""
    CREATE VIEW IF NOT EXISTS home_away_splits AS
    SELECT 
        ps.Player,
        ROUND(AVG(CASE WHEN is_home = 1 THEN PTS END), 1) as Home_PPG,
        ROUND(AVG(CASE WHEN is_home = 0 THEN PTS END), 1) as Away_PPG,
        ROUND(AVG(CASE WHEN is_home = 1 AND game_result = 'W' THEN 1 
                      WHEN is_home = 1 THEN 0 END) * 100, 1) as Home_Win_Pct,
        ROUND(AVG(CASE WHEN is_home = 0 AND game_result = 'W' THEN 1 
                      WHEN is_home = 0 THEN 0 END) * 100, 1) as Away_Win_Pct,
        COUNT(*) as Games_Played
    FROM clean_game_logs cgl
    JOIN player_stats ps ON ps.player_url = cgl.player_url
    GROUP BY ps.Player, cgl.player_url
    HAVING Games_Played >= 10
    """)
    
    print("\nCreated/updated the following views:")
    print("- player_averages: Season averages for each player (including win % and margin)")
    print("- home_away_splits: Home vs Away splits (including win %)")

if __name__ == "__main__":
    # Check if running incrementally
    incremental = len(sys.argv) > 1 and sys.argv[1] == '--incremental'
    clean_player_game_logs(incremental) 