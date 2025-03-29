import requests
import pandas as pd
from bs4 import BeautifulSoup

# Set URL for Cole Anthony's page
url = 'https://www.basketball-reference.com/players/a/anthoco01.html'

# Get the page content
response = requests.get(url)
html_content = response.text

# Parse with BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')

# Find all tables in the page
tables = soup.find_all('table')
print(f'Found {len(tables)} tables on the page')

# Print info about each table
for i, table in enumerate(tables):
    table_id = table.get('id', 'No ID')
    caption = table.find('caption')
    caption_text = caption.get_text(strip=True) if caption else 'No caption'
    print(f'Table {i}: ID={table_id}, Caption={caption_text}')
    
    # Check if it's the 2024-25 season table
    if '2024-25' in caption_text and 'Regular Season' in caption_text:
        print(f'  THIS IS THE 2024-25 REGULAR SEASON TABLE')
        
        # Try to read the table using pandas
        print("  Attempting to read with pandas...")
        try:
            game_log = pd.read_html(str(table))[0]
            print(f"  Success! Found {len(game_log)} rows")
            print(f"  Column names: {list(game_log.columns)}")
            
            # Print first few rows
            print("\nFirst 5 rows:")
            print(game_log.head(5))
        except Exception as e:
            print(f"  Error reading table: {str(e)}")

# Alternatively, try pandas directly on the URL
print("\nTrying pandas directly on the URL...")
try:
    all_tables = pd.read_html(url)
    print(f"Found {len(all_tables)} tables with pandas")
    
    # Look for the table that might contain game logs
    for i, table_df in enumerate(all_tables):
        if 'Date' in table_df.columns and 'Tm' in table_df.columns:
            print(f"Table {i} appears to be a game log:")
            print(f"Columns: {list(table_df.columns)}")
            print(f"Rows: {len(table_df)}")
            print("\nFirst 5 rows:")
            print(table_df.head(5))
except Exception as e:
    print(f"Error with pandas: {str(e)}") 