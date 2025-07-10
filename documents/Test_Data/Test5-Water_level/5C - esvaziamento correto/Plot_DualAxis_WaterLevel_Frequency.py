
import pandas as pd
import plotly.graph_objects as go

# Load water level data
df_level = pd.read_csv("water_level_readings.csv")  # columns: timestamp, water_level_cm
df_level["timestamp"] = pd.to_datetime("2025-05-15 " + df_level["timestamp"])
df_level["timestamp"] = df_level["timestamp"].dt.tz_localize(None)

# Load frequency data
df_freq = pd.read_csv("ipi_frequency_log.csv")  # columns: timestamp, frequency
df_freq.columns = df_freq.columns.str.strip().str.lower()
print(df_freq.columns.tolist())  # Debug print to verify columns
df_freq["timestamp"] = pd.to_datetime("2025-05-15 " + df_freq["timestamp"])
df_freq["timestamp"] = df_freq["timestamp"].dt.tz_localize(None)

# Calculate period from frequency (assume frequency is in Hz)
df_freq["frequency"] = 1 / df_freq["ipi frequency (ms)"]

# Merge the two datasets on timestamp (inner join or nearest if needed)
df = pd.merge_asof(
    df_level.sort_values("timestamp"),
    df_freq.sort_values("timestamp"),
    on="timestamp",
    direction="nearest"
)

# Create figure with secondary Y-axis
fig = go.Figure()

# Water level trace (left Y-axis)
fig.add_trace(go.Scatter(
    x=df["timestamp"],
    y=df["water_level_cm"],
    name="Water Level (cm)",
    mode="lines+markers",
    line=dict(color="blue"),
    yaxis="y1"
))

# Sampling period trace (right Y-axis)
fig.add_trace(go.Scatter(
    x=df["timestamp"],
    y=df["frequency"],
    name="Frequency",
    mode="lines+markers",
    line=dict(color="purple"),
    yaxis="y2"
))

# Add threshold lines to water level
thresholds = [
    {"y": 11, "label": "Flood", "color": "red"},
    {"y": 8, "label": "Full", "color": "green"},
    {"y": 7, "label": "Live Storage", "color": "orange"}
]

for t in thresholds:
    fig.add_hline(
        y=t["y"],
        line=dict(color=t["color"], dash="dot"),
        annotation_text=f"<b>{t['label']}</b>",
        annotation_position="top right"
    )

# Update layout with secondary y-axis
fig.update_layout(
    title="Water Level and Sampling Frequency Over Time",
    xaxis=dict(title="Time"),
    yaxis=dict(title="Water Level (cm)", side="left", showgrid=True),
    yaxis2=dict(title="Sampling Frequency (Hz)", overlaying="y", side="right", showgrid=False),
    legend=dict(x=0.9, y=1.1),
    template="plotly_white",
    
)

fig.show()
fig.write_html("water_level_and_frequency.html")