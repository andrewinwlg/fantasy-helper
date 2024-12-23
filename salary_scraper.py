import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from threading import Thread

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def get_salary_cap_data(driver, page=1, max_retries=3):
    """
    Fetch salary cap data with retries and longer timeouts
    """
    url = f"https://nbafantasy.nba.com/statistics/players?page={page}"
    
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1} for page {page}")
            
            # Go directly to the page
            driver.get(url)
            time.sleep(2)
            
            # Handle cookie consent
            accept_cookies(driver)
            
            # Wait for React
            wait = WebDriverWait(driver, 30)
            print("Waiting for table to load...")
            
            # Look for the specific table row class
            table = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ElementTable__ElementRow-sc-8zrnbf-3")
            )).find_element(By.XPATH, "./..")
            
            print("Found table, getting rows...")
            rows = table.find_elements(By.CLASS_NAME, "ElementTable__ElementRow-sc-8zrnbf-3")
            
            data = []
            total_players = 0  # Add counter
            for i, row in enumerate(rows):
                try:
                    print(f"\nProcessing row {i+1}/{len(rows)}")
                    
                    # Get the player name from the button text
                    name_button = row.find_element(By.CLASS_NAME, "Statistics__ElementNameButton-sc-14oh6cf-7")
                    name_div = name_button.find_element(By.CLASS_NAME, "Statistics__Name-sc-14oh6cf-8")
                    name = name_div.find_element(By.CLASS_NAME, "Utils__Ellipsis-sc-1eav01y-0").text
                    print(f"Found player: {name}")
                    
                    # Get team from the team div
                    team = row.find_element(By.CLASS_NAME, "Statistics__Team-sc-14oh6cf-9").text
                    print(f"Team: {team}")
                    
                    # Get all td elements
                    cols = row.find_elements(By.TAG_NAME, "td")
                    print(f"Column values: {[col.text for col in cols]}")
                    
                    player_data = {
                        'name': name,
                        'team': team,
                        'avgPoints': float(cols[2].text),
                        'ownership': float(cols[3].text.replace('%', '')),
                        'gamesPlayed': float(cols[4].text),
                        'totalPoints': float(cols[5].text)
                    }
                    data.append(player_data)
                    total_players += 1  # Increment counter
                    print(f"Successfully processed row (Total players: {total_players})")
                    
                except Exception as e:
                    print(f"Error processing row {i+1}: {str(e)}")
                    print(f"Row HTML: {row.get_attribute('outerHTML')}")
                    continue
            
            try:
                # Find Next button first to see if we have more pages
                next_button = find_pagination_button(driver, "Next")
                if next_button and "fdivGe" in next_button.get_attribute("class"):
                    print("Found enabled Next button - we have multiple pages")
                    
                    # Get first player name before clicking
                    first_player = driver.find_element(By.CLASS_NAME, "Utils__Ellipsis-sc-1eav01y-0").text
                    print(f"Current first player: {first_player}")
                    
                    # Click Next to see if we can determine total pages
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    
                    # Wait for table to update
                    if wait_for_table_update(driver, first_player):
                        print("Table updated successfully")
                        total_pages = 2
                        
                        # Get data from page 2
                        page2_data = scrape_table_data(driver)
                        if page2_data is not None:
                            data.extend(page2_data)
                        
                        # Keep clicking Next until it's disabled
                        while True:
                            next_button = find_pagination_button(driver, "Next")
                            if not next_button or "STgrV" in next_button.get_attribute("class"):
                                break
                            
                            # Get current first player before clicking
                            first_player = driver.find_element(By.CLASS_NAME, "Utils__Ellipsis-sc-1eav01y-0").text
                            
                            driver.execute_script("arguments[0].click();", next_button)
                            
                            # Wait for table to update
                            if not wait_for_table_update(driver, first_player):
                                print("Table failed to update")
                                break
                                
                            total_pages += 1
                            print(f"Successfully moved to page {total_pages}")
                            
                            # Get data from this page
                            page_data = scrape_table_data(driver)
                            if page_data is not None:
                                data.extend(page_data)
                        
                        print(f"Found {total_pages} total pages")
                        
                    else:
                        print("Table failed to update after clicking Next")
                        total_pages = 1
                else:
                    print("Next button disabled - only one page")
                    total_pages = 1
                
                # Create DataFrame from all collected data
                df = pd.DataFrame(data)
                df['timestamp'] = datetime.now()
                
                return df, total_pages

            except Exception as e:
                print(f"Error finding pagination: {str(e)}")
                # Return what we have with 1 page
                return df, 1
            
        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                return None, None
            print("Retrying...")
            time.sleep(5)
    
    return None, None

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

def wait_for_table_update(driver, current_first_player):
    """Wait for table to update with new data"""
    try:
        # Wait up to 10 seconds for the first player name to change
        wait = WebDriverWait(driver, 10)
        wait.until(lambda d: 
            d.find_element(By.CLASS_NAME, "Utils__Ellipsis-sc-1eav01y-0").text != current_first_player
        )
        return True
    except:
        return False

def scrape_table_data(driver):
    """Scrape data from current table view"""
    try:
        table = driver.find_element(By.CSS_SELECTOR, ".ElementTable__ElementRow-sc-8zrnbf-3").find_element(By.XPATH, "./..")
        rows = table.find_elements(By.CLASS_NAME, "ElementTable__ElementRow-sc-8zrnbf-3")
        
        data = []
        total_players = 0  # Add counter
        for i, row in enumerate(rows):
            try:
                print(f"\nProcessing row {i+1}/{len(rows)}")
                
                name_button = row.find_element(By.CLASS_NAME, "Statistics__ElementNameButton-sc-14oh6cf-7")
                name_div = name_button.find_element(By.CLASS_NAME, "Statistics__Name-sc-14oh6cf-8")
                name = name_div.find_element(By.CLASS_NAME, "Utils__Ellipsis-sc-1eav01y-0").text
                print(f"Found player: {name}")
                
                team = row.find_element(By.CLASS_NAME, "Statistics__Team-sc-14oh6cf-9").text
                print(f"Team: {team}")
                
                cols = row.find_elements(By.TAG_NAME, "td")
                print(f"Column values: {[col.text for col in cols]}")
                
                player_data = {
                    'name': name,
                    'team': team,
                    'avgPoints': float(cols[2].text),
                    'ownership': float(cols[3].text.replace('%', '')),
                    'gamesPlayed': float(cols[4].text),
                    'totalPoints': float(cols[5].text)
                }
                data.append(player_data)
                total_players += 1  # Increment counter
                print(f"Successfully processed row (Total players: {total_players})")
                
            except Exception as e:
                print(f"Error processing row {i+1}: {str(e)}")
                continue
        
        return data
    except Exception as e:
        print(f"Error scraping table data: {str(e)}")
        return None

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

def scrape_all_salaries():
    """
    Scrape all pages of salary data and save to database
    """
    conn = sqlite3.connect('nba_stats.db')
    driver = None
    
    try:
        print("\nInitializing Chrome...")
        
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument("--remote-debugging-port=9222")
        
        # User agent and automation hiding
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Linux paths
        options.binary_location = '/usr/bin/google-chrome'
        
        print("\nStarting Chrome driver...")
        service = Service(
            executable_path='/usr/local/bin/chromedriver',
            log_output="chromedriver.log"
        )
        
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set window size explicitly
        driver.set_window_size(1920, 1080)
        
        # Try to mask webdriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.set_page_load_timeout(180)
        print("Chrome driver started successfully")
        
        # Get first page to determine total pages
        print("\nFetching first page...")
        df, total_pages = get_salary_cap_data(driver, 1)
        if df is None:
            print("Failed to fetch initial data")
            return
        
        print(f"\nFound {total_pages} total pages")
        print("\nColumns in the data:")
        print(df.columns.tolist())
        print("\nSample row:")
        print(df.iloc[0])
        
        all_data = [df]
        
        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            print(f"\nNavigating to page {page} of {total_pages}")
            if not go_to_page(driver, page):
                print(f"Failed to navigate to page {page}")
                continue
            
            df, _ = get_salary_cap_data(driver, page)
            if df is not None:
                all_data.append(df)
                print(f"Successfully fetched page {page}")
            else:
                print(f"Failed to fetch page {page}")
            time.sleep(1)
        
        # Combine all data
        final_df = pd.concat(all_data, ignore_index=True)
        
        # Save to database
        final_df.to_sql('nba_salary_cap_players', conn, if_exists='replace', index=False)
        print(f"\nSaved salary data for {len(final_df)} players")
        
        # Create view
        print("\nCreating database view...")
        conn.execute("""
        CREATE VIEW IF NOT EXISTS player_salary_stats AS
        SELECT 
            ps.Player,
            nsc.salary as Current_Salary,
            nsc.avgPoints as Avg_Fantasy_Points,
            nsc.gamesPlayed as Games_Played,
            ROUND(nsc.avgPoints * 1000.0 / NULLIF(nsc.salary, 0), 2) as Value_Average_Points,
            ROUND(nsc.avgPoints * nsc.gamesPlayed * 1000.0 / NULLIF(nsc.salary, 0), 2) as Value_Total_Points
        FROM player_stats ps
        LEFT JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        WHERE nsc.avgPoints > 0
        ORDER BY Value_Average_Points DESC
        """)
        print("View created successfully")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
    
    finally:
        print("\nCleaning up...")
        if driver:
            driver.quit()
        conn.close()
        print("Done!")

def go_to_page(driver, page_number):
    """Helper function to navigate to a specific page"""
    try:
        # Find and click Next button
        next_button = find_pagination_button(driver, "Next")
        if next_button and "fdivGe" in next_button.get_attribute("class"):  # Check for enabled class
            print("Clicking Next button")
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(2)
            return True
        return False
    except Exception as e:
        print(f"Error navigating to page {page_number}: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting salary scraper...")
    scrape_all_salaries()
    print("\nPress Enter to exit...")
    input()