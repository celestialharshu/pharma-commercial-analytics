-- =====================================================================
-- 01_schema.sql
-- Pharma Commercial Performance & Market Insights Platform
-- PostgreSQL schema (dimensional-model style: dims + fact tables)
-- =====================================================================

DROP SCHEMA IF EXISTS pharma_analytics CASCADE;
CREATE SCHEMA pharma_analytics;
SET search_path TO pharma_analytics;

-- ---------------------------------------------------------------------
-- Dimension: Product
-- ---------------------------------------------------------------------
CREATE TABLE dim_product (
    product_id      VARCHAR(10) PRIMARY KEY,
    brand_name      VARCHAR(100) NOT NULL,
    therapy_area    VARCHAR(50)  NOT NULL,
    molecule        VARCHAR(100),
    dosage_form     VARCHAR(30),
    launch_date     DATE,
    price           NUMERIC(12, 2)
);

-- ---------------------------------------------------------------------
-- Dimension: Healthcare Provider (HCP)
-- ---------------------------------------------------------------------
CREATE TABLE dim_hcp (
    hcp_id                  VARCHAR(10) PRIMARY KEY,
    specialty               VARCHAR(60),
    primary_therapy_area    VARCHAR(50),
    city                    VARCHAR(60),
    state                   VARCHAR(60),
    hospital_type           VARCHAR(30),
    hcp_segment             VARCHAR(30)  -- High / Medium / Low potential
);

-- ---------------------------------------------------------------------
-- Dimension: Date (optional helper dim, populated via generate_series)
-- ---------------------------------------------------------------------
CREATE TABLE dim_date (
    date_key        DATE PRIMARY KEY,
    year            INT,
    month           INT,
    month_name      VARCHAR(15),
    quarter         INT,
    is_month_start  BOOLEAN
);

-- ---------------------------------------------------------------------
-- Fact: Sales transactions (grain: one row per date-product-hcp txn)
-- ---------------------------------------------------------------------
CREATE TABLE fact_sales (
    sale_id         BIGSERIAL PRIMARY KEY,
    txn_date        DATE NOT NULL,
    product_id      VARCHAR(10) REFERENCES dim_product(product_id),
    hcp_id          VARCHAR(10) REFERENCES dim_hcp(hcp_id),
    region          VARCHAR(30),
    units           INT,
    gross_sales     NUMERIC(14, 2),
    discount        NUMERIC(14, 2),
    net_sales       NUMERIC(14, 2),
    is_outlier      BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_fact_sales_date ON fact_sales (txn_date);
CREATE INDEX idx_fact_sales_product ON fact_sales (product_id);
CREATE INDEX idx_fact_sales_hcp ON fact_sales (hcp_id);
CREATE INDEX idx_fact_sales_region ON fact_sales (region);

-- ---------------------------------------------------------------------
-- Fact: Prescriptions (grain: one row per date-product-hcp)
-- ---------------------------------------------------------------------
CREATE TABLE fact_prescriptions (
    rx_id                   BIGSERIAL PRIMARY KEY,
    rx_date                 DATE NOT NULL,
    product_id              VARCHAR(10) REFERENCES dim_product(product_id),
    hcp_id                  VARCHAR(10) REFERENCES dim_hcp(hcp_id),
    new_prescriptions       INT,
    refill_prescriptions    INT,
    total_prescriptions     INT
);

CREATE INDEX idx_fact_rx_date ON fact_prescriptions (rx_date);
CREATE INDEX idx_fact_rx_product ON fact_prescriptions (product_id);
CREATE INDEX idx_fact_rx_hcp ON fact_prescriptions (hcp_id);

-- ---------------------------------------------------------------------
-- Fact: Market data (grain: one row per month-product)
-- ---------------------------------------------------------------------
CREATE TABLE fact_market (
    market_id           BIGSERIAL PRIMARY KEY,
    month               DATE NOT NULL,
    therapy_area        VARCHAR(50),
    product_id          VARCHAR(10) REFERENCES dim_product(product_id),
    market_size         NUMERIC(16, 2),
    competitor_sales    NUMERIC(16, 2),
    company_sales       NUMERIC(16, 2),
    market_share        NUMERIC(6, 4)
);

CREATE INDEX idx_fact_market_month ON fact_market (month);
CREATE INDEX idx_fact_market_product ON fact_market (product_id);

-- ---------------------------------------------------------------------
-- Fact: Patient access / payer data (grain: one row per month-region-payer)
-- ---------------------------------------------------------------------
CREATE TABLE fact_patient_access (
    access_id           BIGSERIAL PRIMARY KEY,
    month               DATE NOT NULL,
    region              VARCHAR(30),
    payer_type          VARCHAR(40),
    approval_rate       NUMERIC(6, 4),
    rejection_rate      NUMERIC(6, 4),
    average_access_days NUMERIC(6, 1)
);

CREATE INDEX idx_fact_access_month ON fact_patient_access (month);

-- ---------------------------------------------------------------------
-- Fact: HCP engagement (grain: one row per date-hcp-interaction_type)
-- ---------------------------------------------------------------------
CREATE TABLE fact_hcp_engagement (
    engagement_id       BIGSERIAL PRIMARY KEY,
    engagement_date     DATE NOT NULL,
    hcp_id              VARCHAR(10) REFERENCES dim_hcp(hcp_id),
    interaction_type    VARCHAR(30),
    interaction_count   INT,
    engagement_channel  VARCHAR(20)
);

CREATE INDEX idx_fact_engagement_date ON fact_hcp_engagement (engagement_date);
CREATE INDEX idx_fact_engagement_hcp ON fact_hcp_engagement (hcp_id);

-- ---------------------------------------------------------------------
-- Analytics table: HCP RFM-style features (populated from Python)
-- ---------------------------------------------------------------------
CREATE TABLE analytics_hcp_features (
    hcp_id                  VARCHAR(10) PRIMARY KEY REFERENCES dim_hcp(hcp_id),
    monetary_value           NUMERIC(16, 2),
    frequency                INT,
    recency_days              INT,
    growth_pct                NUMERIC(8, 2),
    monetary_score           INT,
    recency_score            INT,
    frequency_score           INT,
    value_growth_segment      VARCHAR(50)
);

-- ---------------------------------------------------------------------
-- Analytics table: Sales forecast (populated from Python)
-- ---------------------------------------------------------------------
CREATE TABLE analytics_sales_forecast (
    forecast_id         BIGSERIAL PRIMARY KEY,
    product_id          VARCHAR(10) REFERENCES dim_product(product_id),
    month               DATE,
    actual_net_sales    NUMERIC(16, 2),
    forecast_net_sales  NUMERIC(16, 2),
    scenario            VARCHAR(30),
    is_forecast         BOOLEAN
);

CREATE INDEX idx_forecast_month ON analytics_sales_forecast (month);
CREATE INDEX idx_forecast_product ON analytics_sales_forecast (product_id);
