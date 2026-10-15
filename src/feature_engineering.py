"""
feature_engineering.py
------------------------
Builds analytics feature tables from the cleaned data in data/processed/:

1. hcp_features.csv
   RFM-style HCP scoring:
     - recency_days        : days since last engagement/interaction
     - frequency           : count of prescriptions written (transactions)
     - monetary_value      : total net_sales attributable to the HCP
   Then buckets HCPs into segments:
     High Value / High Growth
     High Value / Low Engagement
     Emerging HCP
     Low Activity

2. monthly_kpi_summary.csv
   Net Sales, Units, Prescriptions, Market Share, ASP, MoM/YoY growth
   at the (month, product, region) grain, plus a total rollup.

3. market_share_drivers.csv
   For each (product, month) shows whether market share moved because
   of company sales growth outpacing / lagging total market growth.

Run:
    python src/feature_engineering.py
"""

import os

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(SCRIPT_DIR, "..", "data", "processed")


def load_processed():
    products = pd.read_csv(os.path.join(PROCESSED_DIR, "product_master.csv"))
    hcps = pd.read_csv(os.path.join(PROCESSED_DIR, "hcp_master.csv"))
    sales = pd.read_csv(os.path.join(PROCESSED_DIR, "sales_transactions.csv"), parse_dates=["date"])
    presc = pd.read_csv(os.path.join(PROCESSED_DIR, "prescriptions.csv"), parse_dates=["date"])
    market = pd.read_csv(os.path.join(PROCESSED_DIR, "market_data.csv"), parse_dates=["month"])
    engagement = pd.read_csv(os.path.join(PROCESSED_DIR, "hcp_engagement.csv"), parse_dates=["date"])
    return products, hcps, sales, presc, market, engagement


def build_hcp_features(hcps, sales, presc, engagement):
    as_of = sales["date"].max()

    # Monetary value: total net sales per HCP
    monetary = sales.groupby("hcp_id")["net_sales"].sum().rename("monetary_value")

    # Frequency: total prescriptions written (proxy for prescribing activity)
    frequency = presc.groupby("hcp_id")["total_prescriptions"].sum().rename("frequency")

    # Recency: days since last engagement interaction (fallback: last sales activity)
    last_engagement = engagement.groupby("hcp_id")["date"].max().rename("last_engagement_date")
    last_sales_activity = sales.groupby("hcp_id")["date"].max().rename("last_sales_date")

    feat = hcps.set_index("hcp_id").join([monetary, frequency, last_engagement, last_sales_activity])
    feat["monetary_value"] = feat["monetary_value"].fillna(0.0)
    feat["frequency"] = feat["frequency"].fillna(0).astype(int)

    feat["last_activity_date"] = feat[["last_engagement_date", "last_sales_date"]].max(axis=1)
    feat["recency_days"] = (as_of - feat["last_activity_date"]).dt.days
    feat["recency_days"] = feat["recency_days"].fillna(feat["recency_days"].max())

    # Growth: compare last 6 months net_sales vs prior 6 months
    cutoff_recent = as_of - pd.DateOffset(months=6)
    cutoff_prior = as_of - pd.DateOffset(months=12)
    recent_sales = (
        sales[sales["date"] > cutoff_recent].groupby("hcp_id")["net_sales"].sum().rename("sales_last_6m")
    )
    prior_sales = (
        sales[(sales["date"] > cutoff_prior) & (sales["date"] <= cutoff_recent)]
        .groupby("hcp_id")["net_sales"]
        .sum()
        .rename("sales_prior_6m")
    )
    feat = feat.join([recent_sales, prior_sales])
    feat["sales_last_6m"] = feat["sales_last_6m"].fillna(0.0)
    feat["sales_prior_6m"] = feat["sales_prior_6m"].fillna(0.0)
    feat["growth_pct"] = np.where(
        feat["sales_prior_6m"] > 0,
        100 * (feat["sales_last_6m"] - feat["sales_prior_6m"]) / feat["sales_prior_6m"],
        np.where(feat["sales_last_6m"] > 0, 100.0, 0.0),
    )

    # Score-based quantile buckets (higher score = better)
    feat["monetary_score"] = pd.qcut(feat["monetary_value"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    feat["recency_score"] = pd.qcut(
        (-feat["recency_days"]).rank(method="first"), 4, labels=[1, 2, 3, 4]
    ).astype(int)  # lower recency_days -> higher score
    feat["frequency_score"] = pd.qcut(feat["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)

    high_value = feat["monetary_score"] >= 3
    high_engagement = feat["recency_score"] >= 3
    high_growth = feat["growth_pct"] >= 10
    low_activity = (feat["monetary_score"] <= 2) & (feat["frequency_score"] <= 2) & (feat["recency_score"] <= 2)

    def assign_segment(row):
        if row["low_activity"]:
            return "Low Activity"
        if row["high_value"] and row["high_growth"]:
            return "High Value / High Growth"
        if row["high_value"] and not row["high_engagement"]:
            return "High Value / Low Engagement"
        if not row["high_value"] and row["high_growth"]:
            return "Emerging HCP"
        return "Emerging HCP" if row["frequency_score"] >= 3 else "Low Activity"

    feat["high_value"] = high_value
    feat["high_engagement"] = high_engagement
    feat["high_growth"] = high_growth
    feat["low_activity"] = low_activity
    feat["value_growth_segment"] = feat.apply(assign_segment, axis=1)

    feat = feat.drop(columns=["high_value", "high_engagement", "high_growth", "low_activity"])
    feat = feat.reset_index()
    return feat


def build_monthly_kpi_summary(products, sales, presc, market):
    sales_m = sales.copy()
    sales_m["month"] = sales_m["date"].values.astype("datetime64[M]")
    presc_m = presc.copy()
    presc_m["month"] = presc_m["date"].values.astype("datetime64[M]")

    sales_agg = (
        sales_m.merge(products[["product_id", "brand_name", "therapy_area"]], on="product_id")
        .groupby(["month", "product_id", "brand_name", "therapy_area", "region"], as_index=False)
        .agg(net_sales=("net_sales", "sum"), gross_sales=("gross_sales", "sum"), units=("units", "sum"))
    )
    presc_agg = presc_m.groupby(["month", "product_id"], as_index=False).agg(
        total_prescriptions=("total_prescriptions", "sum"),
        new_prescriptions=("new_prescriptions", "sum"),
    )

    kpi = sales_agg.merge(presc_agg, on=["month", "product_id"], how="left")
    kpi["asp"] = (kpi["net_sales"] / kpi["units"]).round(2)

    kpi = kpi.sort_values(["product_id", "region", "month"])
    kpi["net_sales_prev_month"] = kpi.groupby(["product_id", "region"])["net_sales"].shift(1)
    kpi["mom_growth_pct"] = (
        100 * (kpi["net_sales"] - kpi["net_sales_prev_month"]) / kpi["net_sales_prev_month"]
    ).round(2)

    kpi["net_sales_prev_year"] = kpi.groupby(["product_id", "region"])["net_sales"].shift(12)
    kpi["yoy_growth_pct"] = (
        100 * (kpi["net_sales"] - kpi["net_sales_prev_year"]) / kpi["net_sales_prev_year"]
    ).round(2)

    # attach market share at product-month grain (region-agnostic)
    market_slim = market[["month", "product_id", "market_share", "market_size"]].drop_duplicates()
    kpi = kpi.merge(market_slim, on=["month", "product_id"], how="left")

    return kpi.drop(columns=["net_sales_prev_month", "net_sales_prev_year"])


def build_market_share_drivers(market):
    df = market.sort_values(["product_id", "month"]).copy()
    df["company_sales_growth_pct"] = df.groupby("product_id")["company_sales"].pct_change() * 100
    df["market_growth_pct"] = df.groupby("product_id")["market_size"].pct_change() * 100
    df["share_change_pp"] = df.groupby("product_id")["market_share"].diff() * 100

    def driver_label(row):
        if pd.isna(row["company_sales_growth_pct"]) or pd.isna(row["market_growth_pct"]):
            return "Insufficient history"
        if row["company_sales_growth_pct"] > row["market_growth_pct"]:
            return "Share gain: company growth outpaced market"
        elif row["company_sales_growth_pct"] < row["market_growth_pct"]:
            return "Share loss: market grew faster than company"
        return "Share stable: growth in line with market"

    df["driver_explanation"] = df.apply(driver_label, axis=1)
    return df


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    products, hcps, sales, presc, market, engagement = load_processed()

    print("Building HCP features (RFM-style segmentation)...")
    hcp_features = build_hcp_features(hcps, sales, presc, engagement)
    hcp_features.to_csv(os.path.join(PROCESSED_DIR, "hcp_features.csv"), index=False)
    print(hcp_features["value_growth_segment"].value_counts().to_string())

    print("\nBuilding monthly KPI summary...")
    kpi_summary = build_monthly_kpi_summary(products, sales, presc, market)
    kpi_summary.to_csv(os.path.join(PROCESSED_DIR, "monthly_kpi_summary.csv"), index=False)
    print(f"  rows: {len(kpi_summary):,}")

    print("\nBuilding market share driver analysis...")
    drivers = build_market_share_drivers(market)
    drivers.to_csv(os.path.join(PROCESSED_DIR, "market_share_drivers.csv"), index=False)
    print(f"  rows: {len(drivers):,}")

    print(f"\nFeature tables written to: {os.path.abspath(PROCESSED_DIR)}")


if __name__ == "__main__":
    main()
