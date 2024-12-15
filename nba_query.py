import sqlite3
import pandas as pd

# Connect to the database
conn = sqlite3.connect('nba_stats.db')

# Example queries:

# 1. Get top 10 scorers
query1 = "SELECT Player, Team, PTS FROM player_stats ORDER BY PTS DESC LIMIT 10"
top_scorers = pd.read_sql_query(query1, conn)
print("\nTop 10 Scorers:")
print(top_scorers)

# 2. Get all stats for a specific player
query2 = "SELECT * FROM player_stats WHERE Player = 'Luka Dončić'"
player_stats = pd.read_sql_query(query2, conn)
print("\nLuka Dončić's Stats:")
print(player_stats)

# 3. Get average points by team
query3 = "SELECT Team, AVG(PTS) as Avg_Points FROM player_stats GROUP BY Team ORDER BY Avg_Points DESC"
team_scoring = pd.read_sql_query(query3, conn)
print("\nTeam Scoring Averages:")
print(team_scoring)

# New queries for player game logs

# 4. Get top 5 individual game performances by points
query4 = """
SELECT player_url as Player, Date, PTS as Points, TRB as Rebounds, AST as Assists, Opp as Opponent
FROM player_game_logs 
ORDER BY CAST(PTS as INTEGER) DESC 
LIMIT 5
"""
top_games = pd.read_sql_query(query4, conn)
print("\nTop 5 Individual Scoring Performances:")
print(top_games)

# 5. Get players averaging a triple-double over their last 10 games
query5 = """
WITH last_10_games AS (
    SELECT player_url,
           AVG(CAST(PTS as FLOAT)) as avg_pts,
           AVG(CAST(TRB as FLOAT)) as avg_reb,
           AVG(CAST(AST as FLOAT)) as avg_ast,
           COUNT(*) as games_played
    FROM player_game_logs
    GROUP BY player_url
    HAVING games_played >= 10
)
SELECT player_url as Player, 
       ROUND(avg_pts, 1) as PPG,
       ROUND(avg_reb, 1) as RPG,
       ROUND(avg_ast, 1) as APG
FROM last_10_games
WHERE avg_pts >= 20
  AND avg_reb >= 5
  AND avg_ast >= 5
ORDER BY (avg_pts + avg_reb + avg_ast) DESC
LIMIT 10
"""
triple_double_players = pd.read_sql_query(query5, conn)
print("\nPlayers Averaging Triple-Double (Last 10 Games):")
print(triple_double_players)

# 6. Get players' home vs away scoring averages
query6 = """
SELECT 
    player_url as Player,
    ROUND(AVG(CASE WHEN "Unnamed:_5" = '@' THEN CAST(PTS as FLOAT) END), 1) as Away_PPG,
    ROUND(AVG(CASE WHEN "Unnamed:_5" IS NULL THEN CAST(PTS as FLOAT) END), 1) as Home_PPG,
    COUNT(*) as Games_Played
FROM player_game_logs
GROUP BY player_url
HAVING Games_Played >= 20
ORDER BY (Home_PPG + Away_PPG)/2 DESC
LIMIT 10
"""
home_away_splits = pd.read_sql_query(query6, conn)
print("\nTop 10 Players' Home vs Away Scoring:")
print(home_away_splits)

# Get table info
query = "PRAGMA table_info(player_game_logs);"
table_info = pd.read_sql_query(query, conn)
print("\nTable structure:")
print(table_info)

# Close the connection
conn.close()