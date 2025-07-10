
import re
import pandas as pd
from pathlib import Path

# Load the log file
log_path = Path("5B.txt")  # Replace with your actual log file name
log_content = log_path.read_text()

# Split the log into blocks
blocks = log_content.split("#################################")

# Extract water level readings with timestamps
entries = []
for block in blocks:
    time_match = re.search(r"Current time: (\d{2}:\d{2}:\d{2})", block)
    water_match = re.search(r"New water level reading - (\d+)\s*cm", block)

    if time_match and water_match:
        timestamp = time_match.group(1)
        water_level = int(water_match.group(1))
        entries.append([timestamp, water_level])

# Create and save the DataFrame
df_water = pd.DataFrame(entries, columns=["timestamp", "water_level_cm"])
df_water.to_csv("water_level_readings.csv", index=False)
