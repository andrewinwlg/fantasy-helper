import sqlite3
import pandas as pd

def calculate_fantasy_points():
    """
    Add fantasy points calculations to clean_game_logs table:
    - ESPN fantasy points
    - NBA Salary Cap game points
    """
    conn = sqlite3.connect('nba_stats.db')
    
    # Read the clean game logs
    query = """
    SELECT * FROM clean_game_logs
    """
    df = pd.read_sql_query(query, conn)
    
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
    
    # Save updated data back to clean_game_logs
    df.to_sql('clean_game_logs', conn, if_exists='replace', index=False)
    
    print("Added fantasy points calculations to clean_game_logs:")
    print("- espn_fpts: ESPN fantasy points")
    print("- nba_salary_cap_fpts: NBA Salary Cap game points")
    
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
    
    print("\nCreated the following views:")
    print("- fantasy_averages: Average and max fantasy points for each player")
    print("- fantasy_home_away_splits: Home vs Away fantasy points splits")
    
    conn.close()

if __name__ == "__main__":
    calculate_fantasy_points() 