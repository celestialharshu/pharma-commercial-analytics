-- =====================================================================
-- 02_load_data.sql
-- Loads processed CSVs (data/processed/) into the pharma_analytics schema.
--
-- Run with psql from the project root, e.g.:
--   psql -d pharma_db -f sql/02_load_data.sql
--
-- NOTE: \copy runs client-side (via psql), so relative paths resolve
-- against the directory you invoke psql from. Adjust paths if needed.
-- =====================================================================

SET search_path TO pharma_analytics;

\copy dim_product (product_id, brand_name, therapy_area, molecule, dosage_form, launch_date, price) FROM 'data/processed/product_master.csv' WITH (FORMAT csv, HEADER true)

\copy dim_hcp (hcp_id, specialty, primary_therapy_area, city, state, hospital_type, hcp_segment) FROM 'data/processed/hcp_master.csv' WITH (FORMAT csv, HEADER true)

\copy fact_sales (txn_date, product_id, hcp_id, region, units, gross_sales, discount, net_sales, is_outlier) FROM 'data/processed/sales_transactions.csv' WITH (FORMAT csv, HEADER true)

\copy fact_prescriptions (rx_date, product_id, hcp_id, new_prescriptions, refill_prescriptions, total_prescriptions) FROM 'data/processed/prescriptions.csv' WITH (FORMAT csv, HEADER true)

\copy fact_market (month, therapy_area, product, product_id, market_size, competitor_sales, company_sales, market_share) FROM 'data/processed/market_data.csv' WITH (FORMAT csv, HEADER true)
-- NOTE: market_data.csv has an extra 'product' text column not present in
-- fact_market; if COPY errors on column mismatch, drop that column first:
--   \! cut -d, -f1,3- data/processed/market_data.csv > /tmp/market_data_trimmed.csv
-- or load into a staging table and INSERT ... SELECT into fact_market.

\copy fact_patient_access (month, region, payer_type, approval_rate, rejection_rate, average_access_days) FROM 'data/processed/patient_access.csv' WITH (FORMAT csv, HEADER true)

\copy fact_hcp_engagement (engagement_date, hcp_id, interaction_type, interaction_count, engagement_channel) FROM 'data/processed/hcp_engagement.csv' WITH (FORMAT csv, HEADER true)

\copy analytics_hcp_features (hcp_id, monetary_value, frequency, recency_days, growth_pct, monetary_score, recency_score, frequency_score, value_growth_segment) FROM 'data/processed/hcp_features.csv' WITH (FORMAT csv, HEADER true)

\copy analytics_sales_forecast (product_id, month, actual_net_sales, forecast_net_sales, scenario, is_forecast) FROM 'data/processed/sales_forecast.csv' WITH (FORMAT csv, HEADER true)

-- Populate dim_date for a reasonable range (adjust as needed)
INSERT INTO dim_date (date_key, year, month, month_name, quarter, is_month_start)
SELECT
    d::date,
    EXTRACT(YEAR FROM d)::int,
    EXTRACT(MONTH FROM d)::int,
    TO_CHAR(d, 'Month'),
    EXTRACT(QUARTER FROM d)::int,
    (EXTRACT(DAY FROM d) = 1)
FROM generate_series('2022-01-01'::date, '2025-12-31'::date, '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- Quick sanity checks
SELECT 'dim_product' AS table_name, COUNT(*) FROM dim_product
UNION ALL SELECT 'dim_hcp', COUNT(*) FROM dim_hcp
UNION ALL SELECT 'fact_sales', COUNT(*) FROM fact_sales
UNION ALL SELECT 'fact_prescriptions', COUNT(*) FROM fact_prescriptions
UNION ALL SELECT 'fact_market', COUNT(*) FROM fact_market
UNION ALL SELECT 'fact_patient_access', COUNT(*) FROM fact_patient_access
UNION ALL SELECT 'fact_hcp_engagement', COUNT(*) FROM fact_hcp_engagement
UNION ALL SELECT 'analytics_hcp_features', COUNT(*) FROM analytics_hcp_features
UNION ALL SELECT 'analytics_sales_forecast', COUNT(*) FROM analytics_sales_forecast;
