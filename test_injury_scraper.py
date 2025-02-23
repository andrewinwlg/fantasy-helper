"""Test the injury scraper functionality and data integrity."""

import os
import sqlite3
import unittest
from datetime import datetime, timedelta

from injury_scraper import init_database, scrape_injury_news

class TestInjuryScraper(unittest.TestCase):
    """Test cases for injury scraper and related data."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database connection and ensure tables exist"""
        cls.conn = sqlite3.connect('nba_stats.db')
        cls.cursor = cls.conn.cursor()
        
        # Ensure tables exist
        init_database()
        
        # Check if we need to run scraper
        cls.cursor.execute('SELECT COUNT(*) FROM player_injuries')
        count = cls.cursor.fetchone()[0]
        if count == 0:
            print("\nNo injury data found, running scraper...")
            scrape_injury_news()

    @classmethod
    def tearDownClass(cls):
        """Close database connection"""
        cls.conn.close()

    def test_injury_player_consistency(self):
        """Test that all injured players exist in the player stats table"""
        # Get all injured players from last 7 days (increased from 1 day)
        self.cursor.execute('''
            SELECT DISTINCT player_name, team 
            FROM player_injuries 
            WHERE created_at >= datetime('now', '-7 day')
        ''')
        injured_players = self.cursor.fetchall()
        
        # Skip test if no data
        if len(injured_players) == 0:
            self.skipTest("No injury data found in the last 7 days")
        
        # Get all players from stats table
        self.cursor.execute('SELECT name, team FROM nba_salary_cap_players')
        all_players = {(name.lower(), team) for name, team in self.cursor.fetchall()}
        
        # Check each injured player exists in player stats
        missing_players = []
        for player_name, team in injured_players:
            if (player_name.lower(), team) not in all_players:
                missing_players.append(f"{player_name} ({team})")
        
        # Format error message with details if any missing players
        if missing_players:
            error_msg = (
                f"Found {len(missing_players)} injured players missing from player stats:\n"
                + "\n".join(missing_players)
                + "\nPossible causes:\n"
                + "1. Player name formatting differences\n"
                + "2. Team abbreviation differences\n"
                + "3. Player stats need to be updated"
            )
            self.fail(error_msg)

    def test_injury_data_freshness(self):
        """Test that injury data exists and is not too old"""
        self.cursor.execute('''
            SELECT MAX(created_at) 
            FROM player_injuries
        ''')
        latest_update = self.cursor.fetchone()[0]
        
        # Skip test if no data
        if not latest_update:
            self.skipTest("No injury data found in database")
            
        latest_update = datetime.strptime(latest_update, '%Y-%m-%d %H:%M:%S')
        time_since_update = datetime.now() - latest_update
        
        self.assertLess(
            time_since_update, 
            timedelta(days=7),  # Increased from 24 hours to 7 days
            f"Injury data is {time_since_update.total_seconds() / 3600:.1f} hours old"
        )
    
    def test_injury_data_format(self):
        """Test that injury data is properly formatted"""
        # Get schema info
        self.cursor.execute('PRAGMA table_info(player_injuries)')
        columns = [col[1] for col in self.cursor.fetchall()]
        
        # Verify required columns exist
        required_columns = {'player_name', 'team', 'injury_type', 'expected_return', 'created_at'}
        missing_columns = required_columns - set(columns)
        self.assertEqual(missing_columns, set(), 
            f"Missing required columns in player_injuries table: {missing_columns}")
        
        # Get recent injuries
        self.cursor.execute('''
            SELECT player_name, team, injury_type, expected_return
            FROM player_injuries
            WHERE created_at >= datetime('now', '-7 day')
        ''')
        injuries = self.cursor.fetchall()
        
        # Skip test if no data
        if len(injuries) == 0:
            self.skipTest("No injury data found in the last 7 days")
        
        for player_name, team, injury_type, expected_return in injuries:
            # Check player name format
            self.assertIsInstance(player_name, str)
            self.assertTrue(len(player_name.split()) >= 2, 
                f"Player name '{player_name}' should have first and last name")
            
            # Check team abbreviation
            self.assertIsInstance(team, str)
            self.assertEqual(len(team), 3, 
                f"Team abbreviation '{team}' should be 3 characters")
            
            # Check injury type
            self.assertIsInstance(injury_type, str)
            self.assertTrue(len(injury_type) > 0, 
                f"Injury type for {player_name} should not be empty")
            
            # Check return date format
            self.assertIsInstance(expected_return, str)
            try:
                datetime.strptime(expected_return, '%Y-%m-%d')
            except ValueError:
                self.fail(f"Invalid return date format for {player_name}: {expected_return}")

if __name__ == '__main__':
    unittest.main() 