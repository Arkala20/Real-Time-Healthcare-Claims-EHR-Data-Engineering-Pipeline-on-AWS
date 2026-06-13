# ── Diagnostics ───────────────────────────────────────────────────────────────

TABLE_ROW_COUNTS = """
SELECT 'dim_patient_cms'    AS table_name, COUNT(*) AS row_count FROM dim_patient_cms    UNION ALL
SELECT 'dim_provider_cms',                 COUNT(*)              FROM dim_provider_cms    UNION ALL
SELECT 'fact_claims',                      COUNT(*)              FROM fact_claims         UNION ALL
SELECT 'fact_carrier_claims',              COUNT(*)              FROM fact_carrier_claims UNION ALL
SELECT 'fact_prescriptions',               COUNT(*)              FROM fact_prescriptions  UNION ALL
SELECT 'dim_patient_ehr',                  COUNT(*)              FROM dim_patient_ehr     UNION ALL
SELECT 'dim_provider_ehr',                 COUNT(*)              FROM dim_provider_ehr    UNION ALL
SELECT 'fact_encounters',                  COUNT(*)              FROM fact_encounters     UNION ALL
SELECT 'fact_conditions',                  COUNT(*)              FROM fact_conditions     UNION ALL
SELECT 'fact_observations',                COUNT(*)              FROM fact_observations   UNION ALL
SELECT 'fact_medications',                 COUNT(*)              FROM fact_medications
ORDER BY row_count DESC
"""

NULL_CHECK_CMS_PATIENT = """
SELECT
    COUNT(*)                            AS total_rows,
    COUNT(patient_id)                   AS non_null_patient_id,
    COUNT(gender_label)                 AS non_null_gender,
    COUNT(race_label)                   AS non_null_race,
    COUNT(risk_tier)                    AS non_null_risk_tier,
    COUNT(risk_score)                   AS non_null_risk_score,
    COUNT(age)                          AS non_null_age,
    COUNT(age_group)                    AS non_null_age_group,
    COUNT(is_chronic)                   AS non_null_is_chronic,
    COUNT(coverage_months)              AS non_null_coverage_months
FROM dim_patient_cms
"""

NULL_CHECK_FACT_CLAIMS = """
SELECT
    COUNT(*)                            AS total_rows,
    COUNT(claim_id)                     AS non_null_claim_id,
    COUNT(claim_type)                   AS non_null_claim_type,
    COUNT(patient_id)                   AS non_null_patient_id,
    COUNT(payment_amount)               AS non_null_payment,
    COUNT(admit_date)                   AS non_null_admit_date,
    COUNT(year)                         AS non_null_year,
    COUNT(month)                        AS non_null_month
FROM fact_claims
"""

NULL_CHECK_EHR_ENCOUNTERS = """
SELECT
    COUNT(*)                            AS total_rows,
    COUNT(encounter_id)                 AS non_null_encounter_id,
    COUNT(patient_ref)                  AS non_null_patient_ref,
    COUNT(encounter_class)              AS non_null_encounter_class,
    COUNT(total_cost)                   AS non_null_total_cost,
    COUNT(is_emergency)                 AS non_null_is_emergency,
    COUNT(visit_year)                   AS non_null_visit_year
FROM fact_encounters
"""

SAMPLE_CMS_PATIENT = "SELECT * FROM dim_patient_cms LIMIT 5"
SAMPLE_FACT_CLAIMS = "SELECT * FROM fact_claims LIMIT 5"
SAMPLE_ENCOUNTERS  = "SELECT * FROM fact_encounters LIMIT 5"
SAMPLE_CONDITIONS  = "SELECT * FROM fact_conditions LIMIT 5"

# ── Main analytics queries (null-safe) ────────────────────────────────────────

RISK_TIER_DISTRIBUTION = """
SELECT
    COALESCE(risk_tier, 'Unknown')            AS risk_tier,
    COUNT(*)                                   AS patient_count,
    ROUND(AVG(COALESCE(risk_score, 0)), 2)    AS avg_risk_score,
    SUM(CASE WHEN is_chronic = TRUE THEN 1 ELSE 0 END) AS chronic_patients
FROM dim_patient_cms
GROUP BY 1
ORDER BY patient_count DESC
"""

CLAIMS_BY_MONTH = """
SELECT
    COALESCE(CAST(year AS VARCHAR), 'Unknown') || '-' ||
    LPAD(COALESCE(CAST(month AS VARCHAR), '0'), 2, '0') AS month_label,
    COALESCE(claim_type, 'Unknown')                      AS claim_type,
    COUNT(*)                                             AS claim_count,
    ROUND(SUM(COALESCE(payment_amount, 0)), 2)           AS total_payment,
    ROUND(AVG(COALESCE(payment_amount, 0)), 2)           AS avg_payment
FROM fact_claims
WHERE year IS NOT NULL AND month IS NOT NULL
GROUP BY year, month, claim_type
ORDER BY year, month
"""

TOP_CONDITIONS = """
SELECT
    COALESCE(icd10_code, 'Unknown')    AS icd10_code,
    COALESCE(icd10_display, 'Unknown') AS icd10_display,
    COUNT(*)                                                              AS occurrence_count,
    SUM(CASE WHEN is_chronic = TRUE THEN 1 ELSE 0 END)                   AS chronic_count,
    ROUND(SUM(CASE WHEN is_chronic = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS chronic_pct
FROM fact_conditions
WHERE clinical_status = 'active'
GROUP BY icd10_code, icd10_display
ORDER BY occurrence_count DESC
LIMIT 10
"""

ENCOUNTER_BREAKDOWN = """
SELECT
    COALESCE(encounter_class, 'Unknown')               AS encounter_class,
    COUNT(*)                                            AS visit_count,
    ROUND(AVG(COALESCE(total_cost, 0)), 2)             AS avg_cost,
    ROUND(SUM(COALESCE(total_cost, 0)), 2)             AS total_cost,
    ROUND(AVG(COALESCE(encounter_duration_hours, 0)), 1) AS avg_duration_hours,
    SUM(CASE WHEN is_emergency = TRUE THEN 1 ELSE 0 END) AS emergency_visits
FROM fact_encounters
GROUP BY 1
ORDER BY visit_count DESC
"""

AGE_CHRONIC_RATE = """
SELECT
    COALESCE(p.age_group, 'Unknown')                                        AS age_group,
    COUNT(DISTINCT p.patient_id)                                             AS patient_count,
    COUNT(DISTINCT c.patient_ref)                                            AS patients_with_conditions,
    SUM(CASE WHEN c.is_chronic = TRUE THEN 1 ELSE 0 END)                    AS chronic_condition_count,
    ROUND(COUNT(DISTINCT c.patient_ref) * 100.0 / NULLIF(COUNT(DISTINCT p.patient_id), 0), 1) AS pct_with_condition
FROM dim_patient_ehr p
LEFT JOIN fact_conditions c ON p.patient_id = c.patient_ref
GROUP BY 1
ORDER BY 1
"""

TOP_DRUGS = """
SELECT
    COALESCE(generic_name, 'Unknown') AS generic_name,
    COALESCE(brand_name, 'Unknown')   AS brand_name,
    COUNT(*)                          AS prescription_count,
    ROUND(AVG(COALESCE(days_supply, 0)), 1)        AS avg_days_supply,
    ROUND(SUM(COALESCE(total_cost, 0)), 2)          AS total_cost,
    ROUND(AVG(COALESCE(patient_pay_amount, 0)), 2)  AS avg_patient_pay
FROM fact_prescriptions
GROUP BY generic_name, brand_name
ORDER BY prescription_count DESC
LIMIT 10
"""

ABNORMAL_LABS = """
SELECT
    COALESCE(category, 'Unknown')                                         AS category,
    COUNT(*)                                                               AS total_observations,
    SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END)                   AS abnormal_count,
    ROUND(SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS abnormal_pct
FROM fact_observations
GROUP BY 1
ORDER BY abnormal_count DESC
"""

HIGH_COST_PATIENTS = """
SELECT
    p.patient_id,
    COALESCE(p.age_group, 'Unknown')    AS age_group,
    COALESCE(p.gender_label, 'Unknown') AS gender_label,
    COALESCE(p.risk_tier, 'Unknown')    AS risk_tier,
    COALESCE(p.risk_score, 0)           AS risk_score,
    COUNT(c.claim_id)                   AS total_claims,
    ROUND(SUM(COALESCE(c.payment_amount, 0)), 2) AS total_spend,
    ROUND(AVG(COALESCE(c.payment_amount, 0)), 2) AS avg_claim_cost
FROM dim_patient_cms p
JOIN fact_claims c ON p.patient_id = c.patient_id
GROUP BY p.patient_id, p.age_group, p.gender_label, p.risk_tier, p.risk_score
ORDER BY total_spend DESC
LIMIT 20
"""

MEDICATION_SPLIT = """
SELECT
    CASE WHEN is_chronic_med = TRUE THEN 'Chronic' ELSE 'Acute' END AS medication_type,
    COUNT(*)                    AS prescription_count,
    COUNT(DISTINCT patient_ref) AS unique_patients,
    COUNT(DISTINCT drug_name)   AS unique_drugs
FROM fact_medications
GROUP BY is_chronic_med
"""

KPI_SUMMARY = """
SELECT
    (SELECT COUNT(*) FROM dim_patient_cms)    AS cms_patients,
    (SELECT COUNT(*) FROM fact_claims)        AS total_claims,
    (SELECT ROUND(SUM(COALESCE(payment_amount, 0)), 0) FROM fact_claims) AS total_claims_spend,
    (SELECT COUNT(*) FROM dim_patient_ehr)    AS ehr_patients,
    (SELECT COUNT(*) FROM fact_encounters)    AS total_encounters,
    (SELECT COUNT(*) FROM fact_conditions)    AS total_conditions,
    (SELECT COUNT(*) FROM fact_prescriptions) AS total_prescriptions,
    (SELECT COUNT(*) FROM fact_observations)  AS total_observations
"""
