import sqlite3
import pandas as pd

# Connect to the database
conn = sqlite3.connect('nba_stats.db')


# Get table info
query = "PRAGMA table_info(player_game_logs);"
table_info = pd.read_sql_query(query, conn)
print("\nTable structure:")
print(table_info)

# Get table info
query = "PRAGMA table_info(player_stats);"
table_info = pd.read_sql_query(query, conn)
print("\nTable structure:")
print(table_info)

# Close the connection
conn.close()