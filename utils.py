import argparse
import sqlite3
from typing import List, Tuple

import pandas as pd
from tabulate import tabulate


def print_ordered_roster(players: List[str]) -> None:
    """
    Print a table of players ordered by 30-day fantasy point average.
    Marks players with * if their position has changed from current_team.txt order.
    
    Args:
        players: List of player names to display
    """
    # Store original order
    original_order = {player: idx for idx, player in enumerate(players)}
    
    # Get player stats from database
    query = """
    SELECT 
        ps.Player,
        psr.Fantasy_Points_Per_Game_30D as avg_fpts_30d,
        psr.Games_Last_30D,
        ps.Pos,
        ps.Team
    FROM player_stats ps
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    WHERE ps.Player IN ({})
    ORDER BY psr.Fantasy_Points_Per_Game_30D DESC
    """.format(','.join([f"'{player}'" for player in players]))

    try:
        with sqlite3.connect('nba_stats.db') as conn:
            df = pd.read_sql_query(query, conn)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return

    if len(df) != len(players):
        print("Warning: Some players not found in database")

    # Add marker for players whose order has changed
    df['Player_Display'] = df.apply(
        lambda row: f"{row['Player']} *" 
        if original_order[row['Player']] != df.index.get_loc(row.name) 
        else row['Player'],
        axis=1
    )

    # Print ordered table
    print("\nRoster ordered by 30-day average:")
    print("(* indicates change in order from current_team.txt)")
    table = tabulate(
        df[['Player_Display', 'avg_fpts_30d', 'Games_Last_30D', 'Pos', 'Team']], 
        headers=['Player', 'FP/G (30d)', 'Games (30d)', 'Pos', 'Team'],
        floatfmt=".1f",
        tablefmt="pipe",
        showindex=False
    )
    print(table)
    
    # Return DataFrame without the display column
    df = df.drop('Player_Display', axis=1)
    return df


def reorder_current_team() -> None:
    """
    Reorder current_team.txt by 30-day fantasy point average.
    Also prints a table showing the ordered list with stats.
    """
    # Read current team
    try:
        with open('current_team.txt', 'r') as f:
            players = [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print("Error: current_team.txt not found")
        return

    # Print and get ordered dataframe
    df = print_ordered_roster(players)
    if df is None:
        return

    # Write ordered list back to file
    try:
        with open('current_team.txt', 'w') as f:
            for player in df['Player']:
                f.write(f"{player}\n")
        print("\nUpdated current_team.txt with ordered list")
    except IOError as e:
        print(f"Error writing to file: {e}")


def main() -> None:
    """Parse command line arguments and run requested function."""
    parser = argparse.ArgumentParser(description="NBA Fantasy roster utilities")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--print-team', action='store_true', help='Print current team ordered by 30-day average')
    group.add_argument('--reorder', action='store_true', help='Reorder current_team.txt by 30-day average')
    
    args = parser.parse_args()
    
    if args.print_team or args.reorder:
        try:
            with open('current_team.txt', 'r') as f:
                players = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            print("Error: current_team.txt not found")
            return
            
        if args.print_team:
            print_ordered_roster(players)
        elif args.reorder:
            reorder_current_team()


if __name__ == "__main__":
    main() 