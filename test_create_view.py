"""Test the player_salary_stats view changes."""

import sqlite3
import unittest

import pandas as pd

from create_view import create_player_stats_view


class TestPlayerSalaryStatsView(unittest.TestCase):
    """Test cases for player_salary_stats view changes."""
    
    def setUp(self):
        """Back up the current view data to a table."""
        self.conn = sqlite3.connect('nba_stats.db')
        
        # Backup current view data
        print("\nBacking up current view data...")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS player_salary_stats_backup AS 
            SELECT * FROM player_salary_stats
        """)
        
        # Get count of backed up records
        cursor = self.conn.execute("SELECT COUNT(*) FROM player_salary_stats_backup")
        count = cursor.fetchone()[0]
        print(f"Backed up {count} records")
    
    def tearDown(self):
        """Clean up the backup table."""
        #self.conn.execute("DROP TABLE IF EXISTS player_salary_stats_backup")
        self.conn.close()
    
    def test_30d_stats_consistency(self):
        """Test that 30-day stats remain consistent after view update."""
        # Get old stats
        old_stats = pd.read_sql("""
            SELECT 
                Player,
                Fantasy_Points_Per_Game_30D as old_fpts,
                Games_Last_30D as old_games,
                Value_Per_Game_30D as old_value
            FROM player_salary_stats_backup
            WHERE Games_Last_30D > 0
        """, self.conn)
        
        # Create new view
        create_player_stats_view()
        
        # Get new stats
        new_stats = pd.read_sql("""
            SELECT 
                Player,
                Fantasy_Points_Per_Game_30D as new_fpts,
                Games_Last_30D as new_games,
                Value_Per_Game_30D as new_value
            FROM player_salary_stats
            WHERE Games_Last_30D > 0
        """, self.conn)
        
        # Merge old and new stats
        comparison = pd.merge(
            old_stats, 
            new_stats, 
            on='Player', 
            suffixes=('_old', '_new')
        )
        
        # Check for differences
        fpts_diff = comparison[
            abs(comparison.old_fpts - comparison.new_fpts) > 0.01
        ]
        games_diff = comparison[
            comparison.old_games != comparison.new_games
        ]
        value_diff = comparison[
            abs(comparison.old_value - comparison.new_value) > 0.01
        ]
        
        # Print any differences found
        if not fpts_diff.empty:
            print("\nFantasy points differences found:")
            print(fpts_diff)
        if not games_diff.empty:
            print("\nGames played differences found:")
            print(games_diff)
        if not value_diff.empty:
            print("\nValue differences found:")
            print(value_diff)
        
        # Assert no differences
        self.assertTrue(fpts_diff.empty, "Fantasy points calculations changed")
        self.assertTrue(games_diff.empty, "Games played counts changed")
        self.assertTrue(value_diff.empty, "Value calculations changed")
        
        # Print summary
        print(f"\nCompared {len(comparison)} players")
        print("All 30-day stats remain consistent")


if __name__ == '__main__':
    unittest.main() 