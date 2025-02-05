"""NBA Fantasy performance prediction using machine learning."""

import numpy as np
import pandas as pd
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
except ImportError:
    print("Warning: scikit-learn not installed. Install with: pip install scikit-learn")


class NBAFantasyPredictor:
    """Predicts NBA fantasy performance using historical data."""
    
    def __init__(self):
        """Initialize the predictor with model and scaler."""
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        
    def prepare_features(self, player_data, schedule_data, team_stats):
        """
        Create features from player data, schedule, and team statistics.
        
        Args:
            player_data: DataFrame with columns [player_id, date, fantasy_points, minutes_played, team]
            schedule_data: DataFrame with columns [date, home_team, away_team]
            team_stats: DataFrame with columns [team, defensive_rating, pace]
            
        Returns:
            DataFrame of prepared features
        """
        features = pd.DataFrame()
        
        # Rolling averages for different time windows
        windows = [7, 15, 30, 60]
        for window_size in windows:
            # Capture window_size in closure
            def rolling_mean(x, size=window_size):
                return x.rolling(size, min_periods=3).mean()
                
            # Fantasy points
            features[f'avg_fp_{window_size}d'] = player_data.groupby('player_id')['fantasy_points'].transform(rolling_mean)
            
            # Minutes played
            features[f'avg_minutes_{window_size}d'] = player_data.groupby('player_id')['minutes_played'].transform(rolling_mean)
        
        # Volatility metrics
        features['fp_std_30d'] = player_data.groupby('player_id')['fantasy_points'].transform(
            lambda x: x.rolling(30, min_periods=3).std()
        )
        
        # Recent trend (short-term vs medium-term performance)
        features['recent_trend'] = features['avg_fp_7d'] - features['avg_fp_30d']
        
        # Rest days
        features['days_since_last_game'] = player_data.groupby('player_id')['date'].transform(
            lambda x: x.diff().dt.days
        )
        
        # Games in last 7 days (fatigue indicator)
        features['games_last_7d'] = player_data.groupby('player_id').apply(
            lambda x: x['date'].rolling('7D').count()
        ).reset_index(level=0, drop=True)
        
        # Opponent strength features
        def get_opponent(row, schedule_data):
            """Get opponent team for a given game."""
            game_schedule = schedule_data[schedule_data['date'] == row['date']]
            if row['team'] in game_schedule['home_team'].values:
                return game_schedule[game_schedule['home_team'] == row['team']]['away_team'].iloc[0]
            return game_schedule[game_schedule['away_team'] == row['team']]['home_team'].iloc[0]
        
        player_data['opponent'] = player_data.apply(lambda x: get_opponent(x, schedule_data), axis=1)
        
        # Merge opponent defensive rating and pace
        features = features.join(
            player_data[['opponent']].merge(
                team_stats[['team', 'defensive_rating', 'pace']], 
                left_on='opponent', 
                right_on='team'
            )[['defensive_rating', 'pace']]
        )
        
        # Home/Away game
        features['is_home'] = player_data.apply(
            lambda x: x['team'] in schedule_data[schedule_data['date'] == x['date']]['home_team'].values,
            axis=1
        )
        
        # Back-to-back game indicator
        features['is_back_to_back'] = features['days_since_last_game'] == 1
        
        # Day of week (some players might perform differently on different days)
        features['day_of_week'] = player_data['date'].dt.dayofweek
        
        # Games until next rest day
        def games_until_rest(date_series):
            """Calculate number of games until next rest day."""
            return date_series.shift(-1).sub(date_series).dt.days.map(lambda x: 0 if x > 1 else 1)
        
        features['games_until_rest'] = player_data.groupby('player_id')['date'].transform(games_until_rest)
        
        return features
        
    def train(self, features, targets):
        """
        Train the model with prepared features.
        
        Args:
            features: DataFrame of prepared features
            targets: Series of target values (fantasy points)
            
        Returns:
            dict with model performance metrics
        """
        # Split the data
        X_train, X_test, y_train, y_test = train_test_split(
            features, targets, test_size=0.2, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        self.model.fit(X_train_scaled, y_train)
        
        # Return test set performance
        test_predictions = self.model.predict(X_test_scaled)
        mse = np.mean((test_predictions - y_test) ** 2)
        rmse = np.sqrt(mse)
        r2 = self.model.score(X_test_scaled, y_test)
        
        return {
            'rmse': rmse,
            'r2': r2,
            'feature_importance': dict(zip(features.columns, self.model.feature_importances_))
        }
    
    def predict(self, features):
        """
        Make predictions for new data.
        
        Args:
            features: DataFrame of prepared features
            
        Returns:
            array of predicted fantasy points
        """
        features_scaled = self.scaler.transform(features)
        return self.model.predict(features_scaled)


def main():
    # Load your data (example structure)
    player_data = pd.DataFrame({
        'player_id': [...],
        'date': [...],
        'fantasy_points': [...],
        'minutes_played': [...],
        'team': [...]
    })
    
    schedule_data = pd.DataFrame({
        'date': [...],
        'home_team': [...],
        'away_team': [...]
    })
    
    team_stats = pd.DataFrame({
        'team': [...],
        'defensive_rating': [...],
        'pace': [...]
    })
    
    # Initialize predictor
    predictor = NBAFantasyPredictor()
    
    # Prepare features
    features = predictor.prepare_features(player_data, schedule_data, team_stats)
    
    # Define target (next game's fantasy points)
    targets = player_data['fantasy_points'].shift(-1)
    
    # Train model and get performance metrics
    performance = predictor.train(features, targets)
    print("Model Performance:", performance)
    
    # Make predictions for upcoming games
    upcoming_features = predictor.prepare_features(new_player_data, new_schedule_data, team_stats)
    predictions = predictor.predict(upcoming_features)

if __name__ == "__main__":
    main()