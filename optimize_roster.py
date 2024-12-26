"""NBA Fantasy roster optimization using linear programming."""

import sqlite3
from dataclasses import dataclass
from typing import Dict

import matplotlib.pyplot as plt
import pandas as pd
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
    constraints: RosterConstraints = None
) -> pd.DataFrame:
    """Optimize roster using linear programming."""
    if constraints is None:
        constraints = RosterConstraints()

    prob = LpProblem("NBA_Fantasy_Roster", LpMaximize)
    player_vars = LpVariable.dicts("players", ((i) for i in df.index), 0, 1, 'Binary')
    
    # Objective: Maximize total fantasy points
    prob += lpSum([df.loc[i, 'avg_fpts'] * player_vars[i] for i in df.index])
    
    # Constraints
    prob += lpSum([df.loc[i, 'salary'] * player_vars[i] for i in df.index]) <= constraints.salary_cap
    prob += lpSum([player_vars[i] for i in df.index]) == 10
    prob += lpSum([player_vars[i] * df.loc[i, 'is_front_court'] for i in df.index]) == constraints.front_court_req
    prob += lpSum([player_vars[i] * df.loc[i, 'is_back_court'] for i in df.index]) == constraints.back_court_req
    
    # Max players per team
    for team in df['Team'].unique():
        team_players = df[df['Team'] == team].index
        prob += lpSum([player_vars[i] for i in team_players]) <= constraints.max_per_team

    prob.solve()
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

def main() -> None:
    """Main function to run the optimization."""
    df = get_player_data()
    optimal_roster = optimize_roster(df)
    
    print("\nOptimal Roster:")
    print(optimal_roster.sort_values('Avg_Fantasy_Points', ascending=False))
    
    print(f"\nTotal Salary: {optimal_roster['Salary'].sum():.1f}")
    print(f"Projected Fantasy Points: {optimal_roster['Avg_Fantasy_Points'].sum():.1f}")
    
    print("\nTeam Distribution:")
    print(optimal_roster['Team'].value_counts())
    
    visualize_roster(optimal_roster)

if __name__ == "__main__":
    main() 