import os
import sqlite3
import pandas as pd
from datetime import datetime
from random import randint
import geopandas as gpd
import plotly.express as px # type: ignore
import json
from flask import Flask, render_template, session, request

# --- App Setup ---
app = Flask(__name__)
app.secret_key = 'your-fixed-secret-key'  

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DB_PATH = os.path.join(BASE_DIR, 'test.db')  # Your database file

# --- Database Functions ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """Ensure PageView table exists"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS PageView (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            page TEXT NOT NULL,
            time_spent REAL,
            start_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- Session Handling ---
def get_session_info():
    """Return session_id, start_time, previous_path if session keys exist, else None"""
    if not all(key in session for key in ("id", "start_time", "previous_path")):
        return None
    return session.get("id"), session.get("start_time"), session.get("previous_path")

@app.before_request
def assign_session_id():
    """Assign session ID and initialize session info if not set"""
    if "id" not in session:
        session["id"] = randint(1_000_000, 9_999_999)
        session["start_time"] = datetime.now()
        session["previous_path"] = request.path

# --- Logging ---
def log_page_view(session_id, page, time_spent):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO PageView (session_id, page, time_spent, start_time) VALUES (?, ?, ?, ?)",
            (session_id, page, time_spent, str(datetime.now())),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging page view: {e}")

def log_data():
    """Log session page view with time spent"""
    session_info = get_session_info()
    if not session_info:
        return
    session_id, start_time, previous_path = session_info

    try:
        time_spent = (datetime.now() - start_time).total_seconds()
    except Exception:
        time_spent = 0

    log_page_view(session_id, previous_path, time_spent)

@app.after_request
def track_time(response):
    """Log page views on key routes"""
    path_mapping = {
        "/": "Home",
        "/Access_data": "Access_data",
        "/Introduction": "Introduction",
        "/Contact": "Contact"
    }

    if request.path in path_mapping:
        log_data()
        session["start_time"] = datetime.now()
        session["previous_path"] = path_mapping[request.path]

    return response

#--- map---
def make_continent_choropleth():
    conn = sqlite3.connect('cleaned_data.db')
    df = pd.read_sql_query("SELECT continent, emission_rate, quarter FROM emissions", conn)
    conn.close()
    df['quarter'] = df['quarter'].astype(str)

    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    conts = world.dissolve(by='continent', as_index=False)[['continent','geometry']]

    geo = conts.merge(df, on='continent', how='right')
    geojson = json.loads(geo.to_json())

    fig = px.choropleth(
        df,
        geojson=geojson,
        locations='continent',
        color='emission_rate',
        animation_frame='quarter',
        featureidkey='properties.continent',
        projection='natural earth',
        color_continuous_scale='OrRd',
        labels={'emission_rate':'MtCO₂e'},
        title='Quarterly CO₂ Emissions by Continent'
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0})

    return fig.to_json()

# --- Routes ---
@app.route("/")
def home():
    return render_template("Website.html")

@app.route('/Access_data')
def access_data():
    choropleth_json = make_continent_choropleth()
    return render_template(
        'access_data.html',
        choropleth_json=choropleth_json,
        barchart='barchart.png',
        heatmap='heatmap.png'
    )

@app.route("/Introduction")
def introduction():
    return render_template("Introduction.html")

@app.route("/Contact")
def contact():
    return render_template("contact.html")

# --- Main ---
if __name__ == '__main__':
    initialize_db()
    app.run(debug=True, port=5000)
