"""
app.py
-------
Streamlit dashboard for the Pharma Commercial Performance & Market
Insights Platform. Reads the processed CSVs from data/processed/
(run src/generate_data.py, src/data_cleaning.py, src/feature_engineering.py
and src/forecasting.py first if that folder is empty).

Run:
    streamlit run app.py
"""

import os

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Pharma Commercial Insights", layout="wide")

PROCESSED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "processed")


@st.cache_data
def load_data():
    products = pd.read_csv(os.path.join(PROCESSED_DIR, "product_master.csv"))
    hcps = pd.read_csv(os.path.join(PROCESSED_DIR, "hcp_master.csv"))
    sales = pd.read_csv(os.path.join(PROCESSED_DIR, "sales_transactions.csv"), parse_dates=["date"])
    presc = pd.read_csv(os.path.join(PROCESSED_DIR, "prescriptions.csv"), parse_dates=["date"])
    market = pd.read_csv(os.path.join(PROCESSED_DIR, "market_data.csv"), parse_dates=["month"])
    access = pd.read_csv(os.path.join(PROCESSED_DIR, "patient_access.csv"), parse_dates=["month"])
    engagement = pd.read_csv(os.path.join(PROCESSED_DIR, "hcp_engagement.csv"), parse_dates=["date"])
    hcp_features = pd.read_csv(os.path.join(PROCESSED_DIR, "hcp_features.csv"))
    kpi_summary = pd.read_csv(os.path.join(PROCESSED_DIR, "monthly_kpi_summary.csv"), parse_dates=["month"])
    drivers = pd.read_csv(os.path.join(PROCESSED_DIR, "market_share_drivers.csv"), parse_dates=["month"])
    forecast = pd.read_csv(os.path.join(PROCESSED_DIR, "sales_forecast.csv"), parse_dates=["month"])
    dq_report = pd.read_csv(os.path.join(PROCESSED_DIR, "data_quality_report.csv"))
    return dict(
        products=products, hcps=hcps, sales=sales, presc=presc, market=market,
        access=access, engagement=engagement, hcp_features=hcp_features,
        kpi_summary=kpi_summary, drivers=drivers, forecast=forecast, dq_report=dq_report,
    )


def missing_data_notice():
    st.error(
        "Processed data not found. From the project root, run:\n\n"
        "```bash\n"
        "python src/generate_data.py\n"
        "python src/data_cleaning.py\n"
        "python src/feature_engineering.py\n"
        "python src/forecasting.py\n"
        "```"
    )
    st.stop()


if not os.path.exists(os.path.join(PROCESSED_DIR, "sales_transactions.csv")):
    missing_data_notice()

data = load_data()

st.sidebar.title("Pharma Commercial Insights")
module = st.sidebar.radio(
    "Module",
    [
        "1. Commercial Performance",
        "2. Customer / HCP Analytics",
        "3. Market & Competitive Analytics",
        "4. Forecasting & Scenario Analysis",
        "5. Data Quality & Reporting",
    ],
)

# Global filters
all_products = sorted(data["products"]["brand_name"].unique())
all_regions = sorted(data["sales"]["region"].unique())
selected_products = st.sidebar.multiselect("Product filter", all_products, default=all_products)
selected_regions = st.sidebar.multiselect("Region filter", all_regions, default=all_regions)

sales = data["sales"].merge(data["products"][["product_id", "brand_name", "therapy_area"]], on="product_id")
sales = sales[sales["brand_name"].isin(selected_products) & sales["region"].isin(selected_regions)]
sales["month"] = sales["date"].values.astype("datetime64[M]")

presc = data["presc"].merge(data["products"][["product_id", "brand_name"]], on="product_id")
presc = presc[presc["brand_name"].isin(selected_products)]
presc["month"] = presc["date"].values.astype("datetime64[M]")


# =====================================================================
# MODULE 1: COMMERCIAL PERFORMANCE
# =====================================================================
if module.startswith("1"):
    st.title("Commercial Performance")

    total_net_sales = sales["net_sales"].sum()
    total_units = sales["units"].sum()
    total_rx = presc["total_prescriptions"].sum()
    asp = total_net_sales / total_units if total_units else 0

    monthly = sales.groupby("month")["net_sales"].sum()
    growth_pct = (
        100 * (monthly.iloc[-1] - monthly.iloc[-2]) / monthly.iloc[-2] if len(monthly) > 1 and monthly.iloc[-2] else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net Sales", f"₹{total_net_sales:,.0f}")
    c2.metric("Units", f"{total_units:,.0f}")
    c3.metric("Prescriptions", f"{total_rx:,.0f}")
    c4.metric("Avg Selling Price", f"₹{asp:,.2f}")
    c5.metric("MoM Growth (latest)", f"{growth_pct:+.1f}%")

    st.subheader("Monthly Sales Trend")
    st.line_chart(monthly)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sales by Product")
        by_product = sales.groupby("brand_name")["net_sales"].sum().sort_values(ascending=False)
        st.bar_chart(by_product)
    with col2:
        st.subheader("Sales by Region")
        by_region = sales.groupby("region")["net_sales"].sum().sort_values(ascending=False)
        st.bar_chart(by_region)

    st.subheader("Product Contribution (Pareto)")
    contrib = sales.groupby("brand_name")["net_sales"].sum().sort_values(ascending=False)
    contrib_pct = (contrib / contrib.sum() * 100).round(2)
    cum_pct = contrib_pct.cumsum().round(2)
    pareto_df = pd.DataFrame({"net_sales": contrib, "pct_of_total": contrib_pct, "cumulative_pct": cum_pct})
    st.dataframe(pareto_df, use_container_width=True)

    st.subheader("YoY / MoM Growth Detail")
    kpi = data["kpi_summary"]
    kpi = kpi[kpi["brand_name"].isin(selected_products) & kpi["region"].isin(selected_regions)]
    st.dataframe(
        kpi[["month", "brand_name", "region", "net_sales", "units", "asp", "mom_growth_pct", "yoy_growth_pct", "market_share"]]
        .sort_values("month", ascending=False),
        use_container_width=True,
        height=350,
    )


# =====================================================================
# MODULE 2: CUSTOMER / HCP ANALYTICS
# =====================================================================
elif module.startswith("2"):
    st.title("Customer / HCP Analytics")

    hf = data["hcp_features"]  # already includes specialty/state/hcp_segment from feature_engineering.py

    c1, c2, c3 = st.columns(3)
    c1.metric("Total HCPs", f"{len(hf):,}")
    c2.metric("High Value / High Growth", f"{(hf['value_growth_segment']=='High Value / High Growth').sum():,}")
    c3.metric("Avg Monetary Value", f"₹{hf['monetary_value'].mean():,.0f}")

    st.subheader("HCP Segments (Value / Growth)")
    seg_counts = hf["value_growth_segment"].value_counts()
    st.bar_chart(seg_counts)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top HCPs by Value")
        top_hcps = hf.sort_values("monetary_value", ascending=False).head(20)
        st.dataframe(
            top_hcps[["hcp_id", "specialty", "state", "hcp_segment", "monetary_value", "frequency", "growth_pct", "value_growth_segment"]],
            use_container_width=True,
        )
    with col2:
        st.subheader("Prescriptions by Specialty")
        rx_by_specialty = (
            presc.merge(data["hcps"][["hcp_id", "specialty"]], on="hcp_id")
            .groupby("specialty")["total_prescriptions"]
            .sum()
            .sort_values(ascending=False)
        )
        st.bar_chart(rx_by_specialty)

    st.subheader("Targeting List: High-Potential HCPs with Low Engagement")
    targets = hf[
        (hf["hcp_segment"] == "High potential") & (hf["value_growth_segment"] == "High Value / Low Engagement")
    ].sort_values("monetary_value", ascending=False)
    st.dataframe(targets, use_container_width=True)


# =====================================================================
# MODULE 3: MARKET & COMPETITIVE ANALYTICS
# =====================================================================
elif module.startswith("3"):
    st.title("Market & Competitive Analytics")

    market = data["market"]
    latest_month = market["month"].max()
    latest = market[market["month"] == latest_month]

    st.subheader(f"Market Share Snapshot — {latest_month.strftime('%B %Y')}")
    share_table = latest[["product", "therapy_area", "market_share", "company_sales", "competitor_sales"]].sort_values(
        "market_share", ascending=False
    )
    share_table["market_share"] = (share_table["market_share"] * 100).round(2)
    st.dataframe(share_table, use_container_width=True)

    st.subheader("Market Share Trend by Therapy Area")
    share_trend = market.groupby(["month", "therapy_area"]).apply(
        lambda g: g["company_sales"].sum() / g["market_size"].sum() if g["market_size"].sum() else 0
    ).reset_index(name="market_share")
    pivot = share_trend.pivot(index="month", columns="therapy_area", values="market_share")
    st.line_chart(pivot)

    st.subheader("Market Share Drivers (Why Did Share Move?)")
    drivers = data["drivers"].merge(data["products"][["product_id", "brand_name"]], on="product_id")
    drivers_view = drivers[drivers["brand_name"].isin(selected_products)][
        ["brand_name", "month", "market_share", "share_change_pp", "company_sales_growth_pct", "market_growth_pct", "driver_explanation"]
    ].sort_values("month", ascending=False)
    st.dataframe(drivers_view, use_container_width=True, height=400)

    st.subheader("Patient Access / Payer Snapshot")
    access = data["access"]
    latest_access = access[access["month"] == access["month"].max()]
    st.dataframe(
        latest_access.pivot_table(index="region", columns="payer_type", values="approval_rate").round(3) * 100,
        use_container_width=True,
    )


# =====================================================================
# MODULE 4: FORECASTING & SCENARIO ANALYSIS
# =====================================================================
elif module.startswith("4"):
    st.title("Forecasting & Scenario Analysis")

    forecast = data["forecast"]
    forecast = forecast[forecast["brand_name"].isin(selected_products)]

    st.subheader("Company-Wide: Actual vs Base Case Forecast")
    actual = forecast[forecast["scenario"] == "Actual"].groupby("month")["actual_net_sales"].sum()
    base = forecast[forecast["scenario"] == "Base Case"].groupby("month")["forecast_net_sales"].sum()
    combined = pd.DataFrame({"Actual": actual, "Forecast (Base Case)": base})
    st.line_chart(combined)

    st.subheader("Scenario Comparison (Next Months)")
    scenario_view = forecast[forecast["is_forecast"] == True]
    scenario_pivot = scenario_view.groupby(["month", "scenario"])["forecast_net_sales"].sum().unstack("scenario")
    st.line_chart(scenario_pivot)
    st.dataframe(scenario_pivot.round(0), use_container_width=True)

    st.subheader("Product-Level Forecast Detail")
    selected_product_forecast = st.selectbox("Select a product", selected_products)
    prod_data = forecast[forecast["brand_name"] == selected_product_forecast]
    prod_actual = prod_data[prod_data["scenario"] == "Actual"].set_index("month")["actual_net_sales"]
    prod_scenarios = prod_data[prod_data["is_forecast"] == True].pivot_table(
        index="month", columns="scenario", values="forecast_net_sales"
    )
    prod_combined = pd.concat([prod_actual.rename("Actual"), prod_scenarios], axis=1)
    st.line_chart(prod_combined)


# =====================================================================
# MODULE 5: DATA QUALITY & REPORTING
# =====================================================================
elif module.startswith("5"):
    st.title("Data Quality & Reporting")

    dq = data["dq_report"]
    st.subheader("Data Quality Report — All Tables")
    st.dataframe(dq, use_container_width=True)

    sales_row = dq[dq["table"] == "sales_transactions"]
    if len(sales_row):
        row = sales_row.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Records", f"{int(row['total_records']):,}")
        c2.metric("Duplicate Records", f"{int(row['duplicate_records']):,}")
        c3.metric("Missing HCP Mappings", f"{int(row['missing_hcp_mappings']):,}")
        c4.metric("Negative Value Records", f"{int(row['negative_value_records']):,}")
        c5.metric("% Records Removed", f"{row['pct_records_removed']:.2f}%")

    st.subheader("Raw → Analytics-Ready Pipeline")
    st.markdown(
        """
        ```
        Raw data (data/raw/)
              ↓
        Validation (nulls, duplicates, invalid IDs/dates, negative values)
              ↓
        Cleaning (src/data_cleaning.py)
              ↓
        Analytics-ready data (data/processed/)
              ↓
        Feature engineering (src/feature_engineering.py)
              ↓
        Forecasting (src/forecasting.py)
        ```
        """
    )

    st.subheader("Records Removed by Table")
    st.bar_chart(dq.set_index("table")["pct_records_removed"])

st.sidebar.markdown("---")
st.sidebar.caption("Synthetic data — for portfolio / demo purposes only.")
