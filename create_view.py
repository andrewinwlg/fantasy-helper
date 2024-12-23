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
        SELECT 
            ps.Player,
            ps.Team as Team,
            nsc.salary as Salary,
            nsc.avgPoints as Fantasy_Points_Per_Game,
            nsc.totalPoints as Total_Fantasy_Points,
            nsc.ownership as Ownership_Percentage,
            ROUND(nsc.avgPoints * 1000.0 / NULLIF(nsc.salary, 0), 2) as Value_Per_Game,
            ROUND(nsc.totalPoints * 1000.0 / NULLIF(nsc.salary, 0), 2) as Total_Value
        FROM player_stats ps
        LEFT JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
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

if __name__ == "__main__":
    create_player_stats_view() 