# ── KPI ───────────────────────────────────────────────────────────────────────

KPI_SUMMARY = """
SELECT
    (SELECT COUNT(*)                          FROM dim_patient_cms)    AS cms_patients,
    (SELECT COUNT(*)                          FROM fact_claims)        AS total_claims,
    (SELECT ROUND(SUM(payment_amount), 0)     FROM fact_claims)        AS total_claims_spend,
    (SELECT COUNT(*)                          FROM fact_carrier_claims) AS carrier_claims,
    (SELECT COUNT(*)                          FROM fact_prescriptions)  AS total_prescriptions,
    (SELECT COUNT(*)                          FROM dim_patient_ehr)    AS ehr_patients,
    (SELECT COUNT(*)                          FROM fact_encounters)    AS total_encounters,
    (SELECT COUNT(*)                          FROM fact_medications)   AS total_medications,
    (SELECT COUNT(*)                          FROM fact_observations)  AS total_observations
"""

# ── CMS — Patient ─────────────────────────────────────────────────────────────

PATIENT_AGE_GROUP = """
SELECT
    COALESCE(age_group, 'Unknown')  AS age_group,
    COUNT(*)                        AS patient_count,
    ROUND(AVG(risk_score), 1)       AS avg_risk_score,
    SUM(CASE WHEN is_chronic = TRUE THEN 1 ELSE 0 END) AS chronic_count
FROM dim_patient_cms
GROUP BY 1
ORDER BY
    CASE age_group
        WHEN '0-17'  THEN 1
        WHEN '18-34' THEN 2
        WHEN '35-49' THEN 3
        WHEN '50-64' THEN 4
        WHEN '65+'   THEN 5
        ELSE 6
    END
"""

PATIENT_GENDER_RACE = """
SELECT
    COALESCE(gender_label, 'Unknown') AS gender_label,
    COALESCE(race_label,   'Unknown') AS race_label,
    COUNT(*) AS patient_count
FROM dim_patient_cms
GROUP BY 1, 2
ORDER BY patient_count DESC
"""

RISK_SCORE_DISTRIBUTION = """
SELECT
    CASE
        WHEN risk_score <= 2 THEN 'Low (0-2)'
        WHEN risk_score <= 5 THEN 'Medium (3-5)'
        ELSE                      'High (6+)'
    END                AS risk_tier,
    COUNT(*)           AS patient_count,
    ROUND(AVG(COALESCE(coverage_months, 0)), 1) AS avg_coverage_months
FROM dim_patient_cms
WHERE risk_score IS NOT NULL
GROUP BY 1
ORDER BY patient_count DESC
"""

# ── CMS — Claims ──────────────────────────────────────────────────────────────

CLAIMS_BY_MONTH = """
SELECT
    YEAR(admit_date)  AS yr,
    MONTH(admit_date) AS mo,
    TO_CHAR(admit_date, 'YYYY-MM')  AS month_label,
    COUNT(*)                         AS claim_count,
    ROUND(SUM(payment_amount), 2)    AS total_payment,
    ROUND(AVG(payment_amount), 2)    AS avg_payment
FROM fact_claims
WHERE admit_date IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2
"""

PAYMENT_BUCKETS = """
SELECT
    CASE
        WHEN payment_amount < 500   THEN '< $500'
        WHEN payment_amount < 2000  THEN '$500 – $2K'
        WHEN payment_amount < 5000  THEN '$2K – $5K'
        WHEN payment_amount < 10000 THEN '$5K – $10K'
        ELSE                             '> $10K'
    END        AS payment_bucket,
    COUNT(*)   AS claim_count,
    ROUND(SUM(payment_amount), 2) AS total_payment
FROM fact_claims
WHERE payment_amount IS NOT NULL
GROUP BY 1
ORDER BY MIN(payment_amount)
"""

HIGH_COST_PATIENTS = """
SELECT
    p.patient_id,
    COALESCE(p.age_group,    'Unknown') AS age_group,
    COALESCE(p.gender_label, 'Unknown') AS gender_label,
    CASE
        WHEN p.risk_score <= 2 THEN 'Low'
        WHEN p.risk_score <= 5 THEN 'Medium'
        ELSE 'High'
    END                                  AS risk_tier,
    COALESCE(p.risk_score, 0)            AS risk_score,
    COUNT(c.claim_id)                    AS total_claims,
    ROUND(SUM(c.payment_amount), 2)      AS total_spend,
    ROUND(AVG(c.payment_amount), 2)      AS avg_claim_cost
FROM dim_patient_cms p
JOIN fact_claims c ON p.patient_id = c.patient_id
GROUP BY 1, 2, 3, 4, 5
ORDER BY total_spend DESC
LIMIT 20
"""

# ── CMS — Prescriptions ───────────────────────────────────────────────────────

TOP_DRUGS = """
SELECT
    COALESCE(generic_name, 'Unknown') AS generic_name,
    COALESCE(brand_name,   'Unknown') AS brand_name,
    COUNT(*)                          AS prescription_count,
    ROUND(AVG(days_supply), 1)        AS avg_days_supply,
    ROUND(SUM(total_cost), 2)         AS total_cost,
    ROUND(AVG(patient_pay_amount), 2) AS avg_patient_pay
FROM fact_prescriptions
GROUP BY 1, 2
ORDER BY prescription_count DESC
LIMIT 10
"""

# ── EHR — Encounters ──────────────────────────────────────────────────────────

ENCOUNTER_BY_CLASS = """
SELECT
    COALESCE(encounter_class, 'Unknown') AS encounter_class,
    COUNT(*)                              AS visit_count,
    ROUND(AVG(total_cost), 2)            AS avg_cost,
    ROUND(SUM(total_cost), 2)            AS total_cost,
    SUM(CASE WHEN encounter_class = 'EMER' THEN 1 ELSE 0 END) AS emergency_count
FROM fact_encounters
GROUP BY 1
ORDER BY visit_count DESC
"""

ENCOUNTERS_BY_MONTH = """
SELECT
    YEAR(period_start)                   AS yr,
    MONTH(period_start)                  AS mo,
    TO_CHAR(period_start, 'YYYY-MM')     AS month_label,
    COUNT(*)                             AS encounter_count,
    ROUND(SUM(total_cost), 2)            AS total_cost,
    ROUND(AVG(total_cost), 2)            AS avg_cost
FROM fact_encounters
WHERE period_start IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2
"""

# ── EHR — Medications ─────────────────────────────────────────────────────────

TOP_MEDICATIONS = """
SELECT
    COALESCE(drug_name, 'Unknown') AS drug_name,
    COUNT(*)                        AS prescription_count,
    COUNT(DISTINCT patient_ref)     AS unique_patients,
    SUM(CASE WHEN is_chronic_med = TRUE THEN 1 ELSE 0 END) AS chronic_count
FROM fact_medications
GROUP BY 1
ORDER BY prescription_count DESC
LIMIT 10
"""

MEDICATION_CHRONIC_SPLIT = """
SELECT
    CASE WHEN is_chronic_med = TRUE THEN 'Chronic' ELSE 'Acute / Other' END AS med_type,
    COUNT(*)                    AS count,
    COUNT(DISTINCT patient_ref) AS unique_patients,
    COUNT(DISTINCT drug_name)   AS unique_drugs
FROM fact_medications
GROUP BY 1
"""

# ── EHR — Observations ────────────────────────────────────────────────────────

TOP_OBSERVATIONS = """
SELECT
    COALESCE(loinc_display, loinc_code, 'Unknown') AS observation_name,
    COUNT(*)                                         AS obs_count,
    ROUND(AVG(value), 2)                             AS avg_value,
    COALESCE(unit, '')                               AS unit,
    SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END)  AS abnormal_count,
    ROUND(SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS abnormal_pct
FROM fact_observations
WHERE loinc_display IS NOT NULL OR loinc_code IS NOT NULL
GROUP BY 1, 4
ORDER BY obs_count DESC
LIMIT 10
"""

ABNORMAL_BY_TEST = """
SELECT
    COALESCE(loinc_display, loinc_code, 'Unknown') AS test_name,
    COUNT(*)                                         AS total,
    SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END)  AS abnormal,
    ROUND(SUM(CASE WHEN is_abnormal = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS abnormal_pct
FROM fact_observations
GROUP BY 1
HAVING COUNT(*) > 5
ORDER BY abnormal_pct DESC
LIMIT 10
"""

# ── Diagnostics ───────────────────────────────────────────────────────────────

TABLE_ROW_COUNTS = """
SELECT 'dim_patient_cms'    AS table_name, COUNT(*) AS row_count FROM dim_patient_cms    UNION ALL
SELECT 'fact_claims',                      COUNT(*)              FROM fact_claims         UNION ALL
SELECT 'fact_carrier_claims',              COUNT(*)              FROM fact_carrier_claims UNION ALL
SELECT 'fact_prescriptions',               COUNT(*)              FROM fact_prescriptions  UNION ALL
SELECT 'dim_patient_ehr',                  COUNT(*)              FROM dim_patient_ehr     UNION ALL
SELECT 'fact_encounters',                  COUNT(*)              FROM fact_encounters     UNION ALL
SELECT 'fact_observations',                COUNT(*)              FROM fact_observations   UNION ALL
SELECT 'fact_medications',                 COUNT(*)              FROM fact_medications
ORDER BY row_count DESC
"""

SAMPLE_CMS_PATIENT = "SELECT * FROM dim_patient_cms LIMIT 5"
SAMPLE_FACT_CLAIMS = "SELECT * FROM fact_claims LIMIT 5"
SAMPLE_ENCOUNTERS  = "SELECT * FROM fact_encounters LIMIT 5"
SAMPLE_MEDICATIONS = "SELECT * FROM fact_medications LIMIT 5"
