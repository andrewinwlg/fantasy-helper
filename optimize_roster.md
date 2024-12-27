# `optimize_roster.py` Overview

The `optimize_roster.py` script is designed to optimize an NBA fantasy basketball roster in the **nba.com Salary Cap game** using linear programming. It selects players based on their average fantasy points while adhering to specific constraints.

## Key Components

### 1. **Imports**
The script imports necessary libraries:
- **SQLite3**: For database interactions.
- **Pandas**: For data manipulation and analysis.
- **Matplotlib & Seaborn**: For data visualization.
- **Pulp**: For linear programming optimization.

### 2. **Data Class for Constraints**
```python
@dataclass
class RosterConstraints:
    """Container for roster optimization constraints."""
    salary_cap: int = 100
    front_court_req: int = 5
    back_court_req: int = 5
    max_per_team: int = 2
```
- This class encapsulates the constraints for the roster optimization, making it easier to manage and pass around.

### 3. **Data Retrieval**
```python
def get_player_data() -> pd.DataFrame:
    """Get player data with positions and 30-day stats."""
```
- This function retrieves player data from the database, including player names, positions, salaries, and average fantasy points over the last 30 days.

### 4. **Optimization Function**
```python
def optimize_roster(
    df: pd.DataFrame, 
    constraints: RosterConstraints = None
) -> pd.DataFrame:
    """Optimize roster using linear programming."""
```
- This function sets up the linear programming model to maximize total fantasy points while adhering to specific constraints.

### 5. **Adding Constraints**
```python
def add_roster_constraints(
    prob: LpProblem, 
    df: pd.DataFrame, 
    player_vars: Dict, 
    constraints: RosterConstraints
) -> None:
    """Add all constraints to the optimization problem."""
```
- This function adds various constraints to the optimization problem, including salary cap, total players, position requirements, and maximum players per team.

### 6. **Selecting Players**
```python
def get_selected_players(df: pd.DataFrame, player_vars: Dict) -> pd.DataFrame:
    """Get selected players from optimization results."""
```
- This function extracts the selected players from the optimization results and returns them as a DataFrame.

### 7. **Visualization**
```python
def visualize_roster(roster: pd.DataFrame) -> None:
    """Create visualizations for the optimal roster."""
```
- This function generates visualizations to help analyze the selected roster, including salary distribution, projected fantasy points, and team distribution.

### 8. **Main Function**
```python
def main() -> None:
    """Main function to run the optimization."""
```
- The main function orchestrates the data retrieval, optimization, and visualization processes.

## How the Algorithm Works

1. **Data Preparation**: The script fetches player data from the database and prepares it for optimization.
2. **Linear Programming Model**: It sets up a linear programming model to maximize the total average fantasy points while adhering to the defined constraints.
3. **Defining Constraints**: Constraints are added to ensure the roster meets the requirements for salary cap, player positions, and team diversity.
4. **Solving the Problem**: The model is solved using the `pulp` library, which finds the optimal roster configuration.
5. **Result Extraction**: The selected players are extracted and displayed, along with visualizations to analyze the roster.

## Guarantees of Optimality

- The algorithm is guaranteed to return the optimal solution (i.e., the highest total average fantasy points) as long as the problem is well-defined and feasible.
- Linear programming methods used in this script ensure that if a feasible solution exists, the optimal solution will be found efficiently.

## Limitations

- **Feasibility**: If the constraints are too strict, the algorithm may not find a solution.
- **Dynamic Changes**: Player performance can change, so the model may need frequent updates to remain accurate.

## Conclusion

In summary, the algorithm effectively uses linear programming to optimize an NBA fantasy roster under specific constraints, and it is guaranteed to return the highest total average fantasy points as long as the problem is feasible.
