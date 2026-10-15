"""
data_cleaning.py
-----------------
Reads raw CSVs from data/raw/, validates + cleans them, writes
analytics-ready CSVs to data/processed/, and writes a data-quality
report (data/processed/data_quality_report.csv +.json) summarizing
issues found and fixed.

Run:
    python src/data_cleaning.py
"""

import json
import os

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(SCRIPT_DIR, "..", "data", "raw")
PROCESSED_DIR = os.path.join(SCRIPT_DIR, "..", "data", "processed")


def read_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(RAW_DIR, name))


def clean_sales_transactions(valid_product_ids: set, valid_hcp_ids: set):
    df = read_raw("sales_transactions.csv")
    total_records = len(df)

    report = {"table": "sales_transactions", "total_records": total_records}

    # Duplicates
    dup_mask = df.duplicated(keep="first")
    report["duplicate_records"] = int(dup_mask.sum())
    df = df[~dup_mask].copy()

    # Invalid dates
    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    invalid_date_mask = parsed_dates.isna()
    report["invalid_dates"] = int(invalid_date_mask.sum())
    df = df[~invalid_date_mask].copy()
    df["date"] = parsed_dates[~invalid_date_mask].values

    # Invalid product IDs
    invalid_pid_mask = ~df["product_id"].isin(valid_product_ids)
    report["invalid_product_ids"] = int(invalid_pid_mask.sum())
    df = df[~invalid_pid_mask].copy()

    # Missing HCP mappings
    missing_hcp_mask = df["hcp_id"].isna() | ~df["hcp_id"].isin(valid_hcp_ids)
    report["missing_hcp_mappings"] = int(missing_hcp_mask.sum())
    df_missing_hcp = df[missing_hcp_mask].copy()
    df = df[~missing_hcp_mask].copy()

    # Negative sales / units treated as outlier/invalid transactions
    negative_mask = (df["net_sales"] < 0) | (df["units"] < 0) | (df["gross_sales"] < 0)
    report["negative_value_records"] = int(negative_mask.sum())
    df_negative = df[negative_mask].copy()
    df = df[~negative_mask].copy()

    # Outlier detection on net_sales using IQR
    q1, q3 = df["net_sales"].quantile([0.25, 0.75])
    iqr = q3 - q1
    upper_bound = q3 + 3 * iqr
    outlier_mask = df["net_sales"] > upper_bound
    report["outlier_transactions"] = int(outlier_mask.sum())
    df["is_outlier"] = outlier_mask

    clean_records = len(df)
    report["clean_records"] = clean_records
    report["pct_records_removed"] = round(100 * (total_records - clean_records) / total_records, 3)

    return df, report, df_missing_hcp, df_negative


def clean_prescriptions(valid_product_ids: set, valid_hcp_ids: set):
    df = read_raw("prescriptions.csv")
    total_records = len(df)
    report = {"table": "prescriptions", "total_records": total_records}

    dup_mask = df.duplicated(keep="first")
    report["duplicate_records"] = int(dup_mask.sum())
    df = df[~dup_mask].copy()

    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    invalid_date_mask = parsed_dates.isna()
    report["invalid_dates"] = int(invalid_date_mask.sum())
    df = df[~invalid_date_mask].copy()
    df["date"] = parsed_dates[~invalid_date_mask].values

    invalid_pid_mask = ~df["product_id"].isin(valid_product_ids)
    report["invalid_product_ids"] = int(invalid_pid_mask.sum())
    df = df[~invalid_pid_mask].copy()

    missing_hcp_mask = df["hcp_id"].isna() | ~df["hcp_id"].isin(valid_hcp_ids)
    report["missing_hcp_mappings"] = int(missing_hcp_mask.sum())
    df = df[~missing_hcp_mask].copy()

    negative_mask = (df["total_prescriptions"] < 0) | (df["new_prescriptions"] < 0) | (df["refill_prescriptions"] < 0)
    report["negative_value_records"] = int(negative_mask.sum())
    df = df[~negative_mask].copy()

    clean_records = len(df)
    report["clean_records"] = clean_records
    report["pct_records_removed"] = round(100 * (total_records - clean_records) / total_records, 3)

    return df, report


def passthrough_clean(name: str, date_cols=None):
    """For tables generated clean by construction (market_data,
    patient_access, hcp_engagement, product_master, hcp_master) we still
    run basic validation: duplicates + null checks + date parsing."""
    df = read_raw(name)
    total_records = len(df)
    report = {"table": name, "total_records": total_records}

    dup_mask = df.duplicated(keep="first")
    report["duplicate_records"] = int(dup_mask.sum())
    df = df[~dup_mask].copy()

    if date_cols:
        for col in date_cols:
            parsed = pd.to_datetime(df[col], errors="coerce")
            invalid_mask = parsed.isna()
            report[f"invalid_{col}"] = int(invalid_mask.sum())
            df = df[~invalid_mask].copy()
            df[col] = parsed[~invalid_mask].values

    null_counts = df.isna().sum()
    report["null_cells_total"] = int(null_counts.sum())

    report["clean_records"] = len(df)
    report["pct_records_removed"] = round(100 * (total_records - len(df)) / total_records, 3) if total_records else 0.0
    return df, report


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    products, products_report = passthrough_clean("product_master.csv", date_cols=["launch_date"])
    hcps, hcps_report = passthrough_clean("hcp_master.csv")

    valid_product_ids = set(products["product_id"])
    valid_hcp_ids = set(hcps["hcp_id"])

    sales_clean, sales_report, sales_missing_hcp, sales_negative = clean_sales_transactions(
        valid_product_ids, valid_hcp_ids
    )
    presc_clean, presc_report = clean_prescriptions(valid_product_ids, valid_hcp_ids)
    market_clean, market_report = passthrough_clean("market_data.csv", date_cols=["month"])
    access_clean, access_report = passthrough_clean("patient_access.csv", date_cols=["month"])
    engagement_clean, engagement_report = passthrough_clean("hcp_engagement.csv", date_cols=["date"])

    # Write cleaned / analytics-ready tables
    products.to_csv(os.path.join(PROCESSED_DIR, "product_master.csv"), index=False)
    hcps.to_csv(os.path.join(PROCESSED_DIR, "hcp_master.csv"), index=False)
    sales_clean.to_csv(os.path.join(PROCESSED_DIR, "sales_transactions.csv"), index=False)
    presc_clean.to_csv(os.path.join(PROCESSED_DIR, "prescriptions.csv"), index=False)
    market_clean.to_csv(os.path.join(PROCESSED_DIR, "market_data.csv"), index=False)
    access_clean.to_csv(os.path.join(PROCESSED_DIR, "patient_access.csv"), index=False)
    engagement_clean.to_csv(os.path.join(PROCESSED_DIR, "hcp_engagement.csv"), index=False)

    # Quarantined / rejected records, kept for audit
    if len(sales_missing_hcp):
        sales_missing_hcp.to_csv(os.path.join(PROCESSED_DIR, "_rejected_sales_missing_hcp.csv"), index=False)
    if len(sales_negative):
        sales_negative.to_csv(os.path.join(PROCESSED_DIR, "_rejected_sales_negative_values.csv"), index=False)

    # Data quality report
    all_reports = [
        products_report,
        hcps_report,
        sales_report,
        presc_report,
        market_report,
        access_report,
        engagement_report,
    ]
    dq_df = pd.DataFrame(all_reports)
    dq_df.to_csv(os.path.join(PROCESSED_DIR, "data_quality_report.csv"), index=False)
    with open(os.path.join(PROCESSED_DIR, "data_quality_report.json"), "w") as f:
        json.dump(all_reports, f, indent=2, default=str)

    print("Data cleaning complete.")
    print(dq_df.to_string(index=False))
    print(f"\nProcessed files written to: {os.path.abspath(PROCESSED_DIR)}")


if __name__ == "__main__":
    main()
