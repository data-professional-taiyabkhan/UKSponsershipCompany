"""
Flask application for visualizing geocoded organizational data on a map.
"""

from flask import Flask, render_template
import pandas as pd

app = Flask(__name__)

# Load the dataset
df = pd.read_csv("cleaned_geocoded_data.csv")

# Home Page Route
@app.route('/')
def home():
    """Home Template with a brief description of the project."""
    return render_template('home.html')

# Map Page Route
@app.route('/map')
def index():
    """
    Renders the map with markers from the dataset.
    """
    # Prepare markers as a list of dictionaries
    markers = [
        {
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "popup": f'{row["Organisation Name"]}, {row["Town/City"]}'
        }
        for _, row in df.iterrows()
    ]
    return render_template("map.html", markers=markers)


if __name__ == "__main__":
    app.run(debug=True)
