import sqlite3
import pandas as pd

def ensure_fantasy_columns_exist(conn):
    """
    Ensures the fantasy points columns exist in clean_game_logs table
    """
    try:
        # Check if columns exist
        cursor = conn.execute('SELECT espn_fpts, nba_salary_cap_fpts FROM clean_game_logs LIMIT 1')
    except sqlite3.OperationalError:
        print("Adding fantasy points columns to clean_game_logs table...")
        conn.execute('ALTER TABLE clean_game_logs ADD COLUMN espn_fpts REAL')
        conn.execute('ALTER TABLE clean_game_logs ADD COLUMN nba_salary_cap_fpts REAL')
        conn.commit()
        print("Added fantasy points columns")

def calculate_fantasy_points():
    """
    Add fantasy points calculations to clean_game_logs table:
    - ESPN fantasy points
    - NBA Salary Cap game points
    Only processes rows that don't already have fantasy points calculated
    """
    conn = sqlite3.connect('nba_stats.db')
    
    # Ensure fantasy points columns exist
    ensure_fantasy_columns_exist(conn)
    
    # Read only the clean game logs that don't have fantasy points calculated
    query = """
    SELECT * FROM clean_game_logs
    WHERE espn_fpts IS NULL 
    OR nba_salary_cap_fpts IS NULL
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("No new games to process")
        conn.close()
        return
    
    print(f"Calculating fantasy points for {len(df)} new games...")
    
    # Calculate ESPN fantasy points
    df['espn_fpts'] = (
        df['3P'] * 1 +           # Three pointers made
        df['FGA'] * -1 +         # Field goal attempts
        df['FG'] * 2 +           # Field goals made
        df['FTA'] * -1 +         # Free throw attempts
        df['FT'] * 1 +           # Free throws made
        df['TRB'] * 1 +          # Total rebounds
        df['AST'] * 2 +          # Assists
        df['STL'] * 4 +          # Steals
        df['BLK'] * 4 +          # Blocks
        df['TOV'] * -2           # Turnovers
    )
    
    # Calculate NBA Salary Cap fantasy points
    df['nba_salary_cap_fpts'] = (
        df['PTS'] * 1 +          # Points
        df['TRB'] * 1.2 +        # Rebounds
        df['AST'] * 1.5 +        # Assists
        df['BLK'] * 3 +          # Blocks
        df['STL'] * 3 +          # Steals
        df['TOV'] * -1           # Turnovers
    )
    
    # Update only the new rows in clean_game_logs
    for _, row in df.iterrows():
        update_query = """
        UPDATE clean_game_logs 
        SET espn_fpts = ?, nba_salary_cap_fpts = ?
        WHERE player_url = ? AND G = ?
        """
        conn.execute(update_query, (
            row['espn_fpts'], 
            row['nba_salary_cap_fpts'],
            row['player_url'],
            row['G']
        ))
    
    conn.commit()
    
    print(f"Added fantasy points calculations for {len(df)} games")
    
    # Refresh the views
    conn.execute("DROP VIEW IF EXISTS fantasy_averages")
    conn.execute("DROP VIEW IF EXISTS fantasy_home_away_splits")
    
    # Create fantasy points averages view
    conn.execute("""
    CREATE VIEW IF NOT EXISTS fantasy_averages AS
    SELECT 
        ps.Player,
        AVG(cgl.espn_fpts) as ESPN_Avg_FPTS,
        AVG(cgl.nba_salary_cap_fpts) as NBA_Cap_Avg_FPTS,
        MAX(cgl.espn_fpts) as ESPN_Max_FPTS,
        MAX(cgl.nba_salary_cap_fpts) as NBA_Cap_Max_FPTS,
        COUNT(*) as Games_Played
    FROM clean_game_logs cgl
    JOIN player_stats ps ON ps.player_url = cgl.player_url
    GROUP BY ps.Player, cgl.player_url
    HAVING Games_Played >= 10
    ORDER BY ESPN_Avg_FPTS DESC
    """)
    
    # Create home/away fantasy splits view
    conn.execute("""
    CREATE VIEW IF NOT EXISTS fantasy_home_away_splits AS
    SELECT 
        ps.Player,
        AVG(CASE WHEN is_home = 1 THEN espn_fpts END) as Home_ESPN_FPTS,
        AVG(CASE WHEN is_home = 0 THEN espn_fpts END) as Away_ESPN_FPTS,
        AVG(CASE WHEN is_home = 1 THEN nba_salary_cap_fpts END) as Home_NBA_Cap_FPTS,
        AVG(CASE WHEN is_home = 0 THEN nba_salary_cap_fpts END) as Away_NBA_Cap_FPTS,
        COUNT(*) as Games_Played
    FROM clean_game_logs cgl
    JOIN player_stats ps ON ps.player_url = cgl.player_url
    GROUP BY ps.Player, cgl.player_url
    HAVING Games_Played >= 10
    ORDER BY (Home_ESPN_FPTS + Away_ESPN_FPTS)/2 DESC
    """)
    
    print("\nRefreshed the following views:")
    print("- fantasy_averages: Average and max fantasy points for each player")
    print("- fantasy_home_away_splits: Home vs Away fantasy points splits")
    
    conn.close()

if __name__ == "__main__":
    calculate_fantasy_points() 