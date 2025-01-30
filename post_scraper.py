import sqlite3
import sys

import pandas as pd


def clean_player_game_logs(incremental: bool = False) -> None:
    """
    Clean player game logs and save to database.
    
    Args:
        incremental: If True, only insert new rows. If False, replace entire table.
    """
    conn = sqlite3.connect('nba_stats.db')
    
    try:
        # Load raw game logs - use player_game_logs directly
        df = pd.read_sql('SELECT * FROM player_game_logs', conn)
        
        # Clean the data
        df = clean_game_logs(df)
        
        # Update clean_game_logs table
        update_clean_game_logs(df, conn, incremental)
        
        # Create/update views
        create_analysis_views(conn)
        
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
    
    # Get existing game/player combinations
    cursor.execute("""
        SELECT Player, Game_Date 
        FROM clean_game_logs
    """)
    existing = {(player, date) for player, date in cursor.fetchall()}
    
    # Filter to only new rows
    df['key'] = list(zip(df['Player'], df['Game_Date']))
    new_rows = df[~df['key'].isin(existing)]
    new_rows = new_rows.drop('key', axis=1)
    
    # Insert new rows
    if len(new_rows) > 0:
        new_rows.to_sql('clean_game_logs', conn, if_exists='append', index=False)
        print(f"Added {len(new_rows)} new rows to clean_game_logs")
    else:
        print("No new rows to add to clean_game_logs")

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