from flask import Flask, render_template
import sqlite3
import pandas as pd

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('nba_stats.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fantasy_averages')
def fantasy_averages():
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM fantasy_averages
        ORDER BY ESPN_Avg_FPTS DESC
        LIMIT 100
    """, conn)
    conn.close()
    return render_template('table.html', 
                         title='Fantasy Averages',
                         table=df.to_html(classes='table table-striped', index=False))

@app.route('/home_away_splits')
def home_away_splits():
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM fantasy_home_away_splits
        ORDER BY (Home_ESPN_FPTS + Away_ESPN_FPTS)/2 DESC
        LIMIT 100
    """, conn)
    conn.close()
    return render_template('table.html', 
                         title='Home/Away Splits',
                         table=df.to_html(classes='table table-striped', index=False))

@app.route('/player_averages')
def player_averages():
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM player_averages
        ORDER BY PPG DESC
        LIMIT 100
    """, conn)
    conn.close()
    return render_template('table.html', 
                         title='Player Averages',
                         table=df.to_html(classes='table table-striped', index=False))

if __name__ == '__main__':
    app.run(debug=True) 