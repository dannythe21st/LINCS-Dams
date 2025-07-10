
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load all three datasets
df_freq = pd.read_csv("Teste4B_ipi_frequency.csv")
df_incl = pd.read_csv("Teste4B_inclinometer.csv")
df_wl = pd.read_csv("Teste4B_distance.csv")

# Convert Time columns to datetime
df_freq["Time"] = pd.to_datetime(df_freq["Time"], format="%H:%M:%S")
df_incl["Time"] = pd.to_datetime(df_incl["Time"], format="%H:%M:%S")
df_wl["Time"] = pd.to_datetime(df_wl["Time"], format="%H:%M:%S")

# Define test phase separators
event_times = pd.to_datetime(["14:44:47", "14:46:32", "14:48:25"], format="%H:%M:%S")

# Create subplots
fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                    subplot_titles=("Frequency Over Time", "Inclination (aX and aY)", "Water Level Over Time"),
                    vertical_spacing=0.08)

# Panel 1: Frequency
fig.add_trace(go.Scatter(x=df_freq["Time"], y=df_freq["Frequency"],
                         mode="lines+markers", name="Frequency (s)", line=dict(color="red")),
              row=1, col=1)

# Panel 2: Inclination
fig.add_trace(go.Scatter(x=df_incl["Time"], y=df_incl["aX"],
                         mode="lines+markers", name="aX", line=dict(color="blue")),
              row=2, col=1)
fig.add_trace(go.Scatter(x=df_incl["Time"], y=df_incl["aY"],
                         mode="lines+markers", name="aY", line=dict(color="green")),
              row=2, col=1)

# Panel 3: Water Level
fig.add_trace(go.Scatter(x=df_wl["Time"], y=df_wl["Water Level (%)"],
                         mode="lines+markers", name="Water Level (%)", line=dict(color="orange")),
              row=3, col=1)

# Add vertical lines to all subplots
for t in event_times:
    for i in range(1, 4):
        fig.add_vline(x=t, line=dict(color="black", dash="dash"), row=i, col=1)

# Layout settings
fig.update_layout(height=900, width=1000, title_text="LINCS Dam Test Data Visualization", showlegend=True)
fig.update_xaxes(title_text="Time", row=3, col=1)
fig.update_yaxes(title_text="Frequency (s)", row=1, col=1)
fig.update_yaxes(title_text="Inclination", row=2, col=1)
fig.update_yaxes(title_text="Water Level (%)", row=3, col=1)

# Show plot
fig.show()
