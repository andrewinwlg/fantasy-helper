"""Integration tests for team_scraper.py"""

import os
import sqlite3
import unittest

from team_scraper import scrape_team_roster


class TestTeamScraper(unittest.TestCase):
    """Test cases for team_scraper.py"""
    
    def setUp(self):
        """Set up database connection."""
        self.conn = sqlite3.connect('nba_fantasy.db')
        self.cursor = self.conn.cursor()
        
        # Get credentials from environment
        self.login_id = os.getenv('NBA_LOGIN')
        self.password = os.getenv('NBA_PWD')
        
        if not self.login_id or not self.password:
            self.skipTest("NBA_LOGIN and NBA_PWD environment variables must be set")
    
    def tearDown(self):
        """Clean up database connection."""
        self.conn.close()
    
    def test_roster(self):
        """Test roster size and contents."""
        # Run the scraper once
        players = scrape_team_roster(self.login_id, self.password)
        
        # Test 1: Check that we got exactly 10 players
        self.assertEqual(len(players), 10, "Roster should contain exactly 10 players")
        
        # Check database size
        self.cursor.execute('SELECT COUNT(*) FROM nba_team_players WHERE login_id = ?', (self.login_id,))
        count = self.cursor.fetchone()[0]
        self.assertEqual(count, 10, "Database should contain exactly 10 players")
        
        # Test 2: Check that Jokic is in the list
        self.assertIn("Nikola Jokic", players, "Nikola Jokic should be in the roster")
        
        # Check Jokic in database
        self.cursor.execute(
            'SELECT COUNT(*) FROM nba_team_players WHERE login_id = ? AND player_name = ?', 
            (self.login_id, 'Nikola Jokic')
        )
        count = self.cursor.fetchone()[0]
        self.assertEqual(count, 1, "Nikola Jokic should be in the database")


if __name__ == '__main__':
    unittest.main() 