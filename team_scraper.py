"""Scrape current team roster from NBA Fantasy website."""

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
import random
import re
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Add dotenv support
try:
    from dotenv import load_dotenv
    # Load environment variables from .env file if it exists
    load_dotenv()
except ImportError:
    print("dotenv package not installed. Using environment variables directly.")
    # If dotenv is not installed, we'll just use os.environ directly


def setup_chrome_driver(use_profile=True):
    """Configure Chrome driver with appropriate options to avoid detection."""
    chrome_options = Options()
    
    # Use a real Chrome profile if available
    if use_profile:
        # Try to find the Chrome user data directory
        home_dir = str(Path.home())
        
        # Common Chrome profile locations based on OS
        profile_locations = [
            # Linux
            os.path.join(home_dir, '.config/google-chrome'),
            os.path.join(home_dir, '.config/chromium'),
            # Windows
            os.path.join(home_dir, 'AppData/Local/Google/Chrome/User Data'),
            # macOS
            os.path.join(home_dir, 'Library/Application Support/Google/Chrome'),
        ]
        
        # Find the first existing profile location
        user_data_dir = None
        for location in profile_locations:
            if os.path.exists(location):
                user_data_dir = location
                break
        
        if user_data_dir:
            print(f"Using Chrome profile from: {user_data_dir}")
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
            
            # Try to use the default profile
            default_profile = os.path.join(user_data_dir, 'Default')
            if os.path.exists(default_profile):
                chrome_options.add_argument(f"--profile-directory=Default")
            else:
                # Try to find any profile directory
                profile_dirs = [d for d in os.listdir(user_data_dir) 
                               if os.path.isdir(os.path.join(user_data_dir, d)) 
                               and (d.startswith('Profile') or d == 'Default')]
                if profile_dirs:
                    chrome_options.add_argument(f"--profile-directory={profile_dirs[0]}")
        else:
            print("No Chrome profile found, using default settings")
    
    # Use non-headless mode for better JavaScript support and to avoid detection
    # chrome_options.add_argument('--headless=new')
    
    # Basic browser settings
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Explicitly enable JavaScript
    chrome_options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.javascript": 1,  # 1 = allow, 2 = block
        "profile.default_content_settings.javascript": 1,
        "javascript.enabled": True,
        # Add additional preferences to appear more human-like
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,  # Block notifications
        "profile.managed_default_content_settings.images": 1,  # Load images
        "profile.default_content_setting_values.cookies": 1,  # Allow cookies
        "profile.default_content_setting_values.plugins": 1,  # Allow plugins
        "profile.default_content_setting_values.popups": 2,  # Block popups
        "profile.default_content_setting_values.geolocation": 2,  # Block location
        "profile.default_content_setting_values.media_stream": 2,  # Block media
    })
    
    # Make the browser appear more like a real user
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Add additional browser-like settings
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--lang=en-US,en;q=0.9')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--allow-running-insecure-content')
    
    # Add browser fingerprinting evasion
    chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    
    # Set up debug directory
    debug_dir = Path('debug')
    debug_dir.mkdir(exist_ok=True)
    
    # Create the driver with a longer page load timeout
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    
    # Execute JavaScript to mask automation fingerprints
    try:
        # Override the navigator properties that automation detection scripts check
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Override the plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Override the languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Overwrite the permissions API
            if (navigator.permissions) {
                window.navigator.permissions.query = (parameters) => {
                    return Promise.resolve({state: 'granted'});
                };
            }
            
            // Add a fake notification API
            window.Notification = {
                permission: 'granted',
                requestPermission: () => Promise.resolve('granted')
            };
            
            // Add a fake battery API
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1,
            });
        """)
        print("Successfully executed anti-detection JavaScript")
    except Exception as e:
        print(f"Warning: Could not execute anti-detection JavaScript: {e}")
    
    return driver


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


def wait_for_javascript(driver, timeout=30):
    """Wait for JavaScript to load completely and handle potential errors."""
    try:
        # Wait for document.readyState to be 'complete'
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        print("Document ready state is 'complete'")
        
        # Wait for jQuery to be loaded and active (if it exists)
        jquery_ready = driver.execute_script('''
            return (typeof jQuery !== 'undefined') ? 
                   jQuery.active === 0 : 
                   true;
        ''')
        if jquery_ready:
            print("jQuery is ready or not used")
        else:
            print("Waiting for jQuery...")
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script('return jQuery.active === 0')
            )
            print("jQuery is now ready")
        
        # Additional wait for any JavaScript frameworks to initialize
        time.sleep(5)
        print("Completed waiting for JavaScript")
        return True
    except Exception as e:
        print(f"Error waiting for JavaScript: {e}")
        return False


def check_javascript_enabled(driver):
    """Check if JavaScript is enabled and working."""
    try:
        # Try to execute a simple JavaScript command
        result = driver.execute_script("return navigator.javaEnabled();")
        print(f"JavaScript enabled: {result}")
        
        # Check if document is ready
        ready_state = driver.execute_script("return document.readyState")
        print(f"Document ready state: {ready_state}")
        
        return True
    except Exception as e:
        print(f"JavaScript check error: {str(e)}")
        return False


# Add this function to simulate human typing
def human_type(element, text):
    """Type text like a human with random delays between keystrokes."""
    for char in text:
        element.send_keys(char)
        # Random delay between keystrokes (50-200ms)
        time.sleep(random.uniform(0.05, 0.2))
    # Small pause after typing (200-500ms)
    time.sleep(random.uniform(0.2, 0.5))


def clear_cookies_and_cache(driver):
    """Clear cookies and cache to avoid detection."""
    try:
        driver.execute_script("window.localStorage.clear();")
        print("Cleared localStorage")
    except Exception as e:
        print(f"Error clearing localStorage: {e}")
    
    try:
        driver.execute_script("window.sessionStorage.clear();")
        print("Cleared sessionStorage")
    except Exception as e:
        print(f"Error clearing sessionStorage: {e}")
    
    try:
        driver.delete_all_cookies()
        print("Cleared cookies")
    except Exception as e:
        print(f"Error clearing cookies: {e}")
    
    # Try to clear cache using Chrome DevTools Protocol
    try:
        driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        print("Cleared browser cache")
    except Exception as e:
        print(f"Error clearing browser cache: {e}")


def clean_player_name(name):
    """Clean up player name by removing line breaks and team/position information."""
    # Remove line breaks
    name = name.replace('\n', ' ')
    
    # Remove team and position codes (e.g., DENFC, ATLBC)
    name = re.sub(r'\b[A-Z]{3}[A-Z]{2}\b', '', name)
    
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Check if the name contains a first and last name separated by spaces
    parts = name.split()
    if len(parts) >= 2:
        # If the first two parts look like a first and last name (capitalized words)
        if parts[0][0].isupper() and parts[1][0].isupper():
            # Special case for names with suffixes (Jr, III, etc.)
            if len(parts) >= 3 and parts[2] in ["II", "III", "IV", "Jr.", "Sr."]:
                return f"{parts[0]} {parts[1]} {parts[2]}"
            # Special case for Kel'el Ware
            elif "Kel'el" in parts[0] or "Kelel" in parts[0]:
                return "Kel'el Ware"
            else:
                return f"{parts[0]} {parts[1]}"
    
    # Special case for Kel'el Ware with different formatting
    if "Kel'el" in name or "Kelel" in name:
        return "Kel'el Ware"
    
    return name


def is_player_name(name):
    """Check if a string is likely to be a player name."""
    # Common NBA player names for validation
    known_players = [
        "Christian Braun", "Nikola Jokic", "LeBron James", "Stephen Curry", "Kevin Durant",
        "Giannis Antetokounmpo", "Luka Doncic", "Jayson Tatum", "Joel Embiid", "Kawhi Leonard",
        "Anthony Davis", "Damian Lillard", "Trae Young", "Ja Morant", "Zion Williamson",
        "Devin Booker", "Donovan Mitchell", "Bam Adebayo", "Jaylen Brown", "Jimmy Butler",
        "Trey Murphy", "Cade Cunningham", "Amen Thompson", "Dyson Daniels", "Jaden McDaniels",
        "Keon Johnson", "Naz Reid", "Murphy III", "Trey Murphy III", "Kel'el Ware", "Kelel Ware"
    ]
    
    # Check if it's a known player
    for player in known_players:
        if player.lower() in name.lower() or name.lower() in player.lower():
            return True
    
    # NBA team names to exclude
    team_names = [
        "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", 
        "Chicago Bulls", "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets", 
        "Detroit Pistons", "Golden State Warriors", "Houston Rockets", "Indiana Pacers", 
        "LA Clippers", "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", 
        "Miami Heat", "Milwaukee Bucks", "Minnesota Timberwolves", "New Orleans Pelicans", 
        "New York Knicks", "Oklahoma City Thunder", "Orlando Magic", "Philadelphia 76ers", 
        "Phoenix Suns", "Portland Trail Blazers", "Sacramento Kings", "San Antonio Spurs", 
        "Toronto Raptors", "Utah Jazz", "Washington Wizards",
        # Short team names
        "Hawks", "Celtics", "Nets", "Hornets", "Bulls", "Cavaliers", "Mavs", "Mavericks",
        "Nuggets", "Pistons", "Warriors", "Golden State", "Rockets", "Pacers", "Clippers",
        "Lakers", "Grizzlies", "Heat", "Bucks", "Wolves", "Timberwolves", "Pelicans",
        "Knicks", "Thunder", "Magic", "Sixers", "76ers", "Suns", "Blazers", "Trail Blazers",
        "Kings", "Spurs", "Raptors", "Jazz", "Wizards"
    ]
    
    # Check if it's a team name
    for team in team_names:
        if team.lower() == name.lower():
            return False
    
    # Common UI elements and team names to exclude
    ui_elements = [
        "accessibility", "hawks", "nets", "bulls", "cavaliers", "warriors", "rockets", "pacers",
        "clippers", "lakers", "bucks", "timberwolves", "pelicans", "knicks", "magic", "76ers",
        "suns", "spurs", "raptors", "jazz", "wizards", "league", "fantasy", "gameday", "transactions",
        "points", "rank", "roster", "team", "view", "profile", "support", "privacy", "terms",
        "english", "portuguese", "captain", "line-up", "bank", "value", "total", "remaining",
        "history", "save", "edit", "continue", "deciding", "purposes", "local time", "new zealand",
        "i accept", "i decline", "accept", "decline", "cookie", "cookies", "policy", "settings",
        "login", "logout", "sign in", "sign out", "register", "account", "password", "username",
        "email", "phone", "contact", "help", "faq", "about", "menu", "navigation", "search",
        "filter", "sort", "order", "asc", "desc", "submit", "cancel", "close", "open", "toggle",
        "expand", "collapse", "show", "hide", "next", "previous", "first", "last", "top", "bottom"
    ]
    
    # Check if it's a UI element
    for element in ui_elements:
        if element.lower() in name.lower():
            return False
    
    # Check if it has the structure of a player name (2-3 words, all alphabetic or with apostrophes)
    words = name.split()
    if 2 <= len(words) <= 3:
        # Check if all words are alphabetic (allowing apostrophes) and capitalized (like a name)
        if all(re.match(r"^[A-Z][a-z']*$", word) for word in words):
            return True
    
    # Special case for last names with suffix (e.g., "MURPHY III")
    if len(words) == 2 and words[1] in ["II", "III", "IV", "JR", "SR"]:
        if words[0].isalpha() and words[0][0].isupper():
            return True
    
    # Special case for names with apostrophes (e.g., "Kel'el Ware")
    if "'" in name and len(words) >= 2:
        return True
    
    return False


def extract_player_names_from_table(driver):
    """Extract player names from a table in list view format."""
    players = []
    
    try:
        # Find all table rows
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        print(f"Found {len(rows)} table rows")
        
        # Skip header row if it exists
        start_idx = 1 if len(rows) > 1 else 0
        
        for row in rows[start_idx:]:
            try:
                # Get all cells in the row
                cells = row.find_elements(By.TAG_NAME, "td")
                
                if len(cells) >= 1:
                    # The player name is typically in the first or second cell
                    for cell_idx in range(min(3, len(cells))):
                        cell_text = cells[cell_idx].text.strip()
                        if cell_text and len(cell_text) > 3:  # Minimum length for a name
                            cleaned_name = clean_player_name(cell_text)
                            if is_player_name(cleaned_name):
                                if "Christian Braun" in cleaned_name:
                                    print(f"Found Christian Braun in cell {cell_idx}!")
                                if "Kel'el" in cleaned_name or "Kelel" in cleaned_name:
                                    print(f"Found Kel'el Ware in cell {cell_idx}!")
                                players.append(cleaned_name)
                                break  # Found a player name in this row
            except Exception as e:
                print(f"Error processing table row: {str(e)}")
                continue
        
        return players
    except Exception as e:
        print(f"Error extracting player names from table: {str(e)}")
        return []


def scrape_team_roster(login_id: str, password: str, use_profile=False) -> list:
    """
    Scrape the current team roster from NBA Fantasy website.
    Returns list of player names.
    """
    init_database()
    
    driver = setup_chrome_driver(use_profile)
    players = []
    conn = None
    
    try:
        # Clear cookies and cache if not using profile
        if not use_profile:
            clear_cookies_and_cache(driver)
        
        # Try different URLs to find the team roster
        urls_to_try = [
            'https://nbafantasy.nba.com/my-team',
            'https://nbafantasy.nba.com/roster',
            'https://nbafantasy.nba.com/team',
            'https://nbafantasy.nba.com/my-roster',
            'https://nbafantasy.nba.com/fantasy/my-team',
            'https://nbafantasy.nba.com/fantasy/roster',
            'https://fantasy.nba.com/my-team',
            'https://fantasy.nba.com/roster'
        ]
        
        success = False
        for url in urls_to_try:
            try:
                print(f"Trying URL: {url}")
                # Navigate to the URL
                driver.get(url)
                
                # Random delay to simulate human behavior (2-4 seconds)
                time.sleep(random.uniform(2, 4))
                
                wait_for_javascript(driver)  # Ensure JavaScript is loaded
                
                # Check if JavaScript is enabled
                js_enabled = check_javascript_enabled(driver)
                print(f"JavaScript check result: {js_enabled}")
                
                # Save page source for debugging
                save_debug_info(driver, f'direct_url_{url.replace("https://", "").replace("/", "_")}')
                
                # Check if we need to log in
                if "login" in driver.current_url.lower() or "sign in" in driver.page_source.lower():
                    print("Login page detected, attempting to log in...")
                    
                    # Login
                    print("Attempting to login...")
                    wait = WebDriverWait(driver, 20)
                    
                    try:
                        # Find and fill login fields
                        print("Looking for login fields...")
                        username_field = wait.until(EC.presence_of_element_located((By.NAME, 'email')))
                        print("Found username field")
                        
                        # Click on the username field first (like a human would)
                        username_field.click()
                        time.sleep(random.uniform(0.3, 0.7))
                        
                        # Type username like a human
                        human_type(username_field, login_id)
                        
                        # Find password field
                        password_field = driver.find_element(By.NAME, 'password')
                        print("Found password field")
                        
                        # Click on the password field (like a human would)
                        password_field.click()
                        time.sleep(random.uniform(0.3, 0.7))
                        
                        # Type password like a human
                        human_type(password_field, password)
                        print("Filled in credentials")
                        
                        # Random delay before clicking login (0.5-1.5 seconds)
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        # Click login button
                        print("Looking for login button...")
                        login_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                        print("Found login button")
                        
                        # Move mouse to login button before clicking (like a human)
                        action = webdriver.ActionChains(driver)
                        action.move_to_element(login_button)
                        action.perform()
                        time.sleep(random.uniform(0.2, 0.5))
                        
                        login_button.click()
                        print("Clicked login button")
                        
                        # Wait for JavaScript to load after login
                        wait_for_javascript(driver, 20)
                        
                        # Random delay after login (3-5 seconds)
                        time.sleep(random.uniform(3, 5))
                    except Exception as e:
                        print(f"Login error: {str(e)}")
                        continue  # Try the next URL
                
                # Check for error messages
                print("Checking for error messages...")
                try:
                    error_element = driver.find_element(By.XPATH, "//h2[text()='Error']")
                    if error_element:
                        error_message = error_element.text
                        print(f"Error detected: '{error_message}'")
                        save_debug_info(driver, f'error_{url.replace("https://", "").replace("/", "_")}')
                        continue  # Try the next URL
                except Exception as e:
                    if "Error detected" in str(e):
                        continue  # Try the next URL
                    print("No error message found, continuing...")
                
                # Try to click on the "List View" tab if it exists
                print("Looking for 'List View' tab...")
                list_view_selectors = [
                    "//button[contains(text(), 'List View')]",
                    "//a[contains(text(), 'List View')]",
                    "//div[contains(text(), 'List View')]",
                    "//span[contains(text(), 'List View')]",
                    "//button[contains(@class, 'list-view')]",
                    "//a[contains(@class, 'list-view')]",
                    "//div[contains(@class, 'list-view')]",
                    "//button[contains(@data-testid, 'list-view')]",
                    "//a[contains(@data-testid, 'list-view')]",
                    "//div[contains(@data-testid, 'list-view')]",
                    "//button[contains(@id, 'list-view')]",
                    "//a[contains(@id, 'list-view')]",
                    "//div[contains(@id, 'list-view')]"
                ]
                
                list_view_clicked = False
                for selector in list_view_selectors:
                    try:
                        list_view_elements = driver.find_elements(By.XPATH, selector)
                        if list_view_elements:
                            print(f"Found 'List View' element with selector: {selector}")
                            for element in list_view_elements:
                                try:
                                    if element.is_displayed() and element.is_enabled():
                                        print("Clicking on 'List View' tab...")
                                        # Scroll to the element
                                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                        time.sleep(random.uniform(0.5, 1))
                                        
                                        # Move mouse to element before clicking (like a human)
                                        action = webdriver.ActionChains(driver)
                                        action.move_to_element(element)
                                        action.perform()
                                        time.sleep(random.uniform(0.2, 0.5))
                                        
                                        element.click()
                                        print("Clicked on 'List View' tab")
                                        list_view_clicked = True
                                        
                                        # Wait for the view to update
                                        time.sleep(random.uniform(1, 2))
                                        wait_for_javascript(driver)
                                        
                                        # Save debug info after clicking List View
                                        save_debug_info(driver, f'list_view_{url.replace("https://", "").replace("/", "_")}')
                                        break
                                except Exception as e:
                                    print(f"Error clicking on List View element: {str(e)}")
                            if list_view_clicked:
                                break
                    except Exception as e:
                        print(f"Error with List View selector {selector}: {str(e)}")
                
                if list_view_clicked:
                    print("Successfully switched to List View")
                    
                    # Try to extract player names from the table in list view
                    print("Extracting player names from table in list view...")
                    table_players = extract_player_names_from_table(driver)
                    
                    if table_players:
                        print(f"Found {len(table_players)} players in table")
                        players.extend(table_players)
                        success = True
                        break  # We found players, no need to try other URLs
                else:
                    print("Could not find or click on 'List View' tab")
                
                # Try to find the roster table using different selectors
                selectors_to_try = [
                    'table.roster-table', 
                    '.roster-list', 
                    '.player-list',
                    '.player-card',
                    '.player-name',
                    '.roster-player-name',
                    '[data-testid="player-name"]',
                    '[data-testid="player-card"]',
                    '.player-row',
                    '.team-roster',
                    '.team-list',
                    '.fantasy-team',
                    '.fantasy-roster',
                    # More specific selectors
                    '.player-item',
                    '.player-info',
                    '.player-details',
                    '.player-stats',
                    '.player-position',
                    '.player-team',
                    '.player-avatar',
                    '.player-image',
                    '.player-photo',
                    '.player-profile',
                    '.player-card-name',
                    '.player-card-info',
                    '.player-card-details',
                    '.player-card-stats',
                    '.player-card-position',
                    '.player-card-team',
                    # List view specific selectors
                    'table tr td',
                    '.list-view table',
                    '.list-view-table',
                    '.list-view .player-name',
                    '.list-view .player-row',
                    '.list-view-container table',
                    '.list-view-container .player-name'
                ]
                
                found_players = False
                for selector in selectors_to_try:
                    try:
                        print(f"Trying selector: {selector}")
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            print(f"Found {len(elements)} elements with selector {selector}")
                            
                            # Extract player names
                            for element in elements:
                                player_name = element.text.strip()
                                if player_name and not player_name.isdigit() and len(player_name) > 1:
                                    # Clean up the player name
                                    cleaned_name = clean_player_name(player_name)
                                    if is_player_name(cleaned_name):
                                        if "Christian Braun" in cleaned_name:
                                            print("Found Christian Braun!")
                                        players.append(cleaned_name)
                            
                            if players:
                                found_players = True
                                print(f"Found {len(players)} players with selector {selector}")
                                break
                    except Exception as e:
                        print(f"Error with selector {selector}: {str(e)}")
                
                if found_players:
                    success = True
                    break  # We found players, no need to try other URLs
                
                # Try to extract player names from the page source using JSON data
                print("Trying to extract player data from JSON in page source...")
                try:
                    page_source = driver.page_source
                    
                    # Look for JSON data containing player information
                    json_patterns = [
                        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                        r'window\.__PRELOADED_STATE__\s*=\s*({.*?});',
                        r'window\.__DATA__\s*=\s*({.*?});',
                        r'window\.__REDUX_STATE__\s*=\s*({.*?});',
                        r'window\.__APP_STATE__\s*=\s*({.*?});',
                        r'"players"\s*:\s*(\[.*?\])',
                        r'"roster"\s*:\s*(\[.*?\])',
                        r'"team"\s*:\s*({.*?})',
                        r'"playerList"\s*:\s*(\[.*?\])'
                    ]
                    
                    for pattern in json_patterns:
                        matches = re.search(pattern, page_source)
                        if matches:
                            print(f"Found JSON data with pattern {pattern}")
                            try:
                                json_str = matches.group(1)
                                # Try to parse the JSON
                                json_data = json.loads(json_str)
                                
                                # Extract player names from the JSON data
                                if isinstance(json_data, list):
                                    # If it's a list, assume it's a list of players
                                    for player in json_data:
                                        if isinstance(player, dict):
                                            for key in ['name', 'playerName', 'fullName', 'displayName']:
                                                if key in player:
                                                    player_name = player[key]
                                                    cleaned_name = clean_player_name(player_name)
                                                    if is_player_name(cleaned_name):
                                                        players.append(cleaned_name)
                                elif isinstance(json_data, dict):
                                    # If it's a dictionary, look for player data
                                    for key, value in json_data.items():
                                        if key in ['players', 'roster', 'team', 'playerList'] and isinstance(value, list):
                                            for player in value:
                                                if isinstance(player, dict):
                                                    for name_key in ['name', 'playerName', 'fullName', 'displayName']:
                                                        if name_key in player:
                                                            player_name = player[name_key]
                                                            cleaned_name = clean_player_name(player_name)
                                                            if is_player_name(cleaned_name):
                                                                players.append(cleaned_name)
                            except json.JSONDecodeError:
                                print(f"Failed to parse JSON data: {json_str[:100]}...")
                    
                    if players:
                        # Filter out duplicates
                        players = list(set(players))
                        print(f"Found {len(players)} player names in JSON data")
                        success = True
                        break  # We found players, no need to try other URLs
                except Exception as e:
                    print(f"Error extracting JSON data: {str(e)}")
                
                # If we didn't find players with the selectors, try looking for any text that could be player names
                if not found_players:
                    print("Trying to find player names in any text elements...")
                    elements = driver.find_elements(By.XPATH, "//*[contains(text(), ' ') and string-length(text()) > 5 and string-length(text()) < 30]")
                    
                    for element in elements:
                        try:
                            text = element.text.strip()
                            if text and len(text.split()) >= 2:
                                cleaned_name = clean_player_name(text)
                                if is_player_name(cleaned_name):
                                    if "Christian Braun" in cleaned_name:
                                        print("Found Christian Braun!")
                                    players.append(cleaned_name)
                        except Exception as e:
                            continue
                    
                    if players:
                        # Filter out duplicates
                        players = list(set(players))
                        print(f"Found {len(players)} potential player names in text elements")
                        success = True
                        break  # We found players, no need to try other URLs
                
                # If we still didn't find players, try looking for them in the page source
                if not found_players:
                    print("Trying to find player names in page source...")
                    page_source = driver.page_source
                    
                    # Look for patterns like "Player Name" in various formats
                    player_patterns = [
                        r'player-name"[^>]*>([^<]+)</span>',
                        r'player-name"[^>]*>([^<]+)</div>',
                        r'"playerName":"([^"]+)"',
                        r'"fullName":"([^"]+)"',
                        r'"displayName":"([^"]+)"',
                        r'"name":"([^"]+)"',
                        r'<td[^>]*>([A-Z][a-z]+ [A-Z][a-z]+)</td>',
                        r'<div[^>]*>([A-Z][a-z]+ [A-Z][a-z]+)</div>',
                        r'<span[^>]*>([A-Z][a-z]+ [A-Z][a-z]+)</span>'
                    ]
                    
                    for pattern in player_patterns:
                        matches = re.findall(pattern, page_source)
                        if matches:
                            print(f"Found {len(matches)} matches with pattern {pattern}")
                            for match in matches:
                                player_name = match.strip()
                                if player_name and len(player_name.split()) >= 2:
                                    cleaned_name = clean_player_name(player_name)
                                    if is_player_name(cleaned_name):
                                        if "Christian Braun" in cleaned_name:
                                            print("Found Christian Braun!")
                                        players.append(cleaned_name)
                    
                    if players:
                        # Filter out duplicates
                        players = list(set(players))
                        print(f"Found {len(players)} player names in page source")
                        success = True
                        break  # We found players, no need to try other URLs
            
            except Exception as e:
                print(f"Error with URL {url}: {str(e)}")
                save_debug_info(driver, f'error_{url.replace("https://", "").replace("/", "_")}')
        
        if success and players:
            # Filter and clean up player names
            cleaned_players = []
            for player in players:
                # Remove any non-alphabetic characters at the beginning or end
                player = player.strip()
                player = re.sub(r'^[^a-zA-Z]+', '', player)
                player = re.sub(r'[^a-zA-Z]+$', '', player)
                
                # Only add if it's a valid player name
                if is_player_name(player):
                    cleaned_players.append(player)
            
            # Remove duplicates and sort
            cleaned_players = sorted(list(set(cleaned_players)))
            
            # Check if we have a reasonable number of players
            if len(cleaned_players) >= 1:  # Even finding one valid player is a success
                players = cleaned_players
                print(f"Final list of {len(players)} players:")
                for player in players:
                    print(f"  - {player}")
                
                # Save players to database
                conn = sqlite3.connect('nba_stats.db', timeout=20)
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
                
                # Save to file
                with open('current_team.txt', 'w') as f:
                    for player in players:
                        f.write(f"{player}\n")
                print("Wrote players to current_team.txt")
            else:
                print(f"Found only {len(cleaned_players)} players, which seems too few. Not saving.")
                players = []
        else:
            print("No players found with any method")
    except Exception as e:
        print(f"Error scraping team roster: {str(e)}")
        save_debug_info(driver, 'error')
    finally:
        if conn:
            conn.close()
        driver.quit()
    
    return players


def read_credentials_from_file(file_path='credentials.txt'):
    """Read credentials from file or environment variables."""
    # Try to get credentials from environment variables first
    login_id = os.environ.get('NBA_LOGIN')
    password = os.environ.get('NBA_PWD')
    
    # If found in environment variables, return them
    if login_id and password:
        return login_id, password
    
    # Otherwise, try to read from credentials file
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                login_id = lines[0].strip()
                password = lines[1].strip()
                return login_id, password
    except FileNotFoundError:
        print(f"Credentials file {file_path} not found")
    except Exception as e:
        print(f"Error reading credentials file: {str(e)}")
    
    # If we get here, no credentials were found
    return None, None


def main():
    """Main function to run the scraper."""
    print("Starting team scraper")
    
    # Get credentials
    login_id, password = read_credentials_from_file()
    
    if not login_id or not password:
        print("Error: NBA_LOGIN and NBA_PWD environment variables must be set.")
        return
    
    print(f"Starting team scraper for {login_id}")
    
    # Use Chrome profile for better login success
    use_profile = True
    print("Using Chrome profile for better login success")
    
    # Scrape team roster
    players = scrape_team_roster(login_id, password, use_profile)
    
    # If no players found or fewer than expected, ask for manual entry
    if len(players) < 9:
        print(f"Found only {len(players)} players, which may be incomplete.")
        manual_entry = input("Would you like to manually enter your team roster? (y/n): ")
        
        if manual_entry.lower() == 'y':
            print("Enter player names one per line. Type 'done' when finished.")
            manual_players = []
            
            while True:
                player = input("Player name (or 'done' to finish): ")
                if player.lower() == 'done':
                    break
                if player:
                    manual_players.append(player)
            
            if manual_players:
                # Save manually entered players to database
                conn = sqlite3.connect('nba_stats.db', timeout=20)
                cursor = conn.cursor()
                
                # Delete existing players for this login
                cursor.execute('DELETE FROM nba_team_players WHERE login_id = ?', (login_id,))
                
                for player in manual_players:
                    cursor.execute(
                        'INSERT INTO nba_team_players (login_id, player_name) VALUES (?, ?)',
                        (login_id, player)
                    )
                
                conn.commit()
                conn.close()
                print(f"Successfully updated {len(manual_players)} players in database")
                
                # Save to file
                with open('current_team.txt', 'w') as f:
                    for player in manual_players:
                        f.write(f"{player}\n")
                print("Wrote players to current_team.txt")
                
                # Print current roster
                print("\nCurrent roster:")
                for player in manual_players:
                    print(f"- {player}")
    
    # Print current roster
    if players:
        print("\nCurrent roster:")
        for player in players:
            print(f"- {player}")


if __name__ == "__main__":
    main() 