import sqlite3
import pandas as pd

# Connect to the database
conn = sqlite3.connect('nba_stats.db')

# Example queries:

# 1. Get top 10 scorers
query1 = "SELECT Player, Team, PTS FROM player_stats ORDER BY PTS DESC LIMIT 10"
top_scorers = pd.read_sql_query(query1, conn)
top_scorers.index = top_scorers.reset_index(drop=True).index + 1
print("\nTop 10 Scorers:")
print(top_scorers)

# 2. Get all stats for a specific player
query2 = "SELECT * FROM player_stats WHERE Player = 'Luka Dončić'"
player_stats = pd.read_sql_query(query2, conn)
player_stats.index = player_stats.reset_index(drop=True).index + 1
print("\nLuka Dončić's Stats:")
print(player_stats)

# 3. Get average points by team
query3 = "SELECT Team, AVG(PTS) as Avg_Points FROM player_stats GROUP BY Team ORDER BY Avg_Points DESC"
team_scoring = pd.read_sql_query(query3, conn)
team_scoring.index = team_scoring.reset_index(drop=True).index + 1
print("\nTeam Scoring Averages:")
print(team_scoring)

# New queries for player game logs

# 4. Get top 5 individual game performances by points with player names
query4 = """
SELECT 
    ps.Player as Player_Name,
    pgl.Date,
    pgl.PTS as Points,
    pgl.TRB as Rebounds,
    pgl.AST as Assists,
    pgl.Opp as Opponent,
    pgl.player_url
FROM player_game_logs pgl
JOIN player_stats ps ON ps.player_url = pgl.player_url
ORDER BY CAST(pgl.PTS as INTEGER) DESC 
LIMIT 5
"""
top_games = pd.read_sql_query(query4, conn)
top_games.index = top_games.reset_index(drop=True).index + 1
print("\nTop 5 Individual Scoring Performances:")
print(top_games)

# 5. Get players averaging high stats with player names
query5 = """
WITH last_10_games AS (
    SELECT 
        pgl.player_url,
        ps.Player as Player_Name,
        AVG(CAST(pgl.PTS as FLOAT)) as avg_pts,
        AVG(CAST(pgl.TRB as FLOAT)) as avg_reb,
        AVG(CAST(pgl.AST as FLOAT)) as avg_ast,
        COUNT(*) as games_played
    FROM player_game_logs pgl
    JOIN player_stats ps ON ps.player_url = pgl.player_url
    GROUP BY pgl.player_url, ps.Player
    HAVING games_played >= 10
)
SELECT 
    Player_Name,
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
triple_double_players.index = triple_double_players.reset_index(drop=True).index + 1
print("\nPlayers with High Stats (Last 10 Games):")
print(triple_double_players)

# 6. Get players' home vs away scoring averages with player names
query6 = """
SELECT 
    ps.Player as Player_Name,
    ROUND(AVG(CASE WHEN "Unnamed:_5" = '@' THEN CAST(pgl.PTS as FLOAT) END), 1) as Away_PPG,
    ROUND(AVG(CASE WHEN "Unnamed:_5" IS NULL THEN CAST(pgl.PTS as FLOAT) END), 1) as Home_PPG,
    COUNT(*) as Games_Played
FROM player_game_logs pgl
JOIN player_stats ps ON ps.player_url = pgl.player_url
GROUP BY ps.Player, pgl.player_url
HAVING Games_Played >= 20
ORDER BY (Home_PPG + Away_PPG)/2 DESC
LIMIT 10
"""
home_away_splits = pd.read_sql_query(query6, conn)
home_away_splits.index = home_away_splits.reset_index(drop=True).index + 1
print("\nTop 10 Players' Home vs Away Scoring:")
print(home_away_splits)

#7. Get players with the most games played
query7 = """
SELECT 
    ps.Player,
    COUNT(*) as Games_Played 
FROM player_game_logs pgl
JOIN player_stats ps ON ps.player_url = pgl.player_url
GROUP BY ps.Player, pgl.player_url 
ORDER BY Games_Played DESC 
LIMIT 10
"""
most_games_played = pd.read_sql_query(query7, conn)
most_games_played.index = most_games_played.reset_index(drop=True).index + 1
print("\nPlayers with the Most Games Played:")
print(most_games_played)

#8. Get players with highest scoring games this season
query8 = """
SELECT 
    ps.Player as Player_Name,
    pgl.Date,
    pgl.Opp as Opponent,
    pgl.PTS as Points,
    pgl.TRB as Rebounds,
    pgl.AST as Assists
FROM player_game_logs pgl
JOIN player_stats ps ON ps.player_url = pgl.player_url
ORDER BY CAST(pgl.PTS as INTEGER) DESC
LIMIT 10
"""
highest_scoring_games = pd.read_sql_query(query8, conn)
highest_scoring_games.index = highest_scoring_games.reset_index(drop=True).index + 1
print("\nHighest Individual Scoring Games This Season:")
print(highest_scoring_games)

# Close the connection
conn.close()