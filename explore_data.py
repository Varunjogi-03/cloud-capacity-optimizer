import pandas as pd
import matplotlib.pyplot as plt

# 1. Load the compressed CSV dataset
print("Loading dataset...")
df = pd.read_csv('dataset/hourly_normalized.csv.gz')

print("--- Dataset Info ---")
print(df.info())
print("\n--- First 5 Rows ---")
print(df.head())

# 2. Filter data for a specific Region and Instance Type (e.g., Region 2, Instance Type 'A')
# Taaki hum ek clear time-series line plot bana sakein
filtered_df = df[(df['REGION_NUM'] == 2) & (df['INSTANCE_TYPE'] == 'A')].copy()

# USAGE_HOUR ko datetime me convert karna (agar format support kare)
filtered_df['USAGE_HOUR'] = pd.to_datetime(filtered_df['USAGE_HOUR'], errors='coerce')
filtered_df = filtered_df.sort_values('USAGE_HOUR')

# First 2 weeks subset (336 hours)
subset = filtered_df.iloc[:336]

# 3. Plotting
plt.figure(figsize=(12, 5))
plt.plot(subset['USAGE_HOUR'], subset['NORM_USAGE'], label='Region 2 - Instance A Demand', color='b')
plt.title('Sample 2-Hourly VM Normalized Usage (Shaved Ice Dataset)')
plt.xlabel('Usage Hour / Timestamp')
plt.ylabel('Normalized Usage (NORM_USAGE)')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig('demand_sample.png')
plt.show()

print("\nPlot saved as demand_sample.png successfully!")