RISK_TIER_DISTRIBUTION = """
SELECT
    risk_tier,
    COUNT(*)                          AS patient_count,
    ROUND(AVG(risk_score), 2)         AS avg_risk_score,
    SUM(CASE WHEN is_chronic THEN 1 ELSE 0 END) AS chronic_patients
FROM dim_patient_cms
GROUP BY risk_tier
ORDER BY patient_count DESC
"""

CLAIMS_BY_MONTH = """
SELECT
    year || '-' || LPAD(month::STRING, 2, '0') AS month_label,
    claim_type,
    COUNT(*)                                     AS claim_count,
    ROUND(SUM(payment_amount), 2)                AS total_payment,
    ROUND(AVG(payment_amount), 2)                AS avg_payment
FROM fact_claims
GROUP BY year, month, claim_type
ORDER BY year, month
"""

TOP_CONDITIONS = """
SELECT
    icd10_code,
    icd10_display,
    COUNT(*)                                                              AS occurrence_count,
    SUM(CASE WHEN is_chronic THEN 1 ELSE 0 END)                          AS chronic_count,
    ROUND(SUM(CASE WHEN is_chronic THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS chronic_pct
FROM fact_conditions
WHERE clinical_status = 'active'
GROUP BY icd10_code, icd10_display
ORDER BY occurrence_count DESC
LIMIT 10
"""

ENCOUNTER_BREAKDOWN = """
SELECT
    encounter_class,
    COUNT(*)                                      AS visit_count,
    ROUND(AVG(total_cost), 2)                     AS avg_cost,
    ROUND(SUM(total_cost), 2)                     AS total_cost,
    ROUND(AVG(encounter_duration_hours), 1)       AS avg_duration_hours,
    SUM(CASE WHEN is_emergency THEN 1 ELSE 0 END) AS emergency_visits
FROM fact_encounters
GROUP BY encounter_class
ORDER BY visit_count DESC
"""

AGE_CHRONIC_RATE = """
SELECT
    p.age_group,
    COUNT(DISTINCT p.patient_id)                                            AS patient_count,
    COUNT(DISTINCT c.patient_ref)                                           AS patients_with_conditions,
    SUM(CASE WHEN c.is_chronic THEN 1 ELSE 0 END)                          AS chronic_condition_count,
    ROUND(COUNT(DISTINCT c.patient_ref) * 100.0 / NULLIF(COUNT(DISTINCT p.patient_id), 0), 1) AS pct_with_condition
FROM dim_patient_ehr p
LEFT JOIN fact_conditions c ON p.patient_id = c.patient_ref
GROUP BY p.age_group
ORDER BY p.age_group
"""

TOP_DRUGS = """
SELECT
    generic_name,
    brand_name,
    COUNT(*)                          AS prescription_count,
    ROUND(AVG(days_supply), 1)        AS avg_days_supply,
    ROUND(SUM(total_cost), 2)         AS total_cost,
    ROUND(AVG(patient_pay_amount), 2) AS avg_patient_pay
FROM fact_prescriptions
GROUP BY generic_name, brand_name
ORDER BY prescription_count DESC
LIMIT 10
"""

ABNORMAL_LABS = """
SELECT
    category,
    COUNT(*)                                                              AS total_observations,
    SUM(CASE WHEN is_abnormal THEN 1 ELSE 0 END)                         AS abnormal_count,
    ROUND(SUM(CASE WHEN is_abnormal THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS abnormal_pct
FROM fact_observations
WHERE category IS NOT NULL
GROUP BY category
ORDER BY abnormal_count DESC
"""

HIGH_COST_PATIENTS = """
SELECT
    p.patient_id,
    p.age_group,
    p.gender_label,
    p.risk_tier,
    p.risk_score,
    COUNT(c.claim_id)               AS total_claims,
    ROUND(SUM(c.payment_amount), 2) AS total_spend,
    ROUND(AVG(c.payment_amount), 2) AS avg_claim_cost
FROM dim_patient_cms p
JOIN fact_claims c ON p.patient_id = c.patient_id
GROUP BY p.patient_id, p.age_group, p.gender_label, p.risk_tier, p.risk_score
ORDER BY total_spend DESC
LIMIT 20
"""

MEDICATION_SPLIT = """
SELECT
    CASE WHEN is_chronic_med THEN 'Chronic' ELSE 'Acute' END AS medication_type,
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
    (SELECT ROUND(SUM(payment_amount), 0) FROM fact_claims) AS total_claims_spend,
    (SELECT COUNT(*) FROM dim_patient_ehr)    AS ehr_patients,
    (SELECT COUNT(*) FROM fact_encounters)    AS total_encounters,
    (SELECT COUNT(*) FROM fact_conditions)    AS total_conditions,
    (SELECT COUNT(*) FROM fact_prescriptions) AS total_prescriptions,
    (SELECT COUNT(*) FROM fact_observations)  AS total_observations
"""
