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
        psr.Value_Per_Game_30D,
        psr.Games_Last_30D,
        psr.Fantasy_Points_Per_Game_15D as avg_fpts_15d,
        psr.Fantasy_Points_Per_Game_7D as avg_fpts_7d,
        ps.Pos,
        ps.Team
    FROM player_stats ps
    JOIN player_salary_stats psr ON ps.Player = psr.Player
    WHERE ps.Player IN ({})
    ORDER BY psr.Fantasy_Points_Per_Game_30D DESC
    """.format(','.join('?' * len(players)))

    try:
        with sqlite3.connect('nba_stats.db') as conn:
            df = pd.read_sql_query(query, conn, params=players)
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
        df[[
            'Player_Display', 
            'avg_fpts_30d',
            'Value_Per_Game_30D',
            'avg_fpts_15d', 
            'avg_fpts_7d',
            'Games_Last_30D',
            'Pos',
            'Team'
        ]], 
        headers=[
            'Player',
            'FP/G (30d)',
            'Value (30d)',
            'FP/G (15d)',
            'FP/G (7d)',
            'Games (30d)',
            'Pos',
            'Team'
        ],
        floatfmt=".1f",
        tablefmt="pipe",
        showindex=False
    )
    print(table)
    
    # Print total of all 30D averages
    total_avg_fpts_30d = df['avg_fpts_30d'].sum()
    print(f"\nTotal of all 30D averages: {total_avg_fpts_30d:.1f}")
    
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


def update_team(login_id: str) -> None:
    """
    Update current_team.txt with the latest team roster from the database.
    
    Args:
        login_id: The login ID to fetch the team roster for
    """
    try:
        # Connect to database
        with sqlite3.connect('nba_stats.db') as conn:
            # Get latest team roster for this login_id
            query = """
            SELECT player_name 
            FROM nba_team_players 
            WHERE login_id = ?
            ORDER BY id ASC
            """
            df = pd.read_sql_query(query, conn, params=[login_id])
            
            if df.empty:
                print(f"No players found for login_id: {login_id}")
                return
            
            if len(df) != 10:
                print(f"Error: Expected 10 players, but found {len(df)} for login_id: {login_id}")
                return
                
            # Write to current_team.txt
            with open('current_team.txt', 'w') as f:
                for player in df['player_name']:
                    f.write(f"{player}\n")
            
            print(f"Updated current_team.txt with {len(df)} players")
            
            # Print the updated roster
            print(f"\nCurrent roster for {login_id}:")
            for player in df['player_name']:
                print(f"  - {player}")
                
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except IOError as e:
        print(f"Error writing to file: {e}")


def main() -> None:
    """Parse command line arguments and run requested function."""
    parser = argparse.ArgumentParser(description="NBA Fantasy roster utilities")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--print-team', action='store_true', help='Print current team ordered by 30-day average')
    group.add_argument('--reorder', action='store_true', help='Reorder current_team.txt by 30-day average')
    group.add_argument('--update', help='Update current_team.txt from database for given login_id')
    
    args = parser.parse_args()
    
    if args.update:
        update_team(args.update)
    elif args.print_team or args.reorder:
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