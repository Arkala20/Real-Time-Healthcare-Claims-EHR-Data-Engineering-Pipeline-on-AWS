-- ============================================================
-- 04_tables_cms.sql
-- CMS Claims table DDL
-- Source: cms_claims_etl.py Glue job output
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

-- dim_patient_cms
-- Source: beneficiary_summary CSV → process_beneficiary()
CREATE TABLE IF NOT EXISTS dim_patient_cms (
    patient_key      STRING,
    patient_id       STRING,
    birth_date       DATE,
    death_date       DATE,
    gender_code      INT,
    race_code        INT,
    state_code       STRING,
    county_code      STRING,
    plan_type        INT,
    chronic_diabetes         BOOLEAN,
    chronic_kidney           BOOLEAN,
    chronic_cancer           BOOLEAN,
    chronic_copd             BOOLEAN,
    chronic_depression       BOOLEAN,
    chronic_ischemic_heart   BOOLEAN,
    chronic_osteoporosis     BOOLEAN,
    chronic_ra_oa            BOOLEAN,
    chronic_stroke           BOOLEAN,
    coverage_months  INT,
    gender_label     STRING,
    race_label       STRING,
    is_deceased      BOOLEAN,
    missing_birth_date_flag BOOLEAN,
    age              INT,
    age_group        STRING,
    risk_score       INT,
    risk_tier        STRING,
    is_chronic       BOOLEAN
);

-- dim_provider_cms
-- Source: providers CSV → process_providers()
CREATE TABLE IF NOT EXISTS dim_provider_cms (
    provider_key             STRING,
    provider_id              STRING,
    npi                      STRING,
    specialty_code           STRING,
    state_code               STRING,
    org_name                 STRING,
    first_name               STRING,
    last_name                STRING,
    group_participation_flag STRING
);

-- fact_claims
-- Source: inpatient_claims + outpatient_claims → process_inpatient_claims()
CREATE TABLE IF NOT EXISTS fact_claims (
    claim_key          STRING,
    claim_id           STRING,
    patient_id         STRING,
    provider_id        STRING,
    claim_type         STRING,
    admit_date         DATE,
    discharge_date     DATE,
    length_of_stay     INT,
    payment_amount     FLOAT,
    deductible_amount  FLOAT,
    coinsurance_amount FLOAT,
    per_diem_amount    FLOAT,
    submitted_amount   FLOAT,
    allowed_amount     FLOAT,
    drg_code           STRING,
    diag_code_1        STRING,
    diag_code_2        STRING,
    diag_code_3        STRING,
    diag_code_4        STRING,
    diag_code_5        STRING,
    is_high_cost       BOOLEAN,
    is_payment_missing BOOLEAN,
    year               INT,
    quarter            INT,
    month              INT,
    week_of_year       INT,
    date_key           INT
);

-- fact_carrier_claims
-- Source: carrier_claims CSV → process_carrier_claims()
CREATE TABLE IF NOT EXISTS fact_carrier_claims (
    claim_key          STRING,
    claim_id           STRING,
    patient_id         STRING,
    performing_npi     STRING,
    service_date       DATE,
    service_end_date   DATE,
    payment_amount     FLOAT,
    deductible_amount  FLOAT,
    coinsurance_amount FLOAT,
    hcpcs_code         STRING,
    claim_status_code  STRING,
    claim_status       STRING,
    is_high_cost       BOOLEAN,
    is_payment_missing BOOLEAN,
    year               INT,
    quarter            INT,
    month              INT,
    week_of_year       INT,
    date_key           INT
);

-- fact_prescriptions
-- Source: prescription_drug_events CSV → process_prescriptions()
CREATE TABLE IF NOT EXISTS fact_prescriptions (
    prescription_key   STRING,
    prescription_id    STRING,
    patient_id         STRING,
    drug_code          STRING,
    generic_name       STRING,
    brand_name         STRING,
    service_date       DATE,
    days_supply        INT,
    quantity_dispensed INT,
    patient_pay_amount FLOAT,
    total_cost         FLOAT,
    plan_pay_amount    FLOAT,
    is_high_cost       BOOLEAN,
    year               INT,
    quarter            INT,
    month              INT,
    week_of_year       INT,
    date_key           INT
);

-- Verify
SHOW TABLES LIKE '%cms%';
SHOW TABLES LIKE 'fact_%';
