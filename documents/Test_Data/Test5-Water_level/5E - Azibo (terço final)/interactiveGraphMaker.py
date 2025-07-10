import pandas as pd
import plotly.express as px

# Load the already formatted CSV
df = pd.read_csv("water_level_readings.txt.csv")

# Convert 'Datetime' column to datetime object
df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")

# Ensure 'Reservoir Level (m)' is numeric
df["Reservoir Level (m)"] = pd.to_numeric(df["Reservoir Level (m)"], errors="coerce")

# Drop rows with missing values
df = df.dropna(subset=["Datetime", "Reservoir Level (m)"])
df = df[df["Reservoir Level (m)"] <= 603]

# Create interactive Plotly chart
fig = px.line(df,
              x="Datetime",
              y="Reservoir Level (m)",
              title="Interactive Reservoir Level Over Time",
              labels={"Datetime": "Date", "Reservoir Level (m)": "Reservoir Level (m)"},
              template="plotly_white")

# Show the chart
fig.show()

# Optional: save as HTML
fig.write_html("Azibo-last-part.html")
