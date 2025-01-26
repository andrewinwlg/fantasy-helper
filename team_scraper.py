"""Scrape current team roster from NBA Fantasy website."""

import os
import sqlite3
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def setup_chrome_driver():
    """Configure Chrome driver with appropriate options."""
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in headless mode
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    return webdriver.Chrome(options=chrome_options)


def init_database():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect('nba_fantasy.db')
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nba_team_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    finally:
        conn.close()


def scrape_team_roster(login_id: str, password: str) -> list:
    """
    Scrape the current team roster from NBA Fantasy website.
    Returns list of player names.
    """
    init_database()
    
    driver = setup_chrome_driver()
    players = []
    conn = None
    
    try:
        # Navigate to login page
        print("Navigating to NBA Fantasy...")
        driver.get('https://nbafantasy.nba.com/my-team')
        time.sleep(2)  # Wait for page to load
        
        # Save page source for debugging
        with open('debug_pre_login.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("Saved pre-login page source to debug_pre_login.html")
        
        # Login
        print("Attempting to login...")
        wait = WebDriverWait(driver, 10)
        
        try:
            # Find and fill login fields
            print("Looking for login fields...")
            username_field = wait.until(EC.presence_of_element_located((By.NAME, 'email')))
            print("Found username field")
            password_field = driver.find_element(By.NAME, 'password')
            print("Found password field")
            
            username_field.send_keys(login_id)
            password_field.send_keys(password)
            print("Filled in credentials")
            
            # Click login button
            print("Looking for login button...")
            login_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            print("Found login button")
            login_button.click()
            print("Clicked login button")
            
        except Exception as e:
            print(f"Login error: {str(e)}")
            # Save page source for debugging login issues
            with open('debug_login_error.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print("Saved login error page source to debug_login_error.html")
            raise
        
        # Wait for roster to load
        print("Waiting for roster to load...")
        time.sleep(5)  # Adjust this if needed
        
        # Click List View button
        print("Looking for List View button...")
        list_view_selectors = [
            'a[href="#list"]',
            '.Tab__Link-sc-vb7yrb-1',
            'a.iQzNhp',
            'a:contains("List View")',
            '.Tab__Link-sc-vb7yrb-1.iQzNhp'
        ]
        
        list_view_clicked = False
        for selector in list_view_selectors:
            try:
                list_view_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                print(f"Found List View button with selector: {selector}")
                list_view_button.click()
                print("Clicked List View button")
                time.sleep(3)  # Wait longer for view to change
                list_view_clicked = True
                break
            except Exception as e:
                print(f"List View button selector {selector} failed: {str(e)}")
        
        if list_view_clicked:
            # Save HTML after list view loads
            print("Saving post-list-view HTML...")
            with open('debug_post_list_view.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print("Saved post-list-view HTML to debug_post_list_view.html")
            
            # Take screenshot of list view
            driver.save_screenshot('debug_list_view.png')
            print("Saved list view screenshot to debug_list_view.png")
        else:
            print("Failed to click List View button")
        
        # Try different selectors for player elements in list view
        selectors = [
            '.ElementInTable__SecondName-sc-1grpbqk-2 .Utils__Ellipsis-sc-1eav01y-0',  # Last name
        ]
        
        for selector in selectors:
            print(f"Trying selector: {selector}")
            try:
                player_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                )
                if player_elements:
                    print(f"Found {len(player_elements)} elements with selector {selector}")
                    # Get last names
                    last_names = [el.text.strip() for el in player_elements]
                    
                    # Find corresponding first names
                    first_name_elements = driver.find_elements(By.CSS_SELECTOR, 
                        '.ElementInTable__Name-sc-1grpbqk-1 .Utils__Ellipsis-sc-1eav01y-0')
                    first_names = [el.text.strip() for el in first_name_elements]
                    
                    # Combine first and last names
                    players = []
                    for i in range(len(last_names)):
                        full_name = f"{first_names[i]} {last_names[i]}"
                        players.append(full_name)
                    
                    if players:
                        print("Found players:")
                        for player in players:
                            print(f"  - {player}")
                        break
            except Exception as e:
                print(f"Selector {selector} failed: {str(e)}")
        
        if not players:
            print("No players found with any selector")
            # Take screenshot
            driver.save_screenshot('debug_roster_page.png')
            print("Saved screenshot to debug_roster_page.png")
        
        if players:
            try:
                conn = sqlite3.connect('nba_fantasy.db', timeout=20)
                cursor = conn.cursor()
                
                # Delete existing players for this login
                cursor.execute('DELETE FROM nba_team_players WHERE login_id = ?', (login_id,))
                
                for player in players:
                    cursor.execute(
                        'INSERT INTO nba_team_players (login_id, player_name) VALUES (?, ?)',
                        (login_id, player)
                    )
                
                conn.commit()
                print(f"Successfully updated {len(players)} players in database")
                
            except Exception as e:
                print(f"Database error: {str(e)}")
                if conn:
                    conn.rollback()
            finally:
                if conn:
                    conn.close()
        
        return players
        
    except Exception as e:
        print(f"Error scraping team roster: {str(e)}")
        try:
            driver.save_screenshot('debug_error.png')
            print("Saved error screenshot to debug_error.png")
        except:
            pass
    finally:
        driver.quit()
        if conn:
            conn.close()
    
    return players


def main():
    """Main function to run the scraper."""
    login_id = os.getenv('NBA_LOGIN')
    password = os.getenv('NBA_PWD')
    
    if not login_id or not password:
        print("Error: NBA_LOGIN and NBA_PWD environment variables must be set")
        return
    
    print(f"Starting team scraper for {login_id}")
    players = scrape_team_roster(login_id, password)
    
    if not players:
        print("No players found - check login credentials or website structure")


if __name__ == "__main__":
    main() 