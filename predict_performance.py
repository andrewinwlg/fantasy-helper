import sqlite3

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split


def load_player_data():
    """Load and prepare player game log data"""
    with sqlite3.connect('nba_stats.db') as conn:
        query = """
        SELECT 
            player_url,
            Date,
            espn_fpts,
            nba_salary_cap_fpts,
            MP as minutes_played,
            PTS as points,
            TRB as rebounds,
            AST as assists,
            STL as steals,
            BLK as blocks,
            TOV as turnovers
        FROM clean_game_logs
        WHERE espn_fpts IS NOT NULL 
        AND nba_salary_cap_fpts IS NOT NULL
        ORDER BY Date ASC
        """
        df = pd.read_sql(query, conn)
    
    # Convert minutes from 'MM:SS' to float minutes
    def convert_minutes(time_str):
        try:
            minutes, seconds = map(int, time_str.split(':'))
            return minutes + seconds/60
        except:
            return 0
    
    df['minutes_played'] = df['minutes_played'].apply(convert_minutes)
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def prepare_features(df, player_url, lookback_games=5):
    """
    Create features based on rolling averages of past N games
    """
    player_df = df[df['player_url'] == player_url].copy()
    
    # Calculate rolling averages
    for col in ['minutes_played', 'points', 'rebounds', 'assists', 
                'steals', 'blocks', 'turnovers', 
                'espn_fpts', 'nba_salary_cap_fpts']:
        player_df[f'{col}_last_{lookback_games}g_avg'] = (
            player_df[col].rolling(window=lookback_games, min_periods=1).mean()
        )
        player_df[f'{col}_last_{lookback_games}g_std'] = (
            player_df[col].rolling(window=lookback_games, min_periods=1).std()
        )
    
    # Drop rows where we don't have enough history
    player_df = player_df.iloc[lookback_games:]
    
    return player_df

def train_model(df, target='espn_fpts', lookback_games=5):
    """
    Train a model to predict fantasy points
    """
    # Prepare features for all players
    all_prepared_data = []
    for player_url in df['player_url'].unique():
        player_data = prepare_features(df, player_url, lookback_games)
        all_prepared_data.append(player_data)
    
    prepared_df = pd.concat(all_prepared_data)
    
    # Define features
    feature_cols = [col for col in prepared_df.columns 
                   if ('_last_' in col and target not in col)]
    
    # Split into features and target
    X = prepared_df[feature_cols]
    y = prepared_df[target]
    
    # Split into train/test
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Train model
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    
    print(f"\nModel Performance for {target}:")
    print(f"Train R2: {r2_score(y_train, train_pred):.3f}")
    print(f"Test R2: {r2_score(y_test, test_pred):.3f}")
    print(f"Test RMSE: {np.sqrt(mean_squared_error(y_test, test_pred)):.3f}")
    
    return model, feature_cols

def predict_next_game(model, feature_cols, player_history):
    """
    Predict fantasy points for next game
    """
    features = player_history[feature_cols].iloc[-1:]
    return model.predict(features)[0]

def main():
    # Load data
    df = load_player_data()
    
    # Train models for both scoring systems
    espn_model, espn_features = train_model(df, target='espn_fpts')
    nba_model, nba_features = train_model(df, target='nba_salary_cap_fpts')
    
    # Example prediction for a specific player
    player_url = '/players/j/jamesle01.html'  # LeBron James
    player_data = prepare_features(df, player_url)
    
    espn_pred = predict_next_game(espn_model, espn_features, player_data)
    nba_pred = predict_next_game(nba_model, nba_features, player_data)
    
    print(f"\nPredictions for next game:")
    print(f"ESPN Fantasy Points: {espn_pred:.1f}")
    print(f"NBA Salary Cap Fantasy Points: {nba_pred:.1f}")

if __name__ == "__main__":
    main() 