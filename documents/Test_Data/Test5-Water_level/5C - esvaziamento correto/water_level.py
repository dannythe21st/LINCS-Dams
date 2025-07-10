
import pandas as pd
import plotly.graph_objects as go

# Load data from CSV
df = pd.read_csv("water_level_readings.csv")  # Ensure your CSV has columns: timestamp, water_level_cm

# Convert timestamps to datetime with a base date
df["timestamp"] = pd.to_datetime("2025-05-15 " + df["timestamp"])

# Create figure
fig = go.Figure()

# Main water level trace
fig.add_trace(go.Scatter(
    x=df["timestamp"],
    y=df["water_level_cm"],
    mode="lines+markers",
    name="Water Level",
    line=dict(color="blue")
))

# Add horizontal threshold lines
thresholds = [
    {"y": 11, "label": "Flood", "color": "red"},
    {"y": 8, "label": "Full", "color": "green"},
    {"y": 7, "label": "Live Storage", "color": "orange"}
]

for t in thresholds:
    fig.add_hline(
        y=t["y"],
        line=dict(color=t["color"], dash="dot"),
        annotation_text=t["label"],
        annotation_position="top right"
    )

# Layout updates
fig.update_layout(
    title="Water Level Over Time",
    xaxis_title="Time",
    yaxis_title="Water Level (cm)",
    template="plotly_white"
)

fig.show()
fig.write_html("water_level.html")
