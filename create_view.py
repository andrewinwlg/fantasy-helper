import sqlite3


def create_player_stats_view(db_path='nba_stats.db'):
    """Create or update the player stats view with correct column names"""
    try:
        conn = sqlite3.connect(db_path)
        print("\nDropping old view if exists...")
        conn.execute("DROP VIEW IF EXISTS player_salary_stats")
        
        print("Creating new view...")
        conn.execute("""
        CREATE VIEW player_salary_stats AS
        WITH recent_games AS (
            SELECT 
                pgl.player_url,
                AVG(
                    CAST(pgl.PTS as FLOAT) * 1.0 +          -- Points
                    CAST(pgl.TRB as FLOAT) * 1.2 +          -- Rebounds
                    CAST(pgl.AST as FLOAT) * 1.5 +          -- Assists
                    CAST(pgl.BLK as FLOAT) * 3.0 +          -- Blocks
                    CAST(pgl.STL as FLOAT) * 3.0 +          -- Steals
                    CAST(pgl.TOV as FLOAT) * -1.0           -- Turnovers
                ) as last_30d_fpts,
                COUNT(pgl.Date) as games_last_30d
            FROM player_game_logs pgl
            WHERE pgl.Date >= date('now', '-30 days')
            GROUP BY pgl.player_url
        )
        SELECT 
            ps.Player,
            ps.Team as Team,
            nsc.salary as Salary,
            nsc.avgPoints as Fantasy_Points_Per_Game,
            COALESCE(rg.last_30d_fpts, 0) as Fantasy_Points_Per_Game_30D,
            COALESCE(rg.games_last_30d, 0) as Games_Last_30D,
            nsc.totalPoints as Total_Fantasy_Points,
            nsc.ownership as Ownership_Percentage,
            ROUND(nsc.avgPoints / NULLIF(nsc.salary, 0), 2) as Value_Per_Game,
            ROUND(COALESCE(rg.last_30d_fpts, 0) / NULLIF(nsc.salary, 0), 2) as Value_Per_Game_30D,
            ROUND(nsc.totalPoints / NULLIF(nsc.salary, 0), 2) as Total_Value
        FROM player_stats ps
        LEFT JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        LEFT JOIN recent_games rg ON rg.player_url = ps.player_url
        WHERE nsc.salary > 0
        ORDER BY Value_Per_Game DESC
        """)
        print("View created successfully")
        
        # Show sample data
        print("\nSample data from view:")
        cursor = conn.execute("SELECT * FROM player_salary_stats LIMIT 5")
        columns = [description[0] for description in cursor.description]
        print("Columns:", columns)
        for row in cursor:
            print(row)
            
    except Exception as e:
        print(f"Error creating view: {str(e)}")
    finally:
        conn.close()

def create_recent_stats_view(db_path='nba_stats.db'):
    try:
        conn = sqlite3.connect(db_path)
        print("\nCreating recent stats view...")
        conn.execute("""
        CREATE VIEW player_salary_recent_stats AS
        SELECT 
            ps.Player,
            ps.Team,
            nsc.salary as Salary,
            AVG(
                CAST(pgl.PTS as FLOAT) * 1.0 +          -- Points
                CAST(pgl.TRB as FLOAT) * 1.2 +          -- Rebounds
                CAST(pgl.AST as FLOAT) * 1.5 +          -- Assists
                CAST(pgl.BLK as FLOAT) * 3.0 +          -- Blocks
                CAST(pgl.STL as FLOAT) * 3.0 +          -- Steals
                CAST(pgl.TOV as FLOAT) * -1.0           -- Turnovers
            ) as Fantasy_Points_Per_Game_30D,
            COUNT(pgl.Date) as Games_Last_30D,
            nsc.ownership as Ownership_Percentage,
            ROUND(AVG(
                CAST(pgl.PTS as FLOAT) * 1.0 +
                CAST(pgl.TRB as FLOAT) * 1.2 +
                CAST(pgl.AST as FLOAT) * 1.5 +
                CAST(pgl.BLK as FLOAT) * 3.0 +
                CAST(pgl.STL as FLOAT) * 3.0 +
                CAST(pgl.TOV as FLOAT) * -1.0
            ) / NULLIF(nsc.salary, 0), 2) as Value_Per_Game_30D
        FROM player_stats ps
        LEFT JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        LEFT JOIN player_game_logs pgl ON pgl.player_url = ps.player_url
        WHERE nsc.salary > 0
        AND pgl.Date >= date('now', '-30 days')
        GROUP BY ps.Player
        ORDER BY Fantasy_Points_Per_Game_30D DESC
        """)
        print("View created successfully")
        
        # Show sample data
        print("\nSample data from view:")
        cursor = conn.execute("SELECT * FROM player_salary_recent_stats LIMIT 5")
        columns = [description[0] for description in cursor.description]
        print("Columns:", columns)
        for row in cursor:
            print(row)
            
    except Exception as e:
        print(f"Error creating view: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_player_stats_view()
    create_recent_stats_view()