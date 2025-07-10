import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load water level data
df_level = pd.read_csv("water_level_readings.csv")
df_level.columns = df_level.columns.str.strip().str.lower()
df_level["timestamp"] = pd.to_datetime("2025-05-15 " + df_level["timestamp"])
df_level["timestamp"] = df_level["timestamp"].dt.tz_localize(None)

# Load frequency data
df_freq = pd.read_csv("ipi_frequency_log.csv")
df_freq.columns = df_freq.columns.str.strip().str.lower()
df_freq["timestamp"] = pd.to_datetime("2025-05-15 " + df_freq["timestamp"])
df_freq["timestamp"] = df_freq["timestamp"].dt.tz_localize(None)

# Compute period = 1 / frequency
df_freq["period"] = 1 / df_freq["ipi frequency (ms)"]

# Compute elapsed time and format as MM:SS string
start_time = min(df_level["timestamp"].min(), df_freq["timestamp"].min())
df_level["elapsed"] = df_level["timestamp"] - start_time
df_freq["elapsed"] = df_freq["timestamp"] - start_time

# Format elapsed as MM:SS
df_level["elapsed_str"] = df_level["elapsed"].dt.components.minutes.astype(str).str.zfill(2) + ":" + df_level["elapsed"].dt.components.seconds.astype(str).str.zfill(2)
df_freq["elapsed_str"] = df_freq["elapsed"].dt.components.minutes.astype(str).str.zfill(2) + ":" + df_freq["elapsed"].dt.components.seconds.astype(str).str.zfill(2)

# Merge on nearest timestamp
df = pd.merge_asof(
    df_level.sort_values("timestamp"),
    df_freq.sort_values("timestamp"),
    on="timestamp",
    direction="nearest"
)

# Compute elapsed_str from merged timestamp
df["elapsed"] = df["timestamp"] - start_time
df["elapsed_str"] = df["elapsed"].dt.components.minutes.astype(str).str.zfill(2) + ":" + df["elapsed"].dt.components.seconds.astype(str).str.zfill(2)

# Create subplots with 2 panels
fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    subplot_titles=("Sampling Frequency (Hz)", "Water Level (cm)"),
    vertical_spacing=0.08
)

# Panel 1: Sampling period
fig.add_trace(go.Scatter(
    y=df["period"],
    mode="lines+markers", name="Sampling Frequency (Hz)",
    line=dict(color="purple")
), row=1, col=1)

# Panel 2: Water level
fig.add_trace(go.Scatter(
    x=df["elapsed_str"], y=df["water level"],
    mode="lines+markers", name="Water Level (cm)",
    line=dict(color="blue")
), row=2, col=1)

# Add threshold lines to both panels
thresholds_water = [
    {"y": 11, "label": "Flood"},
    {"y": 8,  "label": "Full"},
    {"y": 7,  "label": "Live Storage"}
]

thresholds_freq = [
    {"y": 1.0, "label": "Flood"},
    {"y": 0.2, "label": "Full"},
    {"y": 0.1, "label": "Live Storage"}
]

for t in thresholds_freq:
    fig.add_hline(
        annotation = dict(
            x=1.01, xref="paper", xanchor="left"
        ),
        y=t["y"],
        line=dict(dash="dot"),
        annotation_text=f"<b>{t['label']}</b>",
        annotation_position="top right",
        row=1, col=1
    )

for t in thresholds_water:
    fig.add_hline(
        annotation = dict(
            x=1.01, xref="paper", xanchor="left"
        ),
        y=t["y"],
        line=dict(dash="dot"),
        annotation_text=f"<b>{t['label']}</b>",
        annotation_position="top right",
        row=2, col=1
    )


fig.update_layout(
    height=700, width=1000,
    title="LINCS Dam Filling Test - Water Level and Sampling Frequency Graphs",
    showlegend=True,
    template="plotly_white",
    legend=dict(
        y=1.05,
        yanchor="bottom",
        x=1.01,
        xanchor="left"
    )
)

# Add x-axis titles
fig.update_xaxes(
    title_text="Time Elapsed",
    tickangle=45,
    row=2, col=1
)

# Y-axis titles
fig.update_yaxes(title_text="Sampling Frequency (Hz)", row=1, col=1)
fig.update_yaxes(title_text="Water Level (cm)", row=2, col=1)

# Show and export
fig.show()
fig.write_html("water_level_and_frequency_mmss.html")
