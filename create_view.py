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
                -- 7 day stats
                AVG(CASE WHEN pgl.Date >= date('now', '-7 days')
                    THEN CAST(pgl.PTS as FLOAT) * 1.0 +
                         CAST(pgl.TRB as FLOAT) * 1.2 +
                         CAST(pgl.AST as FLOAT) * 1.5 +
                         CAST(pgl.BLK as FLOAT) * 3.0 +
                         CAST(pgl.STL as FLOAT) * 3.0 +
                         CAST(pgl.TOV as FLOAT) * -1.0
                    END) as last_7d_fpts,
                COUNT(CASE WHEN pgl.Date >= date('now', '-7 days') 
                    THEN 1 END) as games_last_7d,
                
                -- 15 day stats
                AVG(CASE WHEN pgl.Date >= date('now', '-15 days')
                    THEN CAST(pgl.PTS as FLOAT) * 1.0 +
                         CAST(pgl.TRB as FLOAT) * 1.2 +
                         CAST(pgl.AST as FLOAT) * 1.5 +
                         CAST(pgl.BLK as FLOAT) * 3.0 +
                         CAST(pgl.STL as FLOAT) * 3.0 +
                         CAST(pgl.TOV as FLOAT) * -1.0
                    END) as last_15d_fpts,
                COUNT(CASE WHEN pgl.Date >= date('now', '-15 days') 
                    THEN 1 END) as games_last_15d,
                
                -- 30 day stats
                AVG(CASE WHEN pgl.Date >= date('now', '-30 days')
                    THEN CAST(pgl.PTS as FLOAT) * 1.0 +
                         CAST(pgl.TRB as FLOAT) * 1.2 +
                         CAST(pgl.AST as FLOAT) * 1.5 +
                         CAST(pgl.BLK as FLOAT) * 3.0 +
                         CAST(pgl.STL as FLOAT) * 3.0 +
                         CAST(pgl.TOV as FLOAT) * -1.0
                    END) as last_30d_fpts,
                COUNT(CASE WHEN pgl.Date >= date('now', '-30 days') 
                    THEN 1 END) as games_last_30d
            FROM player_game_logs pgl
            GROUP BY pgl.player_url
        )
        SELECT 
            ps.Player,
            ps.Team as Team,
            nsc.salary as Salary,
            nsc.avgPoints as Fantasy_Points_Per_Game,
            -- 7 day stats
            COALESCE(rg.last_7d_fpts, 0) as Fantasy_Points_Per_Game_7D,
            COALESCE(rg.games_last_7d, 0) as Games_Last_7D,
            ROUND(COALESCE(rg.last_7d_fpts, 0) / NULLIF(nsc.salary, 0), 2) as Value_Per_Game_7D,
            -- 15 day stats
            COALESCE(rg.last_15d_fpts, 0) as Fantasy_Points_Per_Game_15D,
            COALESCE(rg.games_last_15d, 0) as Games_Last_15D,
            ROUND(COALESCE(rg.last_15d_fpts, 0) / NULLIF(nsc.salary, 0), 2) as Value_Per_Game_15D,
            -- 30 day stats
            COALESCE(rg.last_30d_fpts, 0) as Fantasy_Points_Per_Game_30D,
            COALESCE(rg.games_last_30d, 0) as Games_Last_30D,
            ROUND(COALESCE(rg.last_30d_fpts, 0) / NULLIF(nsc.salary, 0), 2) as Value_Per_Game_30D,
            -- Other stats
            nsc.totalPoints as Total_Fantasy_Points,
            nsc.ownership as Ownership_Percentage,
            ROUND(nsc.avgPoints / NULLIF(nsc.salary, 0), 2) as Value_Per_Game
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