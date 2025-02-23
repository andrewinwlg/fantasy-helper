"""Scrape player injury news from NBA Fantasy website."""

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

def setup_chrome_driver():
    """Configure Chrome driver with appropriate options."""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')  # Use new headless mode
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-gpu')
    
    # Add user agent to appear more like a real browser
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Set up debug directory
    debug_dir = Path('debug')
    debug_dir.mkdir(exist_ok=True)
    
    return webdriver.Chrome(options=chrome_options)

def save_debug_info(driver, stage):
    """Save HTML and screenshot for debugging."""
    debug_dir = Path('debug')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save HTML
    html_file = debug_dir / f"{stage}_{timestamp}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print(f"Saved HTML to {html_file}")
    
    # Save screenshot
    screenshot_file = debug_dir / f"{stage}_{timestamp}.png"
    driver.save_screenshot(str(screenshot_file))
    print(f"Saved screenshot to {screenshot_file}")

def init_database():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect('nba_stats.db')
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_injuries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                team TEXT NOT NULL,
                position TEXT NOT NULL,
                injury_type TEXT NOT NULL,
                expected_return DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    finally:
        conn.close()

def parse_injury_news(news_text):
    """Parse injury news text to extract injury type and return date."""
    parts = news_text.split('expected back')
    if len(parts) != 2:
        return None, None
    
    injury_type = parts[0].strip()
    try:
        # Convert date string to datetime object
        return_date = datetime.strptime(parts[1].strip(), '%Y-%m-%d').date()
        return injury_type, return_date
    except ValueError:
        return injury_type, None

def accept_cookies(driver):
    """Accept any cookie consent banners"""
    try:
        # Try different ways to find and close cookie banners
        selectors = [
            (By.ID, "onetrust-accept-btn-handler"),
            (By.CLASS_NAME, "onetrust-close-btn-handler"),
            (By.ID, "onetrust-policy-text"),
            (By.ID, "onetrust-banner-sdk"),
            (By.CSS_SELECTOR, "[aria-label='Close']"),
            (By.CSS_SELECTOR, "button[contains(text(), 'Accept')]")
        ]
        
        for selector_type, selector in selectors:
            try:
                element = driver.find_element(selector_type, selector)
                print(f"Found cookie element using {selector}")
                element.click()
                time.sleep(1)
                return True
            except:
                continue
                
        # If we can't find a button, try to remove the banner with JavaScript
        driver.execute_script("""
            var elements = document.querySelectorAll('#onetrust-banner-sdk, #onetrust-consent-sdk');
            elements.forEach(e => e.remove());
        """)
        print("Removed cookie banner with JavaScript")
        return True
        
    except Exception as e:
        print(f"Error handling cookies: {str(e)}")
        return False

def find_pagination_button(driver, button_type):
    """Find pagination button by its position or text"""
    try:
        print(f"\nLooking for {button_type} button...")
        
        # Find all buttons
        buttons = driver.find_elements(By.CLASS_NAME, "PaginatorButton__Button-sc-bccamd-0")
        print(f"Found {len(buttons)} buttons with class PaginatorButton__Button-sc-bccamd-0")
        
        if len(buttons) < 4:
            print("Not enough pagination buttons found")
            return None
            
        # Print all buttons for debugging
        for i, button in enumerate(buttons):
            print(f"Button {i}: text='{button.text}' class='{button.get_attribute('class')}'")
        
        # Use button position
        if button_type == "Next":
            print("Returning Next button (index 2)")
            return buttons[2]  # Third button (0-based index)
        elif button_type == "Last":
            print("Returning Last button (index 3)")
            return buttons[3]  # Fourth button
        
        return None
        
    except Exception as e:
        print(f"Error finding {button_type} button: {str(e)}")
        return None

def wait_for_table_update(driver, current_first_player, max_retries=3):
    """Wait for table to update with new data"""
    for attempt in range(max_retries):
        try:
            # Wait up to 10 seconds for the table to be present
            wait = WebDriverWait(driver, 10)
            table = wait.until(EC.presence_of_element_located((
                By.CLASS_NAME, 'InjuryTracker__InjuryTrackerTable-sc-1px8xnl-1'
            )))
            
            # Get the new first player name
            new_first_player = table.find_element(
                By.CLASS_NAME, 'StatusTableElement__FirstName-sc-cq75nl-1'
            ).text
            
            if new_first_player != current_first_player:
                print(f"Table updated: {current_first_player} -> {new_first_player}")
                return True
                
            print(f"Table not updated yet (attempt {attempt + 1})")
            time.sleep(2)
            
        except Exception as e:
            print(f"Error waiting for table update (attempt {attempt + 1}): {str(e)}")
            time.sleep(2)
            
    return False

def scrape_table_data(driver):
    """Scrape data from current table view"""
    injuries = []
    try:
        # Wait for table to be present
        wait = WebDriverWait(driver, 10)
        table = wait.until(EC.presence_of_element_located((
            By.CLASS_NAME, 'InjuryTracker__InjuryTrackerTable-sc-1px8xnl-1'
        )))
        
        # Wait for rows to be present
        rows = wait.until(EC.presence_of_all_elements_located((
            By.CLASS_NAME, 'ElementTable__ElementRow-sc-8zrnbf-3'
        )))
        
        print(f"Found {len(rows)} rows")
        
        for row in rows:
            try:
                # Extract player name
                first_name = row.find_element(
                    By.CLASS_NAME, 'StatusTableElement__FirstName-sc-cq75nl-1'
                ).text
                last_name = row.find_element(
                    By.CLASS_NAME, 'StatusTableElement__SecondName-sc-cq75nl-2'
                ).text
                player_name = f"{first_name} {last_name}"
                print(f"Processing player: {player_name}")
                
                # Extract team
                team = row.find_element(
                    By.CSS_SELECTOR, '.TeamCode__StyledTeamCode-sc-t0jdgp-0 strong'
                ).text
                
                # Extract position
                position = row.find_element(
                    By.CLASS_NAME, 'StatusTableElement__TeamPosition-sc-cq75nl-4'
                ).text
                
                # Extract injury news
                news = row.find_element(
                    By.CLASS_NAME, 'InjuryTracker__News-sc-1px8xnl-8'
                ).text
                
                # Parse injury type and return date
                injury_type, expected_return = parse_injury_news(news)
                
                if injury_type and expected_return:
                    injury = {
                        'player_name': player_name,
                        'team': team,
                        'position': position,
                        'injury_type': injury_type,
                        'expected_return': expected_return
                    }
                    injuries.append(injury)
                    print(f"Added injury record for {player_name}")
                    
            except Exception as e:
                print(f"Error processing row: {str(e)}")
                continue
                
        return injuries
    except Exception as e:
        print(f"Error scraping table data: {str(e)}")
        return None

def scrape_injury_news():
    """
    Scrape the player injury news from NBA Fantasy website.
    Returns list of injury records.
    """
    init_database()
    
    driver = setup_chrome_driver()
    all_injuries = []
    conn = None
    current_page = 1
    max_pages = 8  # We know there are 8 pages
    
    try:
        # Navigate to injury news page
        print("Navigating to NBA Fantasy injury news...")
        driver.get('https://nbafantasy.nba.com/player-news')
        time.sleep(5)  # Initial wait time
        
        # Handle cookie consent
        accept_cookies(driver)
        
        # Wait for injury tracker table to load
        wait = WebDriverWait(driver, 20)
        table = wait.until(EC.presence_of_element_located((
            By.CLASS_NAME, 'InjuryTracker__InjuryTrackerTable-sc-1px8xnl-1'
        )))
        
        while current_page <= max_pages:
            print(f"\nProcessing page {current_page} of {max_pages}")
            
            # Get current page data
            page_injuries = scrape_table_data(driver)
            if page_injuries:
                all_injuries.extend(page_injuries)
                print(f"Added {len(page_injuries)} injuries from page {current_page}")
            else:
                print(f"No injuries found on page {current_page}")
            
            if current_page == max_pages:
                print("Reached last page")
                break
            
            # Get first player name before clicking Next
            try:
                first_player = driver.find_element(
                    By.CLASS_NAME, 'StatusTableElement__FirstName-sc-cq75nl-1'
                ).text
            except:
                print("Could not get first player name")
                break
            
            # Try to go to next page
            next_button = find_pagination_button(driver, "Next")
            if not next_button or "fdivGe" not in next_button.get_attribute("class"):
                print("Next button not found or disabled")
                break
            
            print("\nMoving to next page...")
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(2)
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(2)  # Additional wait after click
            
            # Wait for table to update
            if not wait_for_table_update(driver, first_player):
                print("Table failed to update")
                break
            
            current_page += 1
        
        print(f"\nSuccessfully scraped {len(all_injuries)} total injury records")
        
        # Store all injuries in database
        conn = sqlite3.connect('nba_stats.db')
        cursor = conn.cursor()
        
        for injury in all_injuries:
            cursor.execute('''
                INSERT INTO player_injuries 
                (player_name, team, position, injury_type, expected_return)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                injury['player_name'],
                injury['team'],
                injury['position'],
                injury['injury_type'],
                injury['expected_return']
            ))
        
        conn.commit()
        
    except Exception as e:
        print(f"Error scraping injury news: {str(e)}")
        save_debug_info(driver, 'error_state')
    finally:
        if driver:
            driver.quit()
        if conn:
            conn.close()
    
    return all_injuries

def main():
    """Main function to run the scraper."""
    print("Starting injury news scraper")
    injuries = scrape_injury_news()
    
    if not injuries:
        print("No injuries found - check debug directory for HTML and screenshots")
    else:
        print(f"\nFound {len(injuries)} injuries:")
        for injury in injuries:
            print(f"{injury['player_name']} ({injury['team']}-{injury['position']}) - "
                  f"{injury['injury_type']}, Expected return: {injury['expected_return']}")

if __name__ == "__main__":
    main() 