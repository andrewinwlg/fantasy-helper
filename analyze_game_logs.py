import requests
import pandas as pd
from bs4 import BeautifulSoup

# Set URL for Cole Anthony's 2024-25 game logs
url = 'https://www.basketball-reference.com/players/a/anthoco01/gamelog/2025'

# Get the page content
response = requests.get(url)
html_content = response.text

print(f"Response status code: {response.status_code}")

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
    
    # Try to get the first few rows to see what's inside
    rows = table.find_all('tr', limit=3)
    if rows:
        print(f'  Sample headers/data from first rows:')
        for j, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            if cells:
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                print(f'    Row {j}: {cell_texts[:5]}... (showing first 5 cells)')

# Try with pandas
print("\nTrying pandas to read tables...")
try:
    tables_pd = pd.read_html(url)
    print(f"Found {len(tables_pd)} tables with pandas")
    
    # Look for the table that appears to be the game log
    for i, df in enumerate(tables_pd):
        print(f"\nTable {i} info:")
        # Print head
        if 'Date' in df.columns or 'G' in df.columns:
            print(f"  This appears to be a game log table with {len(df)} rows")
            print(f"  Columns: {list(df.columns)}")
            if len(df) > 5:
                print("\nFirst 5 rows:")
                print(df.head(5))
            else:
                print("\nAll rows:")
                print(df)
        else:
            print(f"  Columns: {list(df.columns)}")
except Exception as e:
    print(f"Error with pandas: {str(e)}")

# Check if there's a table with id="pgl_basic"
pgl_table = soup.find('table', id='pgl_basic')
if pgl_table:
    print("\nFound pgl_basic table (regular season game log)")
    # Try to parse it with pandas
    try:
        game_log = pd.read_html(str(pgl_table))[0]
        print(f"Success! Found {len(game_log)} rows in game log")
        print(f"Column names: {list(game_log.columns)}")
        print("\nFirst 5 rows:")
        print(game_log.head(5))
    except Exception as e:
        print(f"Error reading pgl_basic table: {str(e)}")
else:
    print("\nNo pgl_basic table found")
    
    # Look for any element containing text about game logs
    game_log_elements = soup.find_all(text=lambda text: text and 'game log' in text.lower())
    print(f"Found {len(game_log_elements)} elements mentioning 'game log':")
    for elem in game_log_elements:
        print(f"  '{elem}'")
        
# Try to see if there's any error message on the page
error_divs = soup.find_all('div', class_='error')
if error_divs:
    print("\nFound error messages on the page:")
    for div in error_divs:
        print(f"  {div.get_text(strip=True)}") 