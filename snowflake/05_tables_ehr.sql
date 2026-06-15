-- ============================================================
-- 05_tables_ehr.sql
-- EHR FHIR table DDL
-- Source: ehr_fhir_etl.py Glue job output
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

-- dim_patient_ehr
-- Source: FHIR Patient resource → process_patients()
CREATE TABLE IF NOT EXISTS dim_patient_ehr (
    patient_key       STRING,
    patient_id        STRING,
    mrn               STRING,
    family_name       STRING,
    given_name        STRING,
    gender            STRING,
    birth_date        STRING,
    address_line      STRING,
    city              STRING,
    state             STRING,
    postal_code       STRING,
    race              STRING,
    ethnicity         STRING,
    birth_date_parsed DATE,
    age               INT,
    age_group         STRING
);

-- dim_provider_ehr
-- Source: FHIR Practitioner resource → process_practitioners()
CREATE TABLE IF NOT EXISTS dim_provider_ehr (
    provider_key  STRING,
    practitioner_id STRING,
    npi           STRING,
    family_name   STRING,
    given_name    STRING,
    specialty_code STRING
);

-- fact_encounters
-- Source: FHIR Encounter resource → process_encounters()
CREATE TABLE IF NOT EXISTS fact_encounters (
    encounter_key            STRING,
    encounter_id             STRING,
    status                   STRING,
    encounter_class          STRING,
    patient_ref              STRING,
    period_start             TIMESTAMP,
    period_end               TIMESTAMP,
    reason_icd10             STRING,
    total_cost               FLOAT,
    encounter_duration_hours FLOAT,
    is_emergency             BOOLEAN,
    visit_year               INT,
    visit_month              INT
);

-- fact_conditions
-- Source: FHIR Condition resource → process_conditions()
CREATE TABLE IF NOT EXISTS fact_conditions (
    condition_key    STRING,
    condition_id     STRING,
    clinical_status  STRING,
    icd10_code       STRING,
    icd10_display    STRING,
    snomed_code      STRING,
    snomed_display   STRING,
    patient_ref      STRING,
    encounter_ref    STRING,
    onset_datetime   TIMESTAMP,
    abatement_datetime TIMESTAMP,
    icd10_description STRING,
    icd10_category   STRING,
    is_resolved      BOOLEAN,
    is_chronic       BOOLEAN
);

-- fact_observations
-- Source: FHIR Observation resource → process_observations()
CREATE TABLE IF NOT EXISTS fact_observations (
    observation_key      STRING,
    observation_id       STRING,
    status               STRING,
    category             STRING,
    loinc_code           STRING,
    loinc_display        STRING,
    patient_ref          STRING,
    encounter_ref        STRING,
    effective_datetime   TIMESTAMP,
    value                FLOAT,
    unit                 STRING,
    ref_low              FLOAT,
    ref_high             FLOAT,
    interpretation_code  STRING,
    is_abnormal          BOOLEAN
);

-- fact_medications
-- Source: FHIR MedicationRequest resource → process_medications()
CREATE TABLE IF NOT EXISTS fact_medications (
    medication_key       STRING,
    medication_request_id STRING,
    status               STRING,
    rxnorm_code          STRING,
    drug_name            STRING,
    patient_ref          STRING,
    encounter_ref        STRING,
    provider_ref         STRING,
    authored_on          TIMESTAMP,
    dosage_text          STRING,
    dose_value           FLOAT,
    dose_unit            STRING,
    drug_name_enriched   STRING,
    drug_class           STRING,
    is_chronic_med       BOOLEAN
);

-- Verify
SHOW TABLES LIKE '%ehr%';
SHOW TABLES LIKE 'fact_%';
