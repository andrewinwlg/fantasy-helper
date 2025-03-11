"""Integration tests for team_scraper.py"""

import os
import sqlite3
import unittest
from unittest.mock import patch

from team_scraper import scrape_team_roster, init_database


class TestTeamScraper(unittest.TestCase):
    """Test cases for team_scraper.py."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database connection."""
        cls.conn = sqlite3.connect('nba_stats.db')
        cls.cursor = cls.conn.cursor()
        
        # Create test table if it doesn't exist
        cls.cursor.execute('''
            CREATE TABLE IF NOT EXISTS nba_team_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cls.conn.commit()
    
    @classmethod
    def tearDownClass(cls):
        """Close database connection."""
        cls.conn.close()
    
    def setUp(self):
        """Set up for each test."""
        # Clear test data
        self.cursor.execute('DELETE FROM nba_team_players')
        self.conn.commit()
    
    @patch('team_scraper.setup_chrome_driver')
    @patch('team_scraper.WebDriverWait')
    def test_scrape_team_roster_error(self, mock_wait, mock_setup_driver):
        """Test handling of errors during scraping."""
        # Mock driver to raise exception
        mock_driver = mock_setup_driver.return_value
        mock_driver.get.side_effect = Exception("Test error")
        
        # Call function with test credentials
        result = scrape_team_roster('test@example.com', 'password')
        
        # Verify results
        self.assertEqual(result, [])
        
        # Verify driver was quit
        mock_driver.quit.assert_called_once()
    
    def test_init_database(self):
        """Test database initialization."""
        # Call function
        init_database()
        
        # Verify table exists
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nba_team_players'")
        result = self.cursor.fetchone()
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main() 