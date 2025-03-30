"""NBA Fantasy roster optimization using linear programming."""

import argparse
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import pulp
import seaborn as sns
from pulp import LpMaximize, LpProblem, LpVariable, lpSum
import numpy as np

from utils import reorder_current_team


@dataclass
class RosterConstraints:
    """Container for roster optimization constraints."""
    salary_cap: int = 100
    front_court_req: int = 5
    back_court_req: int = 5
    max_per_team: int = 2

def get_player_data() -> pd.DataFrame:
    """Get player data with positions and 30-day stats."""
    query = """
    SELECT 
        ps.Player,
        ps.Pos,
        ps.Team,
        nsc.salary,
        psr.Fantasy_Points_Per_Game_30D as avg_fpts,
        psr.Fantasy_Points_Per_Game_15D,
        psr.Fantasy_Points_Per_Game_7D,
        psr.Games_Last_30D,
        psr.Games_Last_15D,
        psr.Games_Last_7D,
        psr.Value_Per_Game_30D as value,
        pi.injury_type,
        pi.expected_return
    FROM player_stats ps
    JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    LEFT JOIN (
        SELECT pi1.* 
        FROM player_injuries pi1
        INNER JOIN (
            SELECT player_name, MAX(report_date) as max_date
            FROM player_injuries
            GROUP BY player_name
        ) pi2 ON pi1.player_name = pi2.player_name AND pi1.report_date = pi2.max_date
    ) pi ON ps.Player = pi.player_name
    WHERE psr.Games_Last_30D >= 3  -- Minimum games played
    AND nsc.salary > 0
    """
    
    conn = None
    try:
        conn = sqlite3.connect('nba_stats.db')
        df = pd.read_sql(query, conn)
        
        # Create front_court/back_court indicators
        df['is_front_court'] = df['Pos'].str.contains('F|C')
        df['is_back_court'] = df['Pos'].str.contains('G')
        
        # Exclude injured players with return dates more than 2 days away
        today = pd.Timestamp.now().normalize()
        injured_players = df[
            df['expected_return'].notna() & 
            (pd.to_datetime(df['expected_return']) > today + pd.Timedelta(days=2))
        ]['Player'].tolist()
        
        if injured_players:
            print("\nAutomatically excluding the following injured players:")
            for player in injured_players:
                injury_info = df[df['Player'] == player].iloc[0]
                print(f"- {player}: {injury_info['injury_type']}, Expected return: {injury_info['expected_return']}")
            df = df[~df['Player'].isin(injured_players)]
        
        return df
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def optimize_roster(
    df: pd.DataFrame, 
    salary_cap: float = 100.0,
    constraints: RosterConstraints = RosterConstraints(),
    excluded_players: list = None,
    debug_flag: bool = False,
    weights: dict = None
) -> pd.DataFrame:
    """Optimize roster using linear programming."""
    
    # Debug: Print initial dataframe info
    print(f"\nInitial dataset size: {len(df)} players")
    if debug_flag and excluded_players:
        print(f"Players to exclude: {excluded_players}")
    
    # Filter out excluded players if any are specified
    if excluded_players:
        # Debug: Print players found/not found in dataset
        found_players = set(df[df['Player'].isin(excluded_players)]['Player'])
        not_found = set(excluded_players) - found_players
        if not_found:
            print(f"Warning: Some excluded players not found in dataset: {not_found}")
        
        # Filter and show how many were excluded
        initial_count = len(df)
        df = df[~df['Player'].isin(excluded_players)].copy()
        excluded_count = initial_count - len(df)
        print(f"Excluded {excluded_count} players from optimization")
        
        if debug_flag:
            print("Excluded players that were found in dataset:")
            print(found_players)
    
    if len(df) < 10:
        raise ValueError(f"Not enough players ({len(df)}) to create a valid roster after exclusions")
    
    # Calculate composite score if weights are provided
    if weights:
        df = calculate_composite_score(df, weights)
        # Use composite score for optimization
        objective_column = 'composite_score'
        print("\nUsing composite score for optimization with weights:")
        for key, value in weights.items():
            print(f"  {key}: {value}")
    else:
        # Use 30-day average if no weights provided
        objective_column = 'avg_fpts'
        print("\nUsing 30-day average fantasy points for optimization")
    
    prob = LpProblem("NBA_Fantasy_Roster", LpMaximize)
    player_vars = LpVariable.dicts("players", ((i) for i in df.index), 0, 1, 'Binary')
    
    # Objective: Maximize total fantasy points or composite score
    prob += lpSum([df.loc[i, objective_column] * player_vars[i] for i in df.index])
    
    # Constraints
    prob += lpSum([df.loc[i, 'salary'] * player_vars[i] for i in df.index]) <= salary_cap
    prob += lpSum([player_vars[i] for i in df.index]) == 10
    prob += lpSum([player_vars[i] * df.loc[i, 'is_front_court'] for i in df.index]) == constraints.front_court_req
    prob += lpSum([player_vars[i] * df.loc[i, 'is_back_court'] for i in df.index]) == constraints.back_court_req
    
    # Max players per team
    for team in df['Team'].unique():
        team_players = df[df['Team'] == team].index
        prob += lpSum([player_vars[i] for i in team_players]) <= constraints.max_per_team

    pulp.LpSolverDefault.msg = debug_flag  # Set to True to show output, False to suppress
    prob.solve()
    
    # Debug: Print optimization status
    if debug_flag:
        print(f"\nOptimization Status: {pulp.LpStatus[prob.status]}")
    
    return get_selected_players(df, player_vars, objective_column)

def get_selected_players(df: pd.DataFrame, player_vars: Dict, objective_column: str = 'avg_fpts') -> pd.DataFrame:
    """Get selected players from optimization results."""
    selected_players = []
    for i in df.index:
        if player_vars[i].value() == 1:
            player_data = {
                'Player': df.loc[i, 'Player'],
                'Position': df.loc[i, 'Pos'],
                'Team': df.loc[i, 'Team'],
                'Salary': df.loc[i, 'salary'],
                'Avg_Fantasy_Points': df.loc[i, 'avg_fpts'],
                'Value': df.loc[i, 'value']
            }
            
            # Add additional metrics if available
            if 'Fantasy_Points_Per_Game_15D' in df.columns:
                player_data['Avg_15D'] = df.loc[i, 'Fantasy_Points_Per_Game_15D']
            
            if 'Fantasy_Points_Per_Game_7D' in df.columns:
                player_data['Avg_7D'] = df.loc[i, 'Fantasy_Points_Per_Game_7D']
                
            if 'consistency_score' in df.columns:
                player_data['Consistency'] = df.loc[i, 'consistency_score']
                
            if 'recent_trend_norm' in df.columns:
                player_data['Trend'] = df.loc[i, 'recent_trend_norm']
                
            if 'composite_score' in df.columns:
                player_data['Composite_Score'] = df.loc[i, 'composite_score']
                
            selected_players.append(player_data)
    
    result_df = pd.DataFrame(selected_players)
    
    # Sort by the objective column used in optimization
    if objective_column in df.columns and objective_column != 'avg_fpts':
        sort_column = 'Composite_Score' if objective_column == 'composite_score' else objective_column
        if sort_column in result_df.columns:
            result_df = result_df.sort_values(sort_column, ascending=False)
    else:
        result_df = result_df.sort_values('Avg_Fantasy_Points', ascending=False)
    
    return result_df

def visualize_roster(roster: pd.DataFrame) -> None:
    """Create visualizations for the optimal roster."""
    sns.set(style='whitegrid')
    
    # Create figure with subplots
    fig = plt.figure(figsize=(15, 15))
    
    # 1. Salary distribution
    plt.subplot(3, 2, 1)
    sns.barplot(data=roster, x='Position', y='Salary')
    plt.title('Salary Distribution by Position')
    plt.xticks(rotation=45)
    
    # 2. Fantasy points by player (30D)
    plt.subplot(3, 2, 2)
    sns.barplot(data=roster.sort_values('Avg_Fantasy_Points_30D', ascending=False), 
                x='Player', y='Avg_Fantasy_Points_30D')
    plt.title('30-Day Fantasy Points by Player')
    plt.xticks(rotation=45)
    
    # 3. Team distribution
    plt.subplot(3, 2, 3)
    team_counts = roster['Team'].value_counts()
    sns.barplot(x=team_counts.index, y=team_counts.values)
    plt.title('Players per Team')
    plt.xticks(rotation=45)
    
    # 4. Composite score by player
    plt.subplot(3, 2, 4)
    sns.barplot(data=roster.sort_values('Composite_Score', ascending=False), 
                x='Player', y='Composite_Score')
    plt.title('Composite Score by Player')
    plt.xticks(rotation=45)
    
    # 5. Consistency by player
    plt.subplot(3, 2, 5)
    sns.barplot(data=roster.sort_values('Consistency', ascending=False), 
                x='Player', y='Consistency')
    plt.title('Consistency Score by Player')
    plt.xticks(rotation=45)
    
    # 6. Fantasy points vs Salary
    plt.subplot(3, 2, 6)
    sns.scatterplot(data=roster, x='Salary', y='Composite_Score')
    plt.title('Composite Score vs Salary')
    for i, row in roster.iterrows():
        plt.annotate(row['Player'], (row['Salary'], row['Composite_Score']))
    
    plt.tight_layout()
    plt.show()

def optimize_team_changes(
    current_roster: pd.DataFrame, 
    available_players: pd.DataFrame, 
    salary_cap: float = 100.0, 
    transactions: int = 2,
    excluded_players: list = None,
    debug_flag: bool = False,
    replace: bool = False,
    weights: dict = None
) -> None:
    """Optimize which players to drop and which to add."""
    
    # Filter out excluded players if any are specified
    if excluded_players:
        # Debug: Print players found/not found in dataset
        found_players = set(available_players[available_players['Player'].isin(excluded_players)]['Player'])
        not_found = set(excluded_players) - found_players
        if not_found:
            print(f"Warning: Some excluded players not found in available players: {not_found}")
        
        # Filter and show how many were excluded
        initial_count = len(available_players)
        available_players = available_players[~available_players['Player'].isin(excluded_players)].copy()
        excluded_count = initial_count - len(available_players)
        print(f"Excluded {excluded_count} players from available players pool")
    
    # Calculate composite scores if weights are provided
    if weights:
        current_roster = calculate_composite_score(current_roster, weights)
        available_players = calculate_composite_score(available_players, weights)
        objective_column = 'composite_score'
        print("\nUsing composite score for optimization with weights:")
        for key, value in weights.items():
            print(f"  {key}: {value}")
    else:
        objective_column = 'avg_fpts'
        print("\nUsing 30-day average fantasy points for optimization")
    
    # Create the model
    prob = LpProblem("NBA_Team_Changes", LpMaximize)
    
    # Create binary variables for current players (to drop)
    drop_vars = LpVariable.dicts("drop", ((i) for i in current_roster.index), 0, 1, 'Binary')
    
    # Create binary variables for available players (to add)
    add_vars = LpVariable.dicts("add", ((i) for i in available_players.index), 0, 1, 'Binary')
    
    # Objective: Maximize total fantasy points or composite score after changes
    prob += lpSum([available_players.loc[i, objective_column] * add_vars[i] for i in available_players.index]) - \
            lpSum([current_roster.loc[i, objective_column] * drop_vars[i] for i in current_roster.index])
    
    # Define players that cannot be dropped
    protected_players = ['Nikola Jokic','Giannis Antetokounmpo']  # Add the names of players you want to protect
    
    # Debug: Print expected_return for all players
    print("\nDebug - Current roster expected_return dates:")
    for idx, player in current_roster.iterrows():
        print(f"{player['Player']}: {player['expected_return']}")
    
    # Identify injured players with return dates more than 2 weeks away
    today = pd.Timestamp.now().normalize()
    print(f"Today's date: {today}")
    print(f"Cutoff date for long-term injuries: {today + pd.Timedelta(days=4)}")
    
    # Convert expected_return to datetime
    current_roster['expected_return_dt'] = pd.to_datetime(current_roster['expected_return'], errors='coerce')
    
    # Debug: Print converted dates
    print("\nDebug - Converted dates:")
    for idx, player in current_roster.iterrows():
        if pd.notna(player['expected_return_dt']):
            print(f"{player['Player']}: {player['expected_return_dt']} - Is long term: {player['expected_return_dt'] > today + pd.Timedelta(days=4)}")
    
    long_term_injured_players = current_roster[
        current_roster['expected_return_dt'].notna() & 
        (current_roster['expected_return_dt'] > today + pd.Timedelta(days=4))
    ]
    
    print(f"\nFound {len(long_term_injured_players)} long-term injured players")
    
    # Constraints
    prob += lpSum([drop_vars[i] for i in current_roster.index]) <= transactions  # Drop at most  'transactions' players
    prob += lpSum([add_vars[i] for i in available_players.index]) <= transactions  # Add at most 'transactions' players
    prob += lpSum([drop_vars[i] for i in current_roster.index]) == lpSum([add_vars[i] for i in available_players.index]) <= transactions  # Add and drop the same amount
    
    # Salary cap constraint
    total_salary = (
        lpSum([current_roster.loc[i, 'salary'] for i in current_roster.index]) + 
        lpSum([available_players.loc[i, 'salary'] * add_vars[i] for i in available_players.index]) - 
        lpSum([current_roster.loc[i, 'salary'] * drop_vars[i] for i in current_roster.index])
    )
    prob += total_salary <= salary_cap  # Ensure the total salary does not exceed the cap
    
    # Add constraints to prevent dropping protected players
    for player in protected_players:
        player_index = current_roster[current_roster['Player'] == player].index
        if not player_index.empty:
            prob += drop_vars[player_index[0]] == 0  # Set drop variable to 0 for protected players
    
    # Add constraints to force dropping long-term injured players
    if not long_term_injured_players.empty:
        print("\nPrioritizing dropping the following long-term injured players:")
        for _, player in long_term_injured_players.iterrows():
            print(f"- {player['Player']}: {player['injury_type']}, Expected return: {player['expected_return']}")
            # Force the optimizer to drop this player
            prob += drop_vars[player.name] == 1
    
    # Debugging: Print the constraints if debug_flag is set
    if debug_flag:
        print("Constraints:")
        for constraint in prob.constraints.values():
            print(constraint)

    # Calculate current counts of front court and back court players
    current_front_court_count = current_roster['is_front_court'].sum()
    current_back_court_count = current_roster['is_back_court'].sum()
    
    # Front court and back court constraints
    prob += lpSum([add_vars[i] for i in available_players.index if available_players.loc[i, 'is_front_court']]) + \
            current_front_court_count - lpSum([current_roster.loc[i, 'is_front_court'] * drop_vars[i] for i in current_roster.index]) == 5  # Total front court players
    prob += lpSum([add_vars[i] for i in available_players.index if available_players.loc[i, 'is_back_court']]) + \
            current_back_court_count - lpSum([current_roster.loc[i, 'is_back_court'] * drop_vars[i] for i in current_roster.index]) == 5  # Total back court players
    
    # Max players per team
    for team in available_players['Team'].unique():
        team_players = available_players[available_players['Team'] == team].index
        prob += lpSum([add_vars[i] for i in team_players]) <= 2  # Max 2 players from the same team
        current_team_players = current_roster[current_roster['Team'] == team].index
        prob += lpSum([drop_vars[i] for i in current_team_players]) <= 2  # Max 2 players from the same team to drop

    # Suppress solver output based on debug_flag
    pulp.LpSolverDefault.msg = debug_flag
    prob.solve()
    
    # Check if the problem is feasible
    if prob.status != 1:  # 1 indicates an optimal solution
        print("The optimization problem is infeasible. Please check the constraints.")
        return
    
    # Get results and print them
    players_to_drop, players_to_add = print_optimization_results(current_roster, available_players, drop_vars, add_vars)
    
    if replace:
        while True:
            response = input("\nDo you want to apply these changes to current_team.txt? (yes/no): ").lower()
            if response in ['yes', 'y', 'no', 'n']:
                break
            print("Please answer 'yes' or 'no'")
        
        if response in ['yes', 'y']:
            # Read current team
            with open('current_team.txt', 'r') as f:
                current_players = [line.strip() for line in f.readlines()]
            
            # Remove dropped players and add new players
            for player in players_to_drop:
                current_players.remove(player['Player'])
            for player in players_to_add:
                current_players.append(player['Player'])
            
            # Write updated team back to file
            with open('current_team.txt', 'w') as f:
                for player in current_players:
                    f.write(f"{player}\n")
            
            print("\nUpdated current_team.txt with the new roster")
            
            # Reorder the team by 30-day average
            reorder_current_team()
        else:
            print("\nNo changes made to current_team.txt")

def load_current_team(file_path: str) -> pd.DataFrame:
    """Load current team players from a text file."""
    with open(file_path, 'r') as file:
        players = [line.strip() for line in file.readlines()]
    
    # Fetch player stats for the current roster
    query = f"""
    SELECT 
        ps.Player,
        ps.Pos,
        ps.Team,
        nsc.salary,
        psr.Fantasy_Points_Per_Game_30D as avg_fpts,
        psr.Fantasy_Points_Per_Game_15D,
        psr.Fantasy_Points_Per_Game_7D,
        psr.Games_Last_30D,
        psr.Games_Last_15D,
        psr.Games_Last_7D,
        psr.Value_Per_Game_30D as value,
        pi.injury_type,
        pi.expected_return
    FROM player_stats ps
    JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    LEFT JOIN (
        SELECT pi1.* 
        FROM player_injuries pi1
        INNER JOIN (
            SELECT player_name, MAX(report_date) as max_date
            FROM player_injuries
            GROUP BY player_name
        ) pi2 ON pi1.player_name = pi2.player_name AND pi1.report_date = pi2.max_date
    ) pi ON ps.Player = pi.player_name
    WHERE ps.Player IN ({', '.join(['"' + player + '"' for player in players])})
    """
    
    conn = None
    try:
        conn = sqlite3.connect('nba_stats.db')
        current_roster = pd.read_sql(query, conn)
        
        # Check if exactly 10 players were found
        if len(current_roster) != 10:
            raise ValueError(f"Expected 10 players, but found {len(current_roster)}. Please check the current_team.txt file.")
        
        # Create front_court/back_court indicators for current roster
        current_roster['is_front_court'] = current_roster['Pos'].str.contains('F|C')
        current_roster['is_back_court'] = current_roster['Pos'].str.contains('G')
        
        # Check for injured players
        today = pd.Timestamp.now().normalize()
        injured_players = current_roster[
            current_roster['expected_return'].notna() & 
            (pd.to_datetime(current_roster['expected_return']) > today + pd.Timedelta(days=2))
        ]
        
        if not injured_players.empty:
            print("\nWarning: The following players on your current roster are injured:")
            for _, player in injured_players.iterrows():
                print(f"- {player['Player']}: {player['injury_type']}, Expected return: {player['expected_return']}")
        
        return current_roster
    except Exception as e:
        print(f"Error loading current team: {e}")
        raise
    finally:
        if conn:
            conn.close()

def print_optimization_results(current_roster: pd.DataFrame, available_players: pd.DataFrame, drop_vars: Dict, add_vars: Dict) -> tuple:
    """Print the results of the optimization and return the changes."""
    # Get players to drop
    players_to_drop = [
        {
            'Player': current_roster.loc[i, 'Player'],
            'Position': current_roster.loc[i, 'Pos'],
            'Salary': current_roster.loc[i, 'salary'],
            'Avg_Fantasy_Points': current_roster.loc[i, 'avg_fpts'],
            'Value': current_roster.loc[i, 'value']
        }
        for i in current_roster.index if drop_vars[i].value() == 1
    ]
    
    # Get players to add
    players_to_add = [
        {
            'Player': available_players.loc[i, 'Player'],
            'Position': available_players.loc[i, 'Pos'],
            'Salary': available_players.loc[i, 'salary'],
            'Avg_Fantasy_Points': available_players.loc[i, 'avg_fpts'],
            'Value': available_players.loc[i, 'value']
        }
        for i in available_players.index if add_vars[i].value() == 1
    ]
    
    # Add composite score if available
    if 'composite_score' in current_roster.columns:
        for i, player in enumerate(players_to_drop):
            idx = current_roster[current_roster['Player'] == player['Player']].index[0]
            players_to_drop[i]['Composite_Score'] = current_roster.loc[idx, 'composite_score']
            
            # Add other metrics if available
            if 'Fantasy_Points_Per_Game_15D' in current_roster.columns:
                players_to_drop[i]['Avg_15D'] = current_roster.loc[idx, 'Fantasy_Points_Per_Game_15D']
            if 'Fantasy_Points_Per_Game_7D' in current_roster.columns:
                players_to_drop[i]['Avg_7D'] = current_roster.loc[idx, 'Fantasy_Points_Per_Game_7D']
            if 'consistency_score' in current_roster.columns:
                players_to_drop[i]['Consistency'] = current_roster.loc[idx, 'consistency_score']
            if 'recent_trend_norm' in current_roster.columns:
                players_to_drop[i]['Trend'] = current_roster.loc[idx, 'recent_trend_norm']
    
    if 'composite_score' in available_players.columns:
        for i, player in enumerate(players_to_add):
            idx = available_players[available_players['Player'] == player['Player']].index[0]
            players_to_add[i]['Composite_Score'] = available_players.loc[idx, 'composite_score']
            
            # Add other metrics if available
            if 'Fantasy_Points_Per_Game_15D' in available_players.columns:
                players_to_add[i]['Avg_15D'] = available_players.loc[idx, 'Fantasy_Points_Per_Game_15D']
            if 'Fantasy_Points_Per_Game_7D' in available_players.columns:
                players_to_add[i]['Avg_7D'] = available_players.loc[idx, 'Fantasy_Points_Per_Game_7D']
            if 'consistency_score' in available_players.columns:
                players_to_add[i]['Consistency'] = available_players.loc[idx, 'consistency_score']
            if 'recent_trend_norm' in available_players.columns:
                players_to_add[i]['Trend'] = available_players.loc[idx, 'recent_trend_norm']
    
    print("\nPlayers to drop:")
    for player in players_to_drop:
        output = f"{player['Player']} ({player['Position']}) - Salary: {player['Salary']}, Avg Points: {player['Avg_Fantasy_Points']:.1f}, Value: {player['Value']:.2f}"
        if 'Composite_Score' in player:
            output += f", Composite: {player['Composite_Score']:.1f}"
        if 'Consistency' in player:
            output += f", Consistency: {player['Consistency']:.2f}"
        if 'Trend' in player:
            output += f", Trend: {player['Trend']:.2f}"
        print(output)
    
    print("\nPlayers to add:")
    for player in players_to_add:
        output = f"{player['Player']} ({player['Position']}) - Salary: {player['Salary']}, Avg Points: {player['Avg_Fantasy_Points']:.1f}, Value: {player['Value']:.2f}"
        if 'Composite_Score' in player:
            output += f", Composite: {player['Composite_Score']:.1f}"
        if 'Consistency' in player:
            output += f", Consistency: {player['Consistency']:.2f}"
        if 'Trend' in player:
            output += f", Trend: {player['Trend']:.2f}"
        print(output)

    # Calculate total salary and total average fantasy points before changes
    total_salary_before = current_roster['salary'].sum()
    total_avg_fantasy_points_before = current_roster['avg_fpts'].sum()
    
    print(f"\nTotal Salary before changes: {total_salary_before:.2f}")
    print(f"Total Average Fantasy Points before changes: {total_avg_fantasy_points_before:.2f}")
    
    if 'composite_score' in current_roster.columns:
        total_composite_before = current_roster['composite_score'].sum()
        print(f"Total Composite Score before changes: {total_composite_before:.2f}")

    # Calculate total salary and total average fantasy points after changes
    total_salary_after = (
        total_salary_before - 
        sum(current_roster.loc[i, 'salary'] for i in current_roster.index if drop_vars[i].value() == 1) + 
        sum(available_players.loc[i, 'salary'] for i in available_players.index if add_vars[i].value() == 1)
    )
    
    total_avg_fantasy_points_after = (
        total_avg_fantasy_points_before - 
        sum(current_roster.loc[i, 'avg_fpts'] for i in current_roster.index if drop_vars[i].value() == 1) + 
        sum(available_players.loc[i, 'avg_fpts'] for i in available_players.index if add_vars[i].value() == 1)
    )
    
    print(f"Total Salary after changes: {total_salary_after:.2f}")
    print(f"Total Average Fantasy Points after changes: {total_avg_fantasy_points_after:.2f}")
    
    if 'composite_score' in current_roster.columns and 'composite_score' in available_players.columns:
        total_composite_after = (
            total_composite_before - 
            sum(current_roster.loc[i, 'composite_score'] for i in current_roster.index if drop_vars[i].value() == 1) + 
            sum(available_players.loc[i, 'composite_score'] for i in available_players.index if add_vars[i].value() == 1)
        )
        print(f"Total Composite Score after changes: {total_composite_after:.2f}")

    return players_to_drop, players_to_add

def calculate_composite_score(df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Calculate a composite score based on multiple time periods and consistency metrics.
    
    Args:
        df: DataFrame containing player stats
        weights: Dictionary of weights for different metrics. If None, default weights are used.
            Possible keys: 'avg_30d', 'avg_15d', 'avg_7d', 'consistency', 'recent_trend',
                          'min_games_7d', 'min_games_15d'
    
    Returns:
        DataFrame with added composite_score column
    """
    # Make a copy to avoid modifying the original
    result_df = df.copy()
    
    # Default weights if none provided
    if weights is None:
        weights = {
            'avg_30d': 0.4,    # 30-day average (stability)
            'avg_15d': 0.3,    # 15-day average (medium-term)
            'avg_7d': 0.3,     # 7-day average (recent performance)
            'consistency': 0.5, # How much to penalize inconsistency
            'recent_trend': 0.5, # How much to reward/penalize recent trend
            'min_games_7d': 2,  # Minimum games in last 7 days
            'min_games_15d': 4   # Minimum games in last 15 days
        }
    
    # If min_games parameters aren't in weights, add defaults
    if 'min_games_7d' not in weights:
        weights['min_games_7d'] = 2
    if 'min_games_15d' not in weights:
        weights['min_games_15d'] = 4
        
    # Print the minimum games requirements
    print(f"Minimum games for 7-day stats: {weights['min_games_7d']}")
    print(f"Minimum games for 15-day stats: {weights['min_games_15d']}")
    
    # Convert expected_return to datetime
    result_df['expected_return_dt'] = pd.to_datetime(result_df['expected_return'], errors='coerce')
    
    # CONSISTENCY CALCULATION
    # ----------------------
    # We approximate standard deviation as 50% of average points
    # Higher std_dev = more variance = less consistency
    result_df['std_30d'] = result_df['avg_fpts'] * 0.5  # Approximation if actual std not available
    
    # Calculate consistency score (inverse of standard deviation, normalized)
    # Score ranges from 0 to 1:
    # - 1 = most consistent player (e.g., player who scores ~same points every game)
    # - 0 = least consistent player (e.g., player with extreme game-to-game variance)
    if 'std_30d' in result_df.columns:
        max_std = result_df['std_30d'].max()
        if max_std > 0:
            result_df['consistency_score'] = 1 - (result_df['std_30d'] / max_std)
        else:
            result_df['consistency_score'] = 1.0
    else:
        result_df['consistency_score'] = 1.0  # Default if std not available
    
    # RECENT TREND CALCULATION
    # -----------------------
    # Compare 7-day average to 30-day average to identify improving/declining players
    # Positive value = player is improving, Negative value = player is declining
    if 'Fantasy_Points_Per_Game_7D' in result_df.columns and 'avg_fpts' in result_df.columns:
        # Apply the minimum games filter for 7-day stats
        has_enough_7d_games = result_df['Games_Last_7D'] >= weights['min_games_7d']
        
        # For players with enough recent games, calculate trend
        # For others, set trend to 0 (neutral)
        result_df['recent_trend'] = 0.0
        mask = has_enough_7d_games & (result_df['avg_fpts'] > 0)
        
        if mask.any():
            result_df.loc[mask, 'recent_trend'] = (
                result_df.loc[mask, 'Fantasy_Points_Per_Game_7D'] / 
                result_df.loc[mask, 'avg_fpts'] - 1
            )
        
        # Normalize trend between -1 and 1:
        # - 1 = strongest positive trend (e.g., player who recently became starter)
        # - 0 = no trend (recent performance matches longer-term average)
        # - -1 = strongest negative trend (e.g., player with reduced minutes/role)
        max_trend = max(result_df['recent_trend'].abs().max(), 0.5)  # At least 0.5 to avoid extreme normalization
        result_df['recent_trend_norm'] = result_df['recent_trend'] / max_trend
        
        # Replace any NaNs with 0 (neutral trend)
        result_df['recent_trend_norm'] = result_df['recent_trend_norm'].fillna(0)
    else:
        result_df['recent_trend_norm'] = 0  # Default if trend can't be calculated
    
    # Handle 15-day stats
    if 'Fantasy_Points_Per_Game_15D' in result_df.columns:
        # Apply the minimum games filter for 15-day stats
        has_enough_15d_games = result_df['Games_Last_15D'] >= weights['min_games_15d']
        
        # For players without enough 15-day games, use 30-day average
        result_df['Fantasy_Points_Per_Game_15D_adjusted'] = result_df['avg_fpts']
        
        # For players with enough games, use their actual 15-day average
        mask = has_enough_15d_games
        if mask.any():
            result_df.loc[mask, 'Fantasy_Points_Per_Game_15D_adjusted'] = result_df.loc[mask, 'Fantasy_Points_Per_Game_15D']
    else:
        # If 15-day stats don't exist, use 30-day
        result_df['Fantasy_Points_Per_Game_15D_adjusted'] = result_df['avg_fpts']
    
    # Handle 7-day stats similarly
    if 'Fantasy_Points_Per_Game_7D' in result_df.columns:
        # Apply the minimum games filter for 7-day stats
        has_enough_7d_games = result_df['Games_Last_7D'] >= weights['min_games_7d']
        
        # For players without enough 7-day games, use 30-day average
        result_df['Fantasy_Points_Per_Game_7D_adjusted'] = result_df['avg_fpts']
        
        # For players with enough games, use their actual 7-day average
        mask = has_enough_7d_games
        if mask.any():
            result_df.loc[mask, 'Fantasy_Points_Per_Game_7D_adjusted'] = result_df.loc[mask, 'Fantasy_Points_Per_Game_7D']
    else:
        # If 7-day stats don't exist, use 30-day
        result_df['Fantasy_Points_Per_Game_7D_adjusted'] = result_df['avg_fpts']
    
    # Calculate the composite score
    # The composite score consists of:
    # 1. Weighted average of fantasy points from different time periods (30d, 15d, 7d)
    # 2. Consistency bonus: With default weight of 0.5, adds up to 10% of avg_fpts for perfectly consistent players
    #    (consistency_score ranges from 0-1, multiplied by 0.2 scaling factor and 0.5 weight)
    # 3. Recent trend adjustment: With default weight of 0.5, can add up to 10% of avg_fpts for strongly improving players
    #    or subtract up to 10% for strongly declining players (trend_norm ranges from -1 to 1)
    result_df['composite_score'] = (
        weights['avg_30d'] * result_df['avg_fpts'] +
        weights.get('avg_15d', 0) * result_df['Fantasy_Points_Per_Game_15D_adjusted'] +
        weights.get('avg_7d', 0) * result_df['Fantasy_Points_Per_Game_7D_adjusted'] +
        weights['consistency'] * result_df['consistency_score'] * result_df['avg_fpts'] * 0.2 +  # Scale consistency impact
        weights['recent_trend'] * result_df['recent_trend_norm'] * result_df['avg_fpts'] * 0.2    # Scale trend impact
    )
    
    # Check for and handle any NaN or infinite values
    mask = result_df['composite_score'].isna() | np.isinf(result_df['composite_score'])
    if mask.any():
        print(f"Warning: Found {mask.sum()} players with NaN or infinite composite scores. Using 30-day average instead.")
        result_df.loc[mask, 'composite_score'] = result_df.loc[mask, 'avg_fpts']
    
    # Note on consistency and trend impact:
    # - With default weights (0.5), consistency contributes: 0.5 * consistency_score * avg_fpts * 0.2
    #   Maximum contribution is 0.5 * 1.0 * avg_fpts * 0.2 = 0.1 * avg_fpts (10% bonus)
    # - With default weights (0.5), trend contributes: 0.5 * trend_norm * avg_fpts * 0.2
    #   Maximum contribution ranges from -0.1 * avg_fpts to +0.1 * avg_fpts (-10% to +10%)
    # - These adjustments are modest by design to ensure base performance remains the primary factor
    
    return result_df

def main() -> None:
    """Main function to run the optimization."""
    parser = argparse.ArgumentParser(description="NBA Fantasy Roster Optimization")
    parser.add_argument('--salary-cap', type=float, default=100.0, help='Set the salary cap for the roster (default: 100.0)')
    parser.add_argument('--transactions', type=int, default=2, help='Number of players to add/drop (default: 2)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--exclude', nargs='+', help='List of players to exclude from optimization')
    parser.add_argument('--replace', action='store_true', help='Update current_team.txt with recommended changes after confirmation')
    parser.add_argument('--include-injured', action='store_true', help='Include injured players in optimization')
    
    # Add arguments for composite score weights
    parser.add_argument('--weight-30d', type=float, default=0.4, help='Weight for 30-day average (default: 0.4)')
    parser.add_argument('--weight-15d', type=float, default=0.3, help='Weight for 15-day average (default: 0.3)')
    parser.add_argument('--weight-7d', type=float, default=0.3, help='Weight for 7-day average (default: 0.3)')
    parser.add_argument('--consistency-bonus', type=float, default=0.5, help='Weight for consistency bonus (default: 0.5)')
    parser.add_argument('--trend-weight', type=float, default=0.5, help='Weight for recent trend (default: 0.5)')
    parser.add_argument('--min-games-7d', type=int, default=2, help='Minimum games in last 7 days (default: 2)')
    parser.add_argument('--min-games-15d', type=int, default=4, help='Minimum games in last 15 days (default: 4)')
    parser.add_argument('--no-composite', action='store_true', help='Disable composite score and use only 30-day average')
    
    args = parser.parse_args()
    salary_cap = args.salary_cap
    transactions = args.transactions
    debug_flag = args.debug
    excluded_players = args.exclude if args.exclude else []
    replace = args.replace
    
    # Create weights dictionary from command-line arguments
    weights = None
    if not args.no_composite:
        weights = {
            'avg_30d': args.weight_30d,
            'avg_15d': args.weight_15d,
            'avg_7d': args.weight_7d,
            'consistency': args.consistency_bonus,
            'recent_trend': args.trend_weight,
            'min_games_7d': args.min_games_7d,
            'min_games_15d': args.min_games_15d
        }
        
        # Normalize time period weights to sum to 1.0
        time_period_sum = weights['avg_30d'] + weights['avg_15d'] + weights['avg_7d']
        if time_period_sum != 1.0:
            weights['avg_30d'] /= time_period_sum
            weights['avg_15d'] /= time_period_sum
            weights['avg_7d'] /= time_period_sum
            print(f"\nNormalized time period weights: 30d={weights['avg_30d']:.2f}, " +
                  f"15d={weights['avg_15d']:.2f}, 7d={weights['avg_7d']:.2f}")
    
    if excluded_players:
        print(f"\nExcluding the following players from optimization: {excluded_players}")
    
    current_team_file = 'current_team.txt'
    
    if os.path.exists(current_team_file):
        # Load current roster from file
        current_roster = load_current_team(current_team_file)
        
        # Load available players
        all_players_query = """
        SELECT 
            ps.Player,
            ps.Pos,
            ps.Team,
            nsc.salary,
            psr.Fantasy_Points_Per_Game_30D as avg_fpts,
            psr.Fantasy_Points_Per_Game_15D,
            psr.Fantasy_Points_Per_Game_7D,
            psr.Games_Last_30D,
            psr.Games_Last_15D,
            psr.Games_Last_7D,
            psr.Value_Per_Game_30D as value,
            pi.injury_type,
            pi.expected_return
        FROM player_stats ps
        JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        JOIN player_salary_stats psr ON ps.Player = psr.Player
        LEFT JOIN (
            SELECT pi1.* 
            FROM player_injuries pi1
            INNER JOIN (
                SELECT player_name, MAX(report_date) as max_date
                FROM player_injuries
                GROUP BY player_name
            ) pi2 ON pi1.player_name = pi2.player_name AND pi1.report_date = pi2.max_date
        ) pi ON ps.Player = pi.player_name
        WHERE psr.Games_Last_30D >= 3  -- Minimum games played
        AND nsc.salary > 0
        """
        
        with sqlite3.connect('nba_stats.db') as conn:
            all_players = pd.read_sql(all_players_query, conn)
        
        # Filter out players in the current roster
        available_players = all_players[~all_players['Player'].isin(current_roster['Player'])].copy()
        
        # Create front_court/back_court indicators for available players
        available_players.loc[:, 'is_front_court'] = available_players['Pos'].str.contains('F|C').astype(int)
        available_players.loc[:, 'is_back_court'] = available_players['Pos'].str.contains('G').astype(int)
        
        # Exclude injured players unless --include-injured is specified
        if not args.include_injured:
            today = pd.Timestamp.now().normalize()
            injured_players = available_players[
                available_players['expected_return'].notna() & 
                (pd.to_datetime(available_players['expected_return']) > today + pd.Timedelta(days=2))
            ]['Player'].tolist()
            
            if injured_players:
                print("\nAutomatically excluding the following injured players:")
                for player in injured_players:
                    injury_info = available_players[available_players['Player'] == player].iloc[0]
                    print(f"- {player}: {injury_info['injury_type']}, Expected return: {injury_info['expected_return']}")
                available_players = available_players[~available_players['Player'].isin(injured_players)]
        
        # Call the optimization function
        optimize_team_changes(
            current_roster, 
            available_players, 
            salary_cap=salary_cap, 
            transactions=transactions,
            excluded_players=excluded_players,
            debug_flag=debug_flag,
            replace=replace,
            weights=weights
        )
    else:
        # If no file, run the full optimization
        df = get_player_data()
        optimal_roster = optimize_roster(
            df, 
            salary_cap=salary_cap, 
            debug_flag=debug_flag,
            excluded_players=excluded_players,
            weights=weights
        )
        
        print("\nOptimal Roster:")
        print(optimal_roster.sort_values('Avg_Fantasy_Points', ascending=False))
        
        print(f"\nTotal Salary: {optimal_roster['Salary'].sum():.1f}")
        print(f"Projected Fantasy Points: {optimal_roster['Avg_Fantasy_Points'].sum():.1f}")
        
        if 'Composite_Score' in optimal_roster.columns:
            print(f"Composite Score: {optimal_roster['Composite_Score'].sum():.1f}")
        
        print("\nTeam Distribution:")
        print(optimal_roster['Team'].value_counts())
        
        visualize_roster(optimal_roster)

if __name__ == "__main__":
    main() 