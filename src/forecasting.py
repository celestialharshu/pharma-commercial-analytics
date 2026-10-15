"""
forecasting.py
---------------
Builds a next-N-month sales forecast per product using a simple,
dependency-light Holt-Winters style exponential smoothing model
(statsmodels), with a linear-regression fallback. Also generates
Base / +5% / -5% / High-demand scenarios around the forecast.

Outputs:
    data/processed/sales_forecast.csv
        columns: product_id, brand_name, month, actual_net_sales,
                 forecast_net_sales, scenario, is_forecast

Run:
    python src/forecasting.py --horizon 6
"""

import argparse
import os
import warnings

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(SCRIPT_DIR, "..", "data", "processed")

warnings.filterwarnings("ignore")


def load_monthly_product_sales():
    sales = pd.read_csv(os.path.join(PROCESSED_DIR, "sales_transactions.csv"), parse_dates=["date"])
    products = pd.read_csv(os.path.join(PROCESSED_DIR, "product_master.csv"))
    sales["month"] = sales["date"].values.astype("datetime64[M]")
    monthly = sales.groupby(["product_id", "month"], as_index=False)["net_sales"].sum()
    monthly = monthly.merge(products[["product_id", "brand_name"]], on="product_id")
    return monthly


def forecast_series(ts: pd.Series, horizon: int) -> np.ndarray:
    """Try Holt-Winters exponential smoothing; fall back to a simple
    linear trend + average seasonality if the series is too short or
    the model fails to converge."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        if len(ts) >= 24:
            model = ExponentialSmoothing(
                ts, trend="add", seasonal="add", seasonal_periods=12, initialization_method="estimated"
            )
        elif len(ts) >= 12:
            model = ExponentialSmoothing(ts, trend="add", seasonal=None, initialization_method="estimated")
        else:
            raise ValueError("series too short for Holt-Winters")

        fit = model.fit(optimized=True)
        preds = fit.forecast(horizon)
        return np.maximum(preds.values, 0)
    except Exception:
        # Linear-regression fallback on time index
        x = np.arange(len(ts))
        coeffs = np.polyfit(x, ts.values, deg=1)
        future_x = np.arange(len(ts), len(ts) + horizon)
        preds = np.polyval(coeffs, future_x)
        return np.maximum(preds, 0)


def build_forecast_table(monthly: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows = []
    for product_id, grp in monthly.groupby("product_id"):
        grp = grp.sort_values("month")
        brand_name = grp["brand_name"].iloc[0]
        ts = grp.set_index("month")["net_sales"].asfreq("MS").fillna(0)

        # Historical (actuals)
        for month, value in ts.items():
            rows.append(
                dict(
                    product_id=product_id,
                    brand_name=brand_name,
                    month=month,
                    actual_net_sales=round(float(value), 2),
                    forecast_net_sales=np.nan,
                    scenario="Actual",
                    is_forecast=False,
                )
            )

        base_forecast = forecast_series(ts, horizon)
        last_month = ts.index.max()
        future_months = pd.date_range(last_month + pd.DateOffset(months=1), periods=horizon, freq="MS")

        scenario_multipliers = {
            "Base Case": 1.00,
            "+5% Scenario": 1.05,
            "-5% Scenario": 0.95,
            "High-Demand Scenario": 1.15,
        }

        for scenario_name, mult in scenario_multipliers.items():
            for month, value in zip(future_months, base_forecast):
                rows.append(
                    dict(
                        product_id=product_id,
                        brand_name=brand_name,
                        month=month,
                        actual_net_sales=np.nan,
                        forecast_net_sales=round(float(value * mult), 2),
                        scenario=scenario_name,
                        is_forecast=True,
                    )
                )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=6, help="Number of months to forecast")
    args = parser.parse_args()

    monthly = load_monthly_product_sales()
    print(f"Loaded monthly net sales for {monthly['product_id'].nunique()} products, "
          f"{monthly['month'].nunique()} months of history.")

    forecast_df = build_forecast_table(monthly, horizon=args.horizon)
    out_path = os.path.join(PROCESSED_DIR, "sales_forecast.csv")
    forecast_df.to_csv(out_path, index=False)

    n_forecast_rows = int(forecast_df["is_forecast"].sum())
    print(f"Forecast complete: {n_forecast_rows} forecast rows across "
          f"{forecast_df['scenario'].nunique()} scenarios written to {os.path.abspath(out_path)}")

    # Quick console summary: total base-case forecast next N months
    base_next = forecast_df[(forecast_df["scenario"] == "Base Case")]
    total_by_month = base_next.groupby("month")["forecast_net_sales"].sum().round(0)
    print("\nTotal company net sales — Base Case forecast:")
    print(total_by_month.to_string())


if __name__ == "__main__":
    main()
