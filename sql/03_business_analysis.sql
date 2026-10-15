-- =====================================================================
-- 03_business_analysis.sql
-- Business analytics queries covering the 5 platform modules:
--   1. Commercial Performance
--   2. Customer / HCP Analytics
--   3. Market & Competitive Analytics
--   4. Forecasting & Scenario Analysis
--   5. Data Quality & Reporting
-- =====================================================================

SET search_path TO pharma_analytics;

-- =====================================================================
-- MODULE 1: COMMERCIAL PERFORMANCE
-- =====================================================================

-- 1.1 Monthly net sales trend (company-wide)
SELECT
    DATE_TRUNC('month', txn_date) AS month,
    SUM(net_sales)  AS net_sales,
    SUM(units)      AS units,
    ROUND(SUM(net_sales) / NULLIF(SUM(units), 0), 2) AS avg_selling_price
FROM fact_sales
GROUP BY 1
ORDER BY 1;

-- 1.2 Sales by product with MoM growth
WITH monthly_product_sales AS (
    SELECT
        p.brand_name,
        DATE_TRUNC('month', s.txn_date) AS month,
        SUM(s.net_sales) AS net_sales
    FROM fact_sales s
    JOIN dim_product p ON p.product_id = s.product_id
    GROUP BY 1, 2
)
SELECT
    brand_name,
    month,
    net_sales,
    LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY month) AS prev_month_sales,
    ROUND(
        100.0 * (net_sales - LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY month))
        / NULLIF(LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY month), 0),
        2
    ) AS mom_growth_pct
FROM monthly_product_sales
ORDER BY brand_name, month;

-- 1.3 Sales by region
SELECT
    region,
    SUM(net_sales) AS net_sales,
    ROUND(100.0 * SUM(net_sales) / SUM(SUM(net_sales)) OVER (), 2) AS pct_of_total
FROM fact_sales
GROUP BY region
ORDER BY net_sales DESC;

-- 1.4 Product contribution to total net sales (Pareto view)
SELECT
    p.brand_name,
    p.therapy_area,
    SUM(s.net_sales) AS net_sales,
    ROUND(100.0 * SUM(s.net_sales) / SUM(SUM(s.net_sales)) OVER (), 2) AS pct_of_total,
    ROUND(SUM(SUM(s.net_sales)) OVER (ORDER BY SUM(s.net_sales) DESC)
        / SUM(SUM(s.net_sales)) OVER () * 100, 2) AS cumulative_pct
FROM fact_sales s
JOIN dim_product p ON p.product_id = s.product_id
GROUP BY p.brand_name, p.therapy_area
ORDER BY net_sales DESC;

-- 1.5 YoY growth by product
WITH yearly AS (
    SELECT
        p.brand_name,
        EXTRACT(YEAR FROM s.txn_date)::int AS yr,
        SUM(s.net_sales) AS net_sales
    FROM fact_sales s
    JOIN dim_product p ON p.product_id = s.product_id
    GROUP BY 1, 2
)
SELECT
    brand_name,
    yr,
    net_sales,
    LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY yr) AS prev_year_sales,
    ROUND(
        100.0 * (net_sales - LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY yr))
        / NULLIF(LAG(net_sales) OVER (PARTITION BY brand_name ORDER BY yr), 0),
        2
    ) AS yoy_growth_pct
FROM yearly
ORDER BY brand_name, yr;

-- =====================================================================
-- MODULE 2: CUSTOMER / HCP ANALYTICS
-- =====================================================================

-- 2.1 Highest-value HCPs (by net sales attributed)
SELECT
    h.hcp_id,
    h.specialty,
    h.city,
    h.state,
    h.hcp_segment,
    f.monetary_value,
    f.frequency,
    f.recency_days,
    f.growth_pct,
    f.value_growth_segment
FROM analytics_hcp_features f
JOIN dim_hcp h ON h.hcp_id = f.hcp_id
ORDER BY f.monetary_value DESC
LIMIT 25;

-- 2.2 Specialty contribution to total prescriptions
SELECT
    h.specialty,
    SUM(rx.total_prescriptions) AS total_prescriptions,
    ROUND(100.0 * SUM(rx.total_prescriptions) / SUM(SUM(rx.total_prescriptions)) OVER (), 2) AS pct_of_total
FROM fact_prescriptions rx
JOIN dim_hcp h ON h.hcp_id = rx.hcp_id
GROUP BY h.specialty
ORDER BY total_prescriptions DESC;

-- 2.3 Fastest-growing HCPs (growth_pct desc, min activity threshold)
SELECT
    hcp_id, monetary_value, growth_pct, value_growth_segment
FROM analytics_hcp_features
WHERE frequency > 10
ORDER BY growth_pct DESC
LIMIT 25;

-- 2.4 HCP segment distribution (value/growth quadrant) x potential segment
SELECT
    hcp_segment,
    value_growth_segment,
    COUNT(*) AS n_hcps,
    ROUND(AVG(monetary_value), 2) AS avg_monetary_value
FROM analytics_hcp_features f
JOIN dim_hcp h ON h.hcp_id = f.hcp_id
GROUP BY hcp_segment, value_growth_segment
ORDER BY hcp_segment, value_growth_segment;

-- 2.5 High-potential HCPs with low engagement (targeting list)
SELECT hcp_id, monetary_value, recency_days, value_growth_segment
FROM analytics_hcp_features f
JOIN dim_hcp h USING (hcp_id)
WHERE h.hcp_segment = 'High potential'
  AND value_growth_segment = 'High Value / Low Engagement'
ORDER BY monetary_value DESC;

-- =====================================================================
-- MODULE 3: MARKET & COMPETITIVE ANALYTICS
-- =====================================================================

-- 3.1 Latest month market share by product
WITH latest_month AS (SELECT MAX(month) AS m FROM fact_market)
SELECT
    p.brand_name,
    fm.therapy_area,
    fm.market_share,
    fm.company_sales,
    fm.competitor_sales,
    fm.market_size
FROM fact_market fm
JOIN dim_product p ON p.product_id = fm.product_id
JOIN latest_month lm ON fm.month = lm.m
ORDER BY fm.therapy_area, fm.market_share DESC;

-- 3.2 Market share trend over time by therapy area (company aggregate)
SELECT
    month,
    therapy_area,
    SUM(company_sales) AS company_sales,
    SUM(market_size)   AS market_size,
    ROUND(SUM(company_sales) / NULLIF(SUM(market_size), 0), 4) AS market_share
FROM fact_market
GROUP BY month, therapy_area
ORDER BY therapy_area, month;

-- 3.3 Market share drivers (why did share move?) — see also
-- src/feature_engineering.py -> market_share_drivers.csv for the
-- Python-computed version with company_sales_growth_pct / market_growth_pct.
WITH share_chg AS (
    SELECT
        product_id,
        month,
        market_share,
        market_share - LAG(market_share) OVER (PARTITION BY product_id ORDER BY month) AS share_change,
        company_sales - LAG(company_sales) OVER (PARTITION BY product_id ORDER BY month) AS company_sales_change,
        market_size - LAG(market_size) OVER (PARTITION BY product_id ORDER BY month) AS market_size_change
    FROM fact_market
)
SELECT
    p.brand_name,
    sc.month,
    sc.market_share,
    ROUND(sc.share_change * 100, 2) AS share_change_pp,
    CASE
        WHEN sc.share_change IS NULL THEN 'Insufficient history'
        WHEN sc.share_change > 0 THEN 'Share gain'
        WHEN sc.share_change < 0 THEN 'Share loss'
        ELSE 'Stable'
    END AS movement
FROM share_chg sc
JOIN dim_product p ON p.product_id = sc.product_id
ORDER BY p.brand_name, sc.month;

-- 3.4 Region growth (YoY) — approximate region growth via sales as proxy
WITH yearly_region AS (
    SELECT region, EXTRACT(YEAR FROM txn_date)::int AS yr, SUM(net_sales) AS net_sales
    FROM fact_sales
    GROUP BY 1, 2
)
SELECT
    region, yr, net_sales,
    ROUND(100.0 * (net_sales - LAG(net_sales) OVER (PARTITION BY region ORDER BY yr))
        / NULLIF(LAG(net_sales) OVER (PARTITION BY region ORDER BY yr), 0), 2) AS yoy_growth_pct
FROM yearly_region
ORDER BY region, yr;

-- =====================================================================
-- MODULE 4: FORECASTING & SCENARIO ANALYSIS
-- =====================================================================

-- 4.1 Base-case forecast vs actuals, company-wide, by month
SELECT
    month,
    scenario,
    SUM(COALESCE(actual_net_sales, 0))   AS actual_net_sales,
    SUM(COALESCE(forecast_net_sales, 0)) AS forecast_net_sales
FROM analytics_sales_forecast
WHERE scenario IN ('Actual', 'Base Case')
GROUP BY month, scenario
ORDER BY month, scenario;

-- 4.2 Scenario comparison for next N months (company-wide)
SELECT
    month,
    scenario,
    SUM(forecast_net_sales) AS forecast_net_sales
FROM analytics_sales_forecast
WHERE is_forecast = TRUE
GROUP BY month, scenario
ORDER BY month, scenario;

-- 4.3 Product-level forecast detail
SELECT
    p.brand_name,
    f.month,
    f.scenario,
    f.forecast_net_sales
FROM analytics_sales_forecast f
JOIN dim_product p ON p.product_id = f.product_id
WHERE f.is_forecast = TRUE
ORDER BY p.brand_name, f.month, f.scenario;

-- =====================================================================
-- MODULE 5: DATA QUALITY & REPORTING
-- =====================================================================

-- 5.1 Basic completeness / validity checks on fact_sales
SELECT
    COUNT(*)                                              AS total_records,
    COUNT(*) FILTER (WHERE hcp_id IS NULL)                AS missing_hcp,
    COUNT(*) FILTER (WHERE net_sales < 0 OR units < 0)     AS negative_value_records,
    COUNT(*) FILTER (WHERE is_outlier)                     AS outlier_records,
    COUNT(*) - COUNT(DISTINCT (txn_date, product_id, hcp_id, units, net_sales)) AS possible_duplicates
FROM fact_sales;

-- 5.2 Records per month (volume trend / data completeness sanity check)
SELECT DATE_TRUNC('month', txn_date) AS month, COUNT(*) AS n_records
FROM fact_sales
GROUP BY 1
ORDER BY 1;

-- 5.3 Orphan check: sales referencing a product not in dim_product
SELECT s.product_id, COUNT(*)
FROM fact_sales s
LEFT JOIN dim_product p ON p.product_id = s.product_id
WHERE p.product_id IS NULL
GROUP BY s.product_id;
