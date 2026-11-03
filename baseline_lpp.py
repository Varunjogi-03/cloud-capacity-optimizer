import pandas as pd
import pulp
import numpy as np

# 1. Load dataset and pick one series (e.g., Region 2, Instance Type 'A')
df = pd.read_csv('dataset/hourly_normalized.csv.gz')
series_data = df[(df['REGION_NUM'] == 2) & (df['INSTANCE_TYPE'] == 'A')]['NORM_USAGE'].values

# 2. Define the number of hours to consider (1 week = 168 hours)
hours = 168
if len(series_data) >= hours:
    demand = series_data[:hours]
else:
    # If the series is shorter than 168 hours, we can repeat it to fill the week
    demand = np.resize(series_data, hours)

# Prices
C_reserved_hourly = 1.0   # Reserved price per hour
C_ondemand_hourly = 2.1   # On-Demand price per hour (2.1x premium)

# Create LP Problem using PuLP
prob = pulp.LpProblem("Cloud_Reservation_Baseline", pulp.LpMinimize)

# Decision Variables
R = pulp.LpVariable("Reserved_VMs", lowBound=0, cat='Continuous')
D = [pulp.LpVariable(f"OnDemand_Hour_{h}", lowBound=0, cat='Continuous') for h in range(hours)]

# Objective Function: Minimize Total Cost
prob += (R * hours * C_reserved_hourly) + pulp.lpSum([D[h] * C_ondemand_hourly for h in range(hours)])

# Constraints: R + D[h] >= demand[h]
for h in range(hours):
    prob += R + D[h] >= demand[h], f"Demand_Constraint_Hour_{h}"

# Solve using CBC Solver
prob.solve(pulp.PULP_CBC_CMD(msg=False))

print("Optimization Status:", pulp.LpStatus[prob.status])
print(f"Optimal Reserved Capacity (R*): {R.varValue:.2f} VMs")
print(f"Total Weekly Cost for Region 2 (Instance A): ${pulp.value(prob.objective):.2f}")