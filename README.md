# Pharma Commercial Performance & Market Insights Platform

An end-to-end synthetic analytics platform for pharmaceutical sales,
prescriptions, healthcare-provider (HCP) activity, market share, patient
access, and forecasting — built to demonstrate commercial analytics,
customer segmentation, market/competitive analysis, forecasting, and
data-quality reporting.

## What this answers

- Which regions, products, and HCP segments are driving performance?
- Where are sales underperforming relative to prescriptions?
- Which factors are associated with market-share changes?
- Which customer (HCP) segments should receive more commercial attention?
- What could next-quarter sales look like under different scenarios?

## Tech stack

```
Python (Pandas / NumPy)
        ↓
Data cleaning + EDA
        ↓
PostgreSQL (dimensional model)
        ↓
SQL analytics
        ↓
Power BI / Tableau (see powerbi/dashboard_guide.md)
        ↓
Forecasting + segmentation (statsmodels)
        ↓
Business recommendations
```

Plus a **Streamlit app** (`app.py`) that renders all 5 modules directly
from the processed CSVs, so the whole platform is explorable without
standing up Postgres or a BI tool.

## Project structure

```
pharma-commercial-analytics/
│
├── data/
│   ├── raw/                  # synthetic source data (generate_data.py output)
│   └── processed/            # cleaned + feature-engineered analytics tables
│
├── src/
│   ├── generate_data.py      # generates all 7 synthetic datasets
│   ├── data_cleaning.py      # validation, cleaning, data-quality report
│   ├── feature_engineering.py# HCP RFM segmentation, KPI summary, share drivers
│   └── forecasting.py        # Holt-Winters forecast + 4 scenarios
│
├── notebooks/
│   ├── 01_eda.ipynb                    # Module 1: Commercial Performance visuals
│   ├── 02_customer_segmentation.ipynb  # Module 2: HCP RFM segmentation
│   └── 03_forecasting.ipynb            # Module 4: Forecast + scenario charts
│
├── sql/
│   ├── 01_schema.sql             # PostgreSQL dimensional model (star schema)
│   ├── 02_load_data.sql          # \copy statements to load processed CSVs
│   └── 03_business_analysis.sql  # Queries for all 5 modules
│
├── powerbi/
│   └── dashboard_guide.md    # How to build the 5-page BI dashboard
│
├── app.py                    # Streamlit dashboard (all 5 modules)
├── requirements.txt
└── README.md
```

## Quickstart

```bash
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# 1. Generate synthetic raw data (data/raw/)
python src/generate_data.py --start 2022-01-01 --end 2024-12-31 --seed 42

# 2. Clean + validate (data/processed/, plus a data quality report)
python src/data_cleaning.py

# 3. Feature engineering: HCP segmentation, KPI summary, share drivers
python src/feature_engineering.py

# 4. Forecast next 6 months + scenarios
python src/forecasting.py --horizon 6

# 5. Explore everything in the dashboard
streamlit run app.py
```

Then open the notebooks in `notebooks/` for the narrative EDA / segmentation
/ forecasting walkthroughs, or load `data/processed/*.csv` into PostgreSQL
using `sql/01_schema.sql` + `sql/02_load_data.sql` and run
`sql/03_business_analysis.sql` for the SQL-first version of every module.

## The 5 modules

1. **Commercial Performance** — Net Sales, Growth %, Units, Rx Volume,
   Market Share, ASP; monthly trend, product/region breakdowns, Pareto
   contribution, MoM/YoY growth.
2. **Customer / HCP Analytics** — RFM-style scoring (Recency = days since
   last engagement, Frequency = prescriptions written, Monetary = net sales
   attributed) bucketed into `High Value / High Growth`,
   `High Value / Low Engagement`, `Emerging HCP`, `Low Activity`.
3. **Market & Competitive Analytics** — company vs. competitor market
   share, share trend by therapy area, and a driver explanation for every
   month/product showing whether share moved because company sales grew
   faster or slower than the overall market.
4. **Forecasting & Scenario Analysis** — Holt-Winters exponential smoothing
   (falls back to a linear trend for short histories) projecting the next
   N months per product, with Base Case / +5% / -5% / High-Demand scenarios.
5. **Data Quality & Reporting** — missing HCP mappings, duplicate records,
   invalid product IDs/dates, negative-value records, and outlier
   transactions are deliberately injected into the raw data and then
   detected + quarantined by `data_cleaning.py`, with a full report at
   `data/processed/data_quality_report.csv`.

## Notes on the synthetic data

- All data is generated (`src/generate_data.py`) — no real patient, HCP, or
  company data is used anywhere in this project.
- A small, controlled set of data-quality issues (duplicates, missing HCP
  IDs, invalid product IDs, malformed dates, negative values) is
  deliberately injected into `sales_transactions.csv` so the Data Quality
  module has real issues to catch, matching the "many student projects
  ignore this" gap called out in the original brief.
- Default run settings produce ~24K sales transactions, ~24K prescription
  records, 350 HCPs, and 15 products across 5 therapy areas over 36 months
  — large enough to be a believable dataset, small enough to run instantly
  on a laptop. Increase `--n-hcps` / date range in `generate_data.py` for a
  bigger dataset.
