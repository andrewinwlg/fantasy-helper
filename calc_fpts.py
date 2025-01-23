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
        df['3P'].astype(float) * 1 +           # Three pointers made
        df['FGA'].astype(float) * -1 +         # Field goal attempts
        df['FG'].astype(float) * 2 +           # Field goals made
        df['FTA'].astype(float) * -1 +         # Free throw attempts
        df['FT'].astype(float) * 1 +           # Free throws made
        df['TRB'].astype(float) * 1 +          # Total rebounds
        df['AST'].astype(float) * 2 +          # Assists
        df['STL'].astype(float) * 4 +          # Steals
        df['BLK'].astype(float) * 4 +          # Blocks
        df['TOV'].astype(float) * -2           # Turnovers
    )
    
    # Calculate NBA Salary Cap fantasy points
    df['nba_salary_cap_fpts'] = (
        df['PTS'].astype(float) * 1 +          # Points
        df['TRB'].astype(float) * 1.2 +        # Rebounds
        df['AST'].astype(float) * 1.5 +        # Assists
        df['BLK'].astype(float) * 3 +          # Blocks
        df['STL'].astype(float) * 3 +          # Steals
        df['TOV'].astype(float) * -1           # Turnovers
    )
    
    # Add some debug logging
    print("\nSample calculations:")
    sample_idx = df.index[0]
    print(f"First row stats:")
    print(f"Player: {df.loc[sample_idx, 'player_url']}")
    print(f"Game: {df.loc[sample_idx, 'G']}")
    print(f"ESPN Points: {df.loc[sample_idx, 'espn_fpts']:.2f}")
    print(f"NBA Cap Points: {df.loc[sample_idx, 'nba_salary_cap_fpts']:.2f}")
    
    # Update only the new rows in clean_game_logs
    updated_count = 0
    for _, row in df.iterrows():
        update_query = """
        UPDATE clean_game_logs 
        SET espn_fpts = ?, nba_salary_cap_fpts = ?
        WHERE player_url = ? AND G = ?
        """
        cursor = conn.execute(update_query, (
            float(row['espn_fpts']), 
            float(row['nba_salary_cap_fpts']),
            row['player_url'],
            row['G']
        ))
        updated_count += cursor.rowcount
    
    conn.commit()
    
    # Verify the update
    verify_query = """
    SELECT COUNT(*) as count 
    FROM clean_game_logs 
    WHERE espn_fpts IS NOT NULL 
    AND nba_salary_cap_fpts IS NOT NULL
    """
    cursor = conn.execute(verify_query)
    verified_count = cursor.fetchone()[0]
    
    print(f"\nUpdated {updated_count} rows")
    print(f"Total rows with fantasy points: {verified_count}")
    
    # Refresh the views
    print("\nRefreshing views...")
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
    print("Done!")

if __name__ == "__main__":
    calculate_fantasy_points() 