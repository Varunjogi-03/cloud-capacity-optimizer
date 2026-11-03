import os
import pandas as pd
import matplotlib.pyplot as plt

# 1. Dataset load karein
data_path = 'dataset/hourly_normalized.csv.gz'
print(f"Loading dataset from: {data_path}...")
df = pd.read_csv(data_path)

# 2. Basic Dataset Description & Info
print("\n" + "="*50)
print("              DATASET BASIC DESCRIPTION")
print("="*50)
print(f"Total Rows: {df.shape[0]}")
print(f"Total Columns: {df.shape[1]}\n")

print("--- Data Info ---")
df.info()

print("\n--- Numerical Summary (Describe) ---")
print(df.describe())

print("\n--- Unique Values Count ---")
print(f"Unique Regions: {df['REGION_NUM'].unique()}")
print(f"Unique Instance Types (SKUs): {df['INSTANCE_TYPE'].unique()}")

# 3. Output Folder Creation for Plots
output_folder = 'sku_region_plots'
os.makedirs(output_folder, exist_ok=True)
print(f"\nPlots will be saved in: '{output_folder}/' folder.\n")

# 4. Datetime Formatting
df['USAGE_HOUR'] = pd.to_datetime(df['USAGE_HOUR'], errors='coerce')
df = df.sort_values('USAGE_HOUR')

# 5. plot for each unique Region-SKU combination
grouped = df.groupby(['REGION_NUM', 'INSTANCE_TYPE'])

total_groups = len(grouped)
print(f"Generating plots for {total_groups} unique Region-SKU combinations...")

count = 0
for (region, sku), group_df in grouped:
    count += 1
    
    # Clean plot creation
    plt.figure(figsize=(12, 5))
    
    # Sample window plot (First 2 weeks / 336 hours per group)
    sample_data = group_df.iloc[:336]
    
    plt.plot(sample_data['USAGE_HOUR'], sample_data['NORM_USAGE'], color='tab:blue', linewidth=1.5)
    plt.title(f'Normalized Demand Trace - Region {region} | SKU: {sku}', fontsize=12, fontweight='bold')
    plt.xlabel('Usage Hour', fontsize=10)
    plt.ylabel('Normalized Usage (NORM_USAGE)', fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    
    # Save file with distinct name
    file_name = f"plot_region_{region}_sku_{sku}.png"
    save_path = os.path.join(output_folder, file_name)
    plt.savefig(save_path, dpi=150)
    plt.close() # Memory cleanup
    
    print(f"[{count}/{total_groups}] Saved: {save_path}")

print("\n" + "="*50)
print(f"Success! All {total_groups} plots saved in '{output_folder}/'")
print("="*50)