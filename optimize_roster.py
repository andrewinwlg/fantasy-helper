"""NBA Fantasy roster optimization using linear programming."""

import argparse
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict

import matplotlib.pyplot as plt
import pandas as pd
import pulp
import seaborn as sns
from pulp import LpMaximize, LpProblem, LpVariable, lpSum


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
        psr.Games_Last_30D,
        psr.Value_Per_Game_30D as value
    FROM player_stats ps
    JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    WHERE psr.Games_Last_30D >= 3  -- Minimum games played
    AND nsc.salary > 0
    """
    
    with sqlite3.connect('nba_stats.db') as conn:
        df = pd.read_sql(query, conn)
    
    # Create front_court/back_court indicators
    df['is_front_court'] = df['Pos'].str.contains('F|C')
    df['is_back_court'] = df['Pos'].str.contains('G')
    
    return df

def optimize_roster(
    df: pd.DataFrame, 
    salary_cap: float = 100.0,
    constraints: RosterConstraints = RosterConstraints(),
    excluded_players: list = None,
    debug_flag: bool = False
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
    
    prob = LpProblem("NBA_Fantasy_Roster", LpMaximize)
    player_vars = LpVariable.dicts("players", ((i) for i in df.index), 0, 1, 'Binary')
    
    # Objective: Maximize total fantasy points
    prob += lpSum([df.loc[i, 'avg_fpts'] * player_vars[i] for i in df.index])
    
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
    
    return get_selected_players(df, player_vars)

def get_selected_players(df: pd.DataFrame, player_vars: Dict) -> pd.DataFrame:
    """Get selected players from optimization results."""
    selected_players = []
    for i in df.index:
        if player_vars[i].value() == 1:
            selected_players.append({
                'Player': df.loc[i, 'Player'],
                'Position': df.loc[i, 'Pos'],
                'Team': df.loc[i, 'Team'],
                'Salary': df.loc[i, 'salary'],
                'Avg_Fantasy_Points': df.loc[i, 'avg_fpts'],
                'Value': df.loc[i, 'value']
            })
    
    return pd.DataFrame(selected_players)

def visualize_roster(roster: pd.DataFrame) -> None:
    """Create visualizations for the optimal roster."""
    sns.set(style='whitegrid')
    
    # Create figure with subplots
    fig = plt.figure(figsize=(15, 10))
    
    # 1. Salary distribution
    plt.subplot(2, 2, 1)
    sns.barplot(data=roster, x='Position', y='Salary')
    plt.title('Salary Distribution by Position')
    plt.xticks(rotation=45)
    
    # 2. Fantasy points by player
    plt.subplot(2, 2, 2)
    sns.barplot(data=roster.sort_values('Avg_Fantasy_Points', ascending=False), 
                x='Player', y='Avg_Fantasy_Points')
    plt.title('Projected Fantasy Points by Player')
    plt.xticks(rotation=45)
    
    # 3. Team distribution
    plt.subplot(2, 2, 3)
    team_counts = roster['Team'].value_counts()
    sns.barplot(x=team_counts.index, y=team_counts.values)
    plt.title('Players per Team')
    plt.xticks(rotation=45)
    
    # 4. Value (points per salary dollar)
    plt.subplot(2, 2, 4)
    sns.scatterplot(data=roster, x='Salary', y='Avg_Fantasy_Points')
    plt.title('Fantasy Points vs Salary')
    for i, row in roster.iterrows():
        plt.annotate(row['Player'], (row['Salary'], row['Avg_Fantasy_Points']))
    
    plt.tight_layout()
    plt.show()

def optimize_team_changes(
    current_roster: pd.DataFrame, 
    available_players: pd.DataFrame, 
    salary_cap: float = 100.0, 
    transactions: int = 2,
    excluded_players: list = None,
    debug_flag: bool = False
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
    
    # Create the model
    prob = LpProblem("NBA_Team_Changes", LpMaximize)
    
    # Create binary variables for current players (to drop)
    drop_vars = LpVariable.dicts("drop", ((i) for i in current_roster.index), 0, 1, 'Binary')
    
    # Create binary variables for available players (to add)
    add_vars = LpVariable.dicts("add", ((i) for i in available_players.index), 0, 1, 'Binary')
    
    # Objective: Maximize total fantasy points after changes
    prob += lpSum([available_players.loc[i, 'avg_fpts'] * add_vars[i] for i in available_players.index]) - \
            lpSum([current_roster.loc[i, 'avg_fpts'] * drop_vars[i] for i in current_roster.index])
    
    # Define players that cannot be dropped
    protected_players = ['Nikola Jokic']  # Add the names of players you want to protect
    
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
    print_optimization_results(current_roster, available_players, drop_vars, add_vars)

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
        psr.Games_Last_30D,
        psr.Value_Per_Game_30D as value
    FROM player_stats ps
    JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    WHERE ps.Player IN ({', '.join(['"' + player + '"' for player in players])})
    """
    
    with sqlite3.connect('nba_stats.db') as conn:
        current_roster = pd.read_sql(query, conn)
    
    # Check if exactly 10 players were found
    if len(current_roster) != 10:
        raise ValueError(f"Expected 10 players, but found {len(current_roster)}. Please check the current_team.txt file.")
    
    # Create front_court/back_court indicators for current roster
    current_roster['is_front_court'] = current_roster['Pos'].str.contains('F|C')
    current_roster['is_back_court'] = current_roster['Pos'].str.contains('G')
    
    return current_roster

def print_optimization_results(current_roster: pd.DataFrame, available_players: pd.DataFrame, drop_vars: Dict, add_vars: Dict) -> None:
    """Print the results of the optimization."""
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
    
    print("\nPlayers to drop:")
    for player in players_to_drop:
        print(f"{player['Player']} ({player['Position']}) - Salary: {player['Salary']}, Avg Points: {player['Avg_Fantasy_Points']:.1f}, Value: {player['Value']:.2f}")
    
    print("\nPlayers to add:")
    for player in players_to_add:
        print(f"{player['Player']} ({player['Position']}) - Salary: {player['Salary']}, Avg Points: {player['Avg_Fantasy_Points']:.1f}, Value: {player['Value']:.2f}")

    # Calculate total salary and total average fantasy points before changes
    total_salary_before = current_roster['salary'].sum()
    total_avg_fantasy_points_before = current_roster['avg_fpts'].sum()
    
    print(f"\nTotal Salary before changes: {total_salary_before:.2f}")
    print(f"Total Average Fantasy Points before changes: {total_avg_fantasy_points_before:.2f}")

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

def main() -> None:
    """Main function to run the optimization."""
    parser = argparse.ArgumentParser(description="NBA Fantasy Roster Optimization")
    parser.add_argument('--salary-cap', type=float, default=100.0, help='Set the salary cap for the roster (default: 100.0)')
    parser.add_argument('--transactions', type=int, default=2, help='Number of players to add/drop (default: 2)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--exclude', nargs='+', help='List of players to exclude from optimization')
    
    args = parser.parse_args()
    salary_cap = args.salary_cap
    transactions = args.transactions
    debug_flag = args.debug
    excluded_players = args.exclude if args.exclude else []
    
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
            psr.Games_Last_30D,
            psr.Value_Per_Game_30D as value
        FROM player_stats ps
        JOIN nba_salary_cap_players nsc ON ps.Player = nsc.name
        JOIN player_salary_stats psr ON ps.Player = psr.Player
        """
        
        with sqlite3.connect('nba_stats.db') as conn:
            all_players = pd.read_sql(all_players_query, conn)
        
        # Filter out players in the current roster
        available_players = all_players[~all_players['Player'].isin(current_roster['Player'])].copy()
        
        # Create front_court/back_court indicators for available players
        available_players.loc[:, 'is_front_court'] = available_players['Pos'].str.contains('F|C').astype(int)
        available_players.loc[:, 'is_back_court'] = available_players['Pos'].str.contains('G').astype(int)
        
        # Call the optimization function
        optimize_team_changes(
            current_roster, 
            available_players, 
            salary_cap=salary_cap, 
            transactions=transactions,
            excluded_players=excluded_players,
            debug_flag=debug_flag
        )
    else:
        # If no file, run the full optimization
        df = get_player_data()
        optimal_roster = optimize_roster(
            df, 
            salary_cap=salary_cap, 
            debug_flag=debug_flag,
            excluded_players=excluded_players
        )
        
        print("\nOptimal Roster:")
        print(optimal_roster.sort_values('Avg_Fantasy_Points', ascending=False))
        
        print(f"\nTotal Salary: {optimal_roster['Salary'].sum():.1f}")
        print(f"Projected Fantasy Points: {optimal_roster['Avg_Fantasy_Points'].sum():.1f}")
        
        print("\nTeam Distribution:")
        print(optimal_roster['Team'].value_counts())
        
        visualize_roster(optimal_roster)

if __name__ == "__main__":
    main() 