
import pandas as pd
import plotly.graph_objects as go

# Load inclinometer data
df = pd.read_csv("inclinometer_readings.csv")
df.columns = df.columns.str.strip().str.lower()
df["timestamp"] = pd.to_datetime("2025-05-15 " + df["timestamp"])
df["timestamp"] = df["timestamp"].dt.tz_localize(None)

# Calculate elapsed time from start
start_time = df["timestamp"].min()
df["elapsed"] = df["timestamp"] - start_time
df["elapsed_str"] = df["elapsed"].dt.components.minutes.astype(str).str.zfill(2) + ":" + df["elapsed"].dt.components.seconds.astype(str).str.zfill(2)

# Create figure
fig = go.Figure()

# Scatter plot for aX
fig.add_trace(go.Scatter(
    x=df["elapsed_str"], y=df["ax"],
    mode="markers", name="aX",
    marker=dict(color="darkgreen", size=6)
))

# Scatter plot for aY
fig.add_trace(go.Scatter(
    x=df["elapsed_str"], y=df["ay"],
    mode="markers", name="aY",
    marker=dict(color="darkorange", size=6)
))

# Layout
fig.update_layout(
    title="Inclinometer Dispersion Plot - aX and aY Over Time",
    xaxis_title="Elapsed Time (MM:SS)",
    yaxis_title="Inclination (aX / aY)",
    template="plotly_white",
    legend=dict(
        y=1.05,
        yanchor="bottom",
        x=1.01,
        xanchor="left"
    )
)

fig.show()
fig.write_html("inclinometer_dispersion_plot.html")
