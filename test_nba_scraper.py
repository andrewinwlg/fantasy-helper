import sqlite3
import unittest

import pandas as pd

from nba_scraper import save_to_database, scrape_nba_players


class TestNBAScraper(unittest.TestCase):
    def setUp(self):
        """Run before each test"""
        self.conn = sqlite3.connect('nba_stats.db')
        
    def tearDown(self):
        """Run after each test"""
        self.conn.close()
    
    def test_player_name_matching(self):
        """Test that player names match between data sources"""
        print("\nTesting player name matching...")
        
        # Scrape and save fresh data
        df = scrape_nba_players()
        self.assertIsNotNone(df, "Failed to scrape player data")
        save_to_database(df, 'player_stats')
        
        # Check for unmatched salary players (who have scored at least one point)
        query = """
        SELECT 
            nsc.name,
            nsc.salary,
            nsc.avgPoints as fantasy_points_per_game,
            nsc.ownership as ownership_percentage
        FROM nba_salary_cap_players nsc
        LEFT JOIN player_stats ps ON nsc.name = ps.Player
        WHERE ps.Player IS NULL
        AND nsc.avgPoints > 0
        ORDER BY nsc.salary DESC;
        """
        
        unmatched = pd.read_sql(query, self.conn)
        
        if len(unmatched) > 0:
            print("\nUnmatched players found:")
            print(unmatched)
            
        self.assertEqual(len(unmatched), 0, 
            f"Found {len(unmatched)} players in salary data that don't match player stats")
        
        # Additional quality checks
        print("\nChecking for duplicate players...")
        query = """
        SELECT Player, COUNT(*) as count
        FROM player_stats
        GROUP BY Player
        HAVING count > 1;
        """
        duplicates = pd.read_sql(query, self.conn)
        if len(duplicates) > 0:
            print("\nDuplicate players found:")
            print(duplicates)
        self.assertEqual(len(duplicates), 0, 
            f"Found {len(duplicates)} duplicate players in player stats")
        
        print("\nChecking for null values in key columns...")
        query = """
        SELECT Player, Team, player_url
        FROM player_stats
        WHERE Player IS NULL 
        OR Team IS NULL 
        OR player_url IS NULL;
        """
        nulls = pd.read_sql(query, self.conn)
        if not nulls.empty:
            print("\nRows with null values:")
            print(nulls)
        self.assertTrue(nulls.empty, "Found rows with null values in key columns")
        
        # Check raw scraped data for duplicates
        print("\nChecking raw scraped data for duplicates...")
        raw_duplicates = df[df.duplicated(['Player'], keep=False)]
        if not raw_duplicates.empty:
            print("\nDuplicates in raw data:")
            print(raw_duplicates[['Player', 'Team', 'player_url']])
        
        print("\nChecking for players missing from salary data...")
        query = """
        SELECT 
            ps.Player,
            ps.Team,
            ps.PTS as points_per_game,
            ps.MP as minutes_per_game
        FROM player_stats ps
        LEFT JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        WHERE nsc.name IS NULL
        ORDER BY ps.PTS DESC;
        """
        
        missing_from_salary = pd.read_sql(query, self.conn)
        
        if len(missing_from_salary) > 0:
            print("\nPlayers missing from salary data:")
            print(missing_from_salary)
            
        self.assertEqual(len(missing_from_salary), 0, 
            f"Found {len(missing_from_salary)} players in stats that don't have salary data")

if __name__ == '__main__':
    unittest.main(verbosity=2) 