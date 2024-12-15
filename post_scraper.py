import sqlite3
import pandas as pd

def clean_player_game_logs():
    """
    Clean and transform the player_game_logs table data:
    - Convert numeric columns from TEXT to proper numeric types
    - Clean up the home/away indicator
    - Format dates consistently
    - Split game result into result and margin columns
    """
    conn = sqlite3.connect('nba_stats.db')
    
    # Read the current data
    query = """
    SELECT * FROM player_game_logs
    """
    df = pd.read_sql_query(query, conn)
    
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
    
    # Save the cleaned data to a new table
    df.to_sql('clean_game_logs', conn, if_exists='replace', index=False)
    
    print("Created clean_game_logs table with the following improvements:")
    print("- Converted numeric columns to proper types")
    print("- Added is_home column (1 for home games, 0 for away)")
    print("- Split game results into game_result (W/L) and game_margin columns")
    print("- Formatted dates as datetime")
    print("- Removed unnecessary columns")
    
    # Create some useful views for analysis
    
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
    
    print("\nCreated the following views:")
    print("- player_averages: Season averages for each player (including win % and margin)")
    print("- home_away_splits: Home vs Away splits (including win %)")
    
    conn.close()

if __name__ == "__main__":
    clean_player_game_logs() 