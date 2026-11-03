# Cloud Commitment & Capacity Simulator

An open-source Python tool for optimizing multi-cloud virtual machine (VM) capacity commitments (Reserved Instances and Savings Plans) under demand uncertainty.


This repository provides a simulation and optimization framework to:
* **Minimize Cloud Costs:** Uses linear programming (PuLP) to calculate the optimal mix of reserved and on-demand VMs based on real-world periodic workload traces.
* **Mitigate Forecast Risk:** Evaluates how forecast errors and unexpected demand drops impact cloud bills.
* **Analyze Bottlenecks:** Extracts dual values (shadow prices) to identify strict cloud provider limits and constraints.
* **Time-Shifting & Laddering:** Simulates staggered commitment expirations and off-peak batch workload scheduling.

## Tech Stack
* Python 3.10 / 3.11
* PuLP (CBC Solver)
* Pandas & NumPy
* SciPy (Numerical Optimization)
* Prophet (Time-Series Forecasting)

Follow these steps to set up and run the project on your local machine (Windows / macOS / Linux):

### 1. Clone the Repository
Open your terminal / command prompt and clone this repository:

git clone "repo_url"

cd cloud-commitment-simulator

### 2. Create virtual environment
python3.10 -m venv venv

### 3. Activate on Windows (PowerShell/CMD):
venv\Scripts\activate

### 4. Install the Dependencies
pip install --upgrade pip

pip install numpy pandas scipy matplotlib seaborn pulp prophet malloovia

### 5. explore data
python explore_all_skus.py

python baseline_lpp.py



## Acknowledgements
This project utilizes the **Shaved Ice** compute resource commitment dataset released by Snowflake researchers[cite: 6]. 
- Original Paper: *Shaved Ice: Optimal Compute Resource Commitments for Dynamic Multi-Cloud Workloads* (ICPE '25).
- Dataset Link: [Zenodo / GitHub Repository](https://github.com/Snowflake-Labs/shavedice-dataset)[cite: 6].
