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

def calculate_fantasy_points(batch_size=1000):
    """
    Add fantasy points calculations to clean_game_logs table:
    - ESPN fantasy points
    - NBA Salary Cap game points
    Only processes rows that don't already have fantasy points calculated
    
    Args:
        batch_size: Number of rows to process in each batch
    """
    print("Starting calculate_fantasy_points...")
    
    # Set a timeout to prevent database locking issues
    conn = sqlite3.connect('nba_stats.db', timeout=60.0)
    
    try:
        # Ensure fantasy points columns exist
        print("Ensuring fantasy points columns exist...")
        ensure_fantasy_columns_exist(conn)
        
        # Read only the clean game logs that don't have fantasy points calculated
        print("Querying for games without fantasy points...")
        query = """
        SELECT * FROM clean_game_logs
        WHERE (espn_fpts IS NULL 
        OR nba_salary_cap_fpts IS NULL)
        AND MP not in ('Inactive','Did Not Play','Did Not Dress','Player Suspended','Not With Team')
        """
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print("No new games to process")
            conn.close()
            return
        
        total_rows = len(df)
        print(f"Calculating fantasy points for {total_rows} new games...")
        
        # Calculate ESPN fantasy points
        print("Calculating ESPN fantasy points...")
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
        print("Calculating NBA Salary Cap fantasy points...")
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
        
        # Process in batches
        total_batches = (total_rows + batch_size - 1) // batch_size  # Ceiling division
        updated_count = 0
        
        import signal
        import sys
        
        # Define a timeout handler
        def timeout_handler(signum, frame):
            print("\n\nTimeout reached! Stopping processing.")
            print(f"Processed {updated_count} out of {total_rows} rows.")
            conn.commit()
            sys.exit(0)
        
        # Set timeout handler for SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, timeout_handler)
        
        print(f"Processing {total_rows} rows in {total_batches} batches (batch size: {batch_size})...")
        
        cursor = conn.cursor()
        update_query = """
        UPDATE clean_game_logs 
        SET espn_fpts = ?, nba_salary_cap_fpts = ?
        WHERE player_url = ? AND G = ?
        """
        
        try:
            for batch_num in range(total_batches):
                batch_start = batch_num * batch_size
                batch_end = min(batch_start + batch_size, total_rows)
                batch_df = df.iloc[batch_start:batch_end]
                
                print(f"Processing batch {batch_num + 1}/{total_batches} (rows {batch_start + 1}-{batch_end})...")
                
                # Prepare data for batch update
                update_data = [
                    (float(row['espn_fpts']), float(row['nba_salary_cap_fpts']), row['player_url'], row['G']) 
                    for _, row in batch_df.iterrows()
                ]
                
                # Execute batch update
                cursor.executemany(update_query, update_data)
                updated_count += len(update_data)
                
                # Commit after each batch to avoid long transactions
                conn.commit()
                print(f"  Committed {len(update_data)} rows. Progress: {updated_count}/{total_rows} ({updated_count/total_rows*100:.1f}%)")
                
        except KeyboardInterrupt:
            print("\n\nProcess interrupted by user!")
            print(f"Processed {updated_count} out of {total_rows} rows.")
            conn.commit()
        
        # Verify the update
        print("Verifying updates...")
        verify_query = """
        SELECT COUNT(*) FROM clean_game_logs
        WHERE (espn_fpts IS NULL 
        OR nba_salary_cap_fpts IS NULL)
        AND MP not in ('Inactive','Did Not Play','Did Not Dress','Player Suspended','Not With Team')
        """
        cursor = conn.execute(verify_query)
        result = cursor.fetchone()
        verified_count = result[0] if result is not None else 0  # Handle None case
        
        print(f"\nUpdated {updated_count} rows")
        print(f"Total rows with no fantasy points: {verified_count}")
        
        # Refresh the views
        print("\nRefreshing views...")
        conn.execute("DROP VIEW IF EXISTS fantasy_averages")
        conn.execute("DROP VIEW IF EXISTS fantasy_home_away_splits")
        
        # Create fantasy points averages view
        print("Creating fantasy_averages view...")
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
        print("Creating fantasy_home_away_splits view...")
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
        
    except Exception as e:
        print(f"Error in calculate_fantasy_points: {str(e)}")
        import traceback
        print(f"Full stack trace:\n{traceback.format_exc()}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("Database connection closed")
        
    print("Done with calculate_fantasy_points!")

if __name__ == "__main__":
    calculate_fantasy_points() 