"""
generate_data.py
-----------------
Generates a synthetic, internally-consistent set of datasets for the
Pharma Commercial Performance & Market Insights Platform.

Outputs (written to data/raw/):
    product_master.csv
    hcp_master.csv
    sales_transactions.csv
    prescriptions.csv
    market_data.csv
    patient_access.csv
    hcp_engagement.csv

Run:
    python src/generate_data.py --start 2022-01-01 --end 2024-12-31 --seed 42
"""

import argparse
import os
from datetime import datetime

import numpy as np
import pandas as pd

RNG_SEED_DEFAULT = 42

THERAPY_AREAS = ["Oncology", "Cardiology", "Diabetes", "Respiratory", "Neurology"]

REGIONS = ["North", "South", "East", "West", "Central"]

STATES_BY_REGION = {
    "North": ["Delhi", "Punjab", "Haryana"],
    "South": ["Karnataka", "Tamil Nadu", "Kerala"],
    "East": ["West Bengal", "Odisha", "Bihar"],
    "West": ["Maharashtra", "Gujarat", "Rajasthan"],
    "Central": ["Madhya Pradesh", "Chhattisgarh", "Uttar Pradesh"],
}

CITIES_BY_STATE = {
    "Delhi": ["New Delhi"],
    "Punjab": ["Ludhiana", "Amritsar"],
    "Haryana": ["Gurugram", "Faridabad"],
    "Karnataka": ["Bengaluru", "Mysuru"],
    "Tamil Nadu": ["Chennai", "Coimbatore"],
    "Kerala": ["Kochi", "Thiruvananthapuram"],
    "West Bengal": ["Kolkata", "Howrah"],
    "Odisha": ["Bhubaneswar", "Cuttack"],
    "Bihar": ["Patna", "Gaya"],
    "Maharashtra": ["Mumbai", "Pune"],
    "Gujarat": ["Ahmedabad", "Surat"],
    "Rajasthan": ["Jaipur", "Jodhpur"],
    "Madhya Pradesh": ["Bhopal", "Indore"],
    "Chhattisgarh": ["Raipur", "Bilaspur"],
    "Uttar Pradesh": ["Lucknow", "Kanpur"],
}

SPECIALTIES_BY_THERAPY = {
    "Oncology": ["Oncologist", "Hematologist"],
    "Cardiology": ["Cardiologist", "General Physician"],
    "Diabetes": ["Endocrinologist", "General Physician"],
    "Respiratory": ["Pulmonologist", "General Physician"],
    "Neurology": ["Neurologist", "General Physician"],
}

HOSPITAL_TYPES = ["Government", "Private", "Trust/NGO", "Corporate Chain"]

HCP_SEGMENTS = ["High potential", "Medium potential", "Low potential"]

INTERACTION_TYPES = ["Field Visit", "Email", "Webinar", "Conference", "Phone Call"]
ENGAGEMENT_CHANNELS = ["In-person", "Digital", "Event"]

PAYER_TYPES = ["Government Scheme", "Private Insurance", "Out-of-pocket", "Corporate Plan"]


def month_range(start: str, end: str):
    return pd.date_range(start=start, end=end, freq="MS")


def generate_products(rng: np.random.Generator, n_products_per_area: int = 3) -> pd.DataFrame:
    rows = []
    pid = 1
    for area in THERAPY_AREAS:
        for i in range(n_products_per_area):
            product_id = f"P{pid:03d}"
            brand_name = f"{area[:4].upper()}-{chr(65 + i)}{pid}"
            molecule = f"Molecule-{area[:2].upper()}{i+1}"
            dosage_form = rng.choice(["Tablet", "Injection", "Capsule", "Syrup", "Inhaler"])
            launch_year = int(rng.integers(2016, 2023))
            launch_date = f"{launch_year}-{int(rng.integers(1,13)):02d}-01"
            price = round(float(rng.uniform(50, 4500)), 2)
            rows.append(
                dict(
                    product_id=product_id,
                    brand_name=brand_name,
                    therapy_area=area,
                    molecule=molecule,
                    dosage_form=dosage_form,
                    launch_date=launch_date,
                    price=price,
                )
            )
            pid += 1
    return pd.DataFrame(rows)


def generate_hcps(rng: np.random.Generator, products: pd.DataFrame, n_hcps: int = 400) -> pd.DataFrame:
    rows = []
    all_states = list(CITIES_BY_STATE.keys())
    seg_probs = [0.2, 0.5, 0.3]
    for i in range(1, n_hcps + 1):
        hcp_id = f"H{i:04d}"
        area = rng.choice(THERAPY_AREAS)
        specialty = rng.choice(SPECIALTIES_BY_THERAPY[area])
        state = rng.choice(all_states)
        city = rng.choice(CITIES_BY_STATE[state])
        hospital_type = rng.choice(HOSPITAL_TYPES, p=[0.25, 0.4, 0.15, 0.2])
        segment = rng.choice(HCP_SEGMENTS, p=seg_probs)
        rows.append(
            dict(
                hcp_id=hcp_id,
                specialty=specialty,
                primary_therapy_area=area,
                city=city,
                state=state,
                hospital_type=hospital_type,
                hcp_segment=segment,
            )
        )
    return pd.DataFrame(rows)


def region_for_state(state: str) -> str:
    for region, states in STATES_BY_REGION.items():
        if state in states:
            return region
    return "Central"


def generate_sales_and_prescriptions(
    rng: np.random.Generator,
    products: pd.DataFrame,
    hcps: pd.DataFrame,
    months: pd.DatetimeIndex,
):
    """Generate monthly sales_transactions and prescriptions, one row per
    (month, product, hcp) for a random subset of active hcp-product pairs
    each month, to keep volumes realistic rather than a full cross-join."""

    sales_rows = []
    presc_rows = []

    hcp_ids = hcps["hcp_id"].values
    hcp_segment_map = hcps.set_index("hcp_id")["hcp_segment"].to_dict()
    hcp_state_map = hcps.set_index("hcp_id")["state"].to_dict()
    hcp_area_map = hcps.set_index("hcp_id")["primary_therapy_area"].to_dict()

    segment_activity_weight = {"High potential": 0.85, "Medium potential": 0.55, "Low potential": 0.25}

    for _, prod in products.iterrows():
        product_id = prod["product_id"]
        base_price = prod["price"]
        area = prod["therapy_area"]

        # HCPs relevant to this product's therapy area engage more often
        relevant_hcps = hcps[hcps["primary_therapy_area"] == area]["hcp_id"].tolist()
        other_hcps = [h for h in hcp_ids if h not in relevant_hcps]

        # slight growth trend + seasonality per product
        trend = rng.uniform(0.002, 0.012)
        season_phase = rng.uniform(0, 2 * np.pi)

        for m_idx, month in enumerate(months):
            month_str = month.strftime("%Y-%m-%d")
            seasonal_factor = 1 + 0.15 * np.sin(2 * np.pi * month.month / 12 + season_phase)
            growth_factor = 1 + trend * m_idx

            active_relevant = [h for h in relevant_hcps if rng.random() < segment_activity_weight[hcp_segment_map[h]]]
            active_other = [h for h in other_hcps if rng.random() < 0.03]
            active_hcps = active_relevant + active_other

            for hcp_id in active_hcps:
                seg_mult = {"High potential": 1.6, "Medium potential": 1.0, "Low potential": 0.5}[
                    hcp_segment_map[hcp_id]
                ]
                base_units = rng.poisson(lam=max(1.0, 6 * seg_mult * seasonal_factor * growth_factor))
                if base_units <= 0:
                    continue
                units = int(base_units)
                gross_sales = round(units * base_price, 2)
                discount_rate = float(rng.uniform(0.02, 0.18))
                discount = round(gross_sales * discount_rate, 2)
                net_sales = round(gross_sales - discount, 2)
                state = hcp_state_map[hcp_id]
                region = region_for_state(state)

                sales_rows.append(
                    dict(
                        date=month_str,
                        product_id=product_id,
                        hcp_id=hcp_id,
                        region=region,
                        units=units,
                        gross_sales=gross_sales,
                        discount=discount,
                        net_sales=net_sales,
                    )
                )

                new_rx = int(rng.poisson(lam=max(0.5, units * rng.uniform(0.15, 0.35))))
                refill_rx = int(rng.poisson(lam=max(0.5, units * rng.uniform(0.2, 0.5))))
                total_rx = new_rx + refill_rx

                presc_rows.append(
                    dict(
                        date=month_str,
                        product_id=product_id,
                        hcp_id=hcp_id,
                        new_prescriptions=new_rx,
                        refill_prescriptions=refill_rx,
                        total_prescriptions=total_rx,
                    )
                )

    sales_df = pd.DataFrame(sales_rows)
    presc_df = pd.DataFrame(presc_rows)
    return sales_df, presc_df


def generate_market_data(rng: np.random.Generator, products: pd.DataFrame, sales_df: pd.DataFrame, months: pd.DatetimeIndex):
    rows = []
    company_sales_by_area_month = (
        sales_df.merge(products[["product_id", "therapy_area"]], on="product_id")
        .groupby([pd.to_datetime(sales_df["date"]).values.astype("datetime64[M]"), "therapy_area"])["net_sales"]
        .sum()
    )
    # rebuild grouping cleanly
    sales_df2 = sales_df.merge(products[["product_id", "therapy_area", "brand_name"]], on="product_id")
    sales_df2["month"] = pd.to_datetime(sales_df2["date"]).values.astype("datetime64[M]")

    for area in THERAPY_AREAS:
        area_products = products[products["therapy_area"] == area]
        # base market size per area, grows slowly with noise
        base_market = float(rng.uniform(2_000_000, 8_000_000))
        market_trend = rng.uniform(0.001, 0.01)
        for m_idx, month in enumerate(months):
            month_np = np.datetime64(month, "M")
            company_sales = float(
                sales_df2[(sales_df2["therapy_area"] == area) & (sales_df2["month"] == month_np)]["net_sales"].sum()
            )
            market_size = base_market * (1 + market_trend * m_idx) * (1 + rng.uniform(-0.03, 0.03))
            competitor_sales = max(0.0, market_size - company_sales)
            market_share = round(company_sales / market_size, 4) if market_size > 0 else 0.0

            for _, prod in area_products.iterrows():
                prod_sales = float(
                    sales_df2[(sales_df2["product_id"] == prod["product_id"]) & (sales_df2["month"] == month_np)][
                        "net_sales"
                    ].sum()
                )
                rows.append(
                    dict(
                        month=month.strftime("%Y-%m-%d"),
                        therapy_area=area,
                        product=prod["brand_name"],
                        product_id=prod["product_id"],
                        market_size=round(market_size, 2),
                        competitor_sales=round(competitor_sales, 2),
                        company_sales=round(prod_sales, 2),
                        market_share=round(prod_sales / market_size, 4) if market_size > 0 else 0.0,
                    )
                )
    return pd.DataFrame(rows)


def generate_patient_access(rng: np.random.Generator, months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for region in REGIONS:
        for payer in PAYER_TYPES:
            base_approval = rng.uniform(0.55, 0.9)
            for month in months:
                approval_rate = float(np.clip(base_approval + rng.uniform(-0.05, 0.05), 0.3, 0.98))
                rejection_rate = round(1 - approval_rate, 4)
                avg_days = float(np.clip(rng.normal(loc=12 if payer == "Government Scheme" else 6, scale=3), 1, 45))
                rows.append(
                    dict(
                        month=month.strftime("%Y-%m-%d"),
                        region=region,
                        payer_type=payer,
                        approval_rate=round(approval_rate, 4),
                        rejection_rate=rejection_rate,
                        average_access_days=round(avg_days, 1),
                    )
                )
    return pd.DataFrame(rows)


def generate_hcp_engagement(rng: np.random.Generator, hcps: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    channel_map = {
        "Field Visit": "In-person",
        "Email": "Digital",
        "Webinar": "Digital",
        "Conference": "Event",
        "Phone Call": "In-person",
    }
    seg_visits = {"High potential": 4, "Medium potential": 2, "Low potential": 0.7}

    for _, hcp in hcps.iterrows():
        hcp_id = hcp["hcp_id"]
        segment = hcp["hcp_segment"]
        for month in months:
            n_interactions = rng.poisson(lam=seg_visits[segment])
            for _ in range(int(n_interactions)):
                interaction_type = rng.choice(INTERACTION_TYPES, p=[0.35, 0.3, 0.15, 0.1, 0.1])
                # random day within month
                day = int(rng.integers(1, 28))
                date_str = f"{month.year}-{month.month:02d}-{day:02d}"
                rows.append(
                    dict(
                        date=date_str,
                        hcp_id=hcp_id,
                        interaction_type=interaction_type,
                        interaction_count=1,
                        engagement_channel=channel_map[interaction_type],
                    )
                )
    df = pd.DataFrame(rows)
    # aggregate multiple same-day/type interactions into counts
    df = (
        df.groupby(["date", "hcp_id", "interaction_type", "engagement_channel"], as_index=False)[
            "interaction_count"
        ].sum()
    )
    return df


def inject_data_quality_issues(rng: np.random.Generator, sales_df: pd.DataFrame, hcps: pd.DataFrame) -> pd.DataFrame:
    """Deliberately introduce a small, controlled number of data-quality
    issues into a copy of sales_transactions so the Data Quality module
    has something real to detect (missing HCPs, duplicates, invalid IDs,
    negative sales, bad dates)."""
    df = sales_df.copy()
    n = len(df)

    # 1. Missing HCP mappings (~0.8%)
    missing_idx = rng.choice(df.index, size=int(n * 0.008), replace=False)
    df.loc[missing_idx, "hcp_id"] = np.nan

    # 2. Duplicate records (~0.2%)
    dup_idx = rng.choice(df.index, size=int(n * 0.002), replace=False)
    dup_rows = df.loc[dup_idx]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Invalid product IDs (~0.1%)
    invalid_pid_idx = rng.choice(df.index, size=int(n * 0.001), replace=False)
    df.loc[invalid_pid_idx, "product_id"] = "P999"

    # 4. Invalid / malformed dates (~0.1%)
    invalid_date_idx = rng.choice(df.index, size=int(n * 0.001), replace=False)
    df.loc[invalid_date_idx, "date"] = "0000-00-00"

    # 5. Negative sales / units (~0.15%)
    neg_idx = rng.choice(df.index, size=int(n * 0.0015), replace=False)
    df.loc[neg_idx, "net_sales"] = -np.abs(df.loc[neg_idx, "net_sales"])
    df.loc[neg_idx, "units"] = -np.abs(df.loc[neg_idx, "units"])

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--seed", type=int, default=RNG_SEED_DEFAULT)
    parser.add_argument("--n-hcps", type=int, default=400)
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    outdir = args.outdir or os.path.join(script_dir, "..", "data", "raw")
    os.makedirs(outdir, exist_ok=True)

    months = month_range(args.start, args.end)

    print(f"Generating products...")
    products = generate_products(rng)

    print(f"Generating {args.n_hcps} HCPs...")
    hcps = generate_hcps(rng, products, n_hcps=args.n_hcps)

    print(f"Generating sales & prescriptions for {len(months)} months...")
    sales_df, presc_df = generate_sales_and_prescriptions(rng, products, hcps, months)

    print("Injecting controlled data-quality issues into a raw sales copy...")
    sales_df_raw = inject_data_quality_issues(rng, sales_df, hcps)

    print("Generating market data...")
    market_df = generate_market_data(rng, products, sales_df, months)

    print("Generating patient access data...")
    access_df = generate_patient_access(rng, months)

    print("Generating HCP engagement data...")
    engagement_df = generate_hcp_engagement(rng, hcps, months)

    # Write outputs
    products.to_csv(os.path.join(outdir, "product_master.csv"), index=False)
    hcps.to_csv(os.path.join(outdir, "hcp_master.csv"), index=False)
    sales_df_raw.to_csv(os.path.join(outdir, "sales_transactions.csv"), index=False)
    presc_df.to_csv(os.path.join(outdir, "prescriptions.csv"), index=False)
    market_df.to_csv(os.path.join(outdir, "market_data.csv"), index=False)
    access_df.to_csv(os.path.join(outdir, "patient_access.csv"), index=False)
    engagement_df.to_csv(os.path.join(outdir, "hcp_engagement.csv"), index=False)

    print("\nDone. Row counts:")
    print(f"  product_master.csv       : {len(products):>8,}")
    print(f"  hcp_master.csv           : {len(hcps):>8,}")
    print(f"  sales_transactions.csv   : {len(sales_df_raw):>8,}")
    print(f"  prescriptions.csv        : {len(presc_df):>8,}")
    print(f"  market_data.csv          : {len(market_df):>8,}")
    print(f"  patient_access.csv       : {len(access_df):>8,}")
    print(f"  hcp_engagement.csv       : {len(engagement_df):>8,}")
    print(f"\nFiles written to: {os.path.abspath(outdir)}")


if __name__ == "__main__":
    main()
