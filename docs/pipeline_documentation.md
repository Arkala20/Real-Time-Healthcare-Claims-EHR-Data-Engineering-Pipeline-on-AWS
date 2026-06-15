# Real-Time Healthcare Claims & EHR Data Engineering Pipeline on AWS

**Authors:** Thrivikram Kotharu, Arkala  
**Date:** June 2026  
**Stack:** AWS Lambda · AWS Glue · Amazon S3 · Snowflake · Streamlit

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Data Sources & Schema](#3-data-sources--schema)
4. [AWS Infrastructure Setup](#4-aws-infrastructure-setup)
5. [Data Ingestion — Lambda Functions](#5-data-ingestion--lambda-functions)
6. [API Gateway — Trigger Endpoint](#6-api-gateway--trigger-endpoint)
7. [Raw Data Storage — Amazon S3](#7-raw-data-storage--amazon-s3)
8. [ETL — AWS Glue](#8-etl--aws-glue)
9. [Clean Data Storage — S3 Clean Buckets](#9-clean-data-storage--s3-clean-buckets)
10. [Snowflake — Data Warehouse](#10-snowflake--data-warehouse)
11. [Snowpipe — Auto-Ingest](#11-snowpipe--auto-ingest)
12. [Streamlit Analytics Dashboard](#12-streamlit-analytics-dashboard)
13. [CI/CD — GitHub Actions](#13-cicd--github-actions)
14. [End-to-End Data Flow](#14-end-to-end-data-flow)

---

## 1. Project Overview

This project builds a **real-time healthcare data engineering pipeline** that:

- Generates synthetic **CMS Claims** (Medicare/Medicaid style) and **FHIR R4 EHR** (Electronic Health Records) data
- Ingests the raw data into **Amazon S3** via AWS Lambda
- Transforms and cleans the data using **AWS Glue PySpark** ETL jobs
- Loads the clean Parquet data into **Snowflake** automatically via **Snowpipe**
- Provides an interactive **Streamlit** analytics dashboard for exploring the data

The pipeline is fully event-driven: a single API call triggers data generation, which cascades through S3 → Glue → Snowflake with no manual intervention.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER / API CALL                             │
│              POST /trigger  (API Gateway HTTP API)                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │   Lambda: api-trigger│
                    │  (async invoke both) │
                    └──────┬──────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
┌──────────────────────┐   ┌──────────────────────┐
│ Lambda: cms-claims-  │   │ Lambda: fhir-ehr-    │
│    generator         │   │    generator          │
│  Generates CMS CSV   │   │  Generates FHIR R4   │
│  (7 entity types)    │   │  Bundle JSON          │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────┐
│  S3: cms-claims-raw  │   │  S3: ehr-raw          │
│  year=/month=/day=/  │   │  fhir/*.json          │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────┐
│ Glue: cms-claims-etl │   │ Glue: ehr-fhir-etl   │
│ PySpark transform    │   │ PySpark FHIR flatten  │
│ → Parquet output     │   │ → Parquet output      │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────┐
│ S3: cms-claims-clean │   │ S3: ehr-clean         │
│ dim_patient/         │   │ dim_patient/          │
│ fact_claims/  etc.   │   │ fact_encounters/ etc. │
└──────────┬───────────┘   └──────────┬───────────┘
           │   S3 ObjectCreated event  │
           └────────────┬─────────────┘
                        │ SQS notification
                        ▼
           ┌────────────────────────┐
           │   Snowflake Snowpipe   │
           │   (AUTO_INGEST=TRUE)   │
           └────────────┬───────────┘
                        │
                        ▼
           ┌────────────────────────┐
           │   Snowflake Tables     │
           │   DATABASE: healthcare  │
           │   SCHEMA: raw          │
           └────────────┬───────────┘
                        │
                        ▼
           ┌────────────────────────┐
           │   Streamlit Dashboard  │
           │   (snowflake-connector)│
           └────────────────────────┘
```

---

## 3. Data Sources & Schema

### 3.1 CMS Claims Data (Synthetic DE-SynPUF)

The **CMS DE-SynPUF** (Synthetic Public Use File) schema is based on real Medicare claims structure. We generate 7 entity types per batch:

| Entity | Description | Key Fields |
|---|---|---|
| `beneficiary_summary` | Patient demographics + chronic conditions | DESYNPUF_ID, birth date, gender, race, 9 chronic flags |
| `providers` | Provider directory | PROVIDER_ID, NPI, specialty, state |
| `inpatient_claims` | Hospital stays | CLM_ID, admit/discharge dates, DRG code, payment |
| `outpatient_claims` | Outpatient visits | CLM_ID, service dates, HCPCS codes, payment |
| `carrier_claims` | Physician/carrier claims | CLM_ID, performing NPI, service date, payment |
| `prescription_drug_events` | Pharmacy fills | PDE_ID, drug code, generic/brand name, days supply, cost |
| `diagnosis_codes` | ICD-10 reference codes | ICD10 code + description |

**Medical coding standards used:**
- **ICD-10** — International Classification of Diseases (diagnosis codes)
- **HCPCS** — Healthcare Common Procedure Coding System
- **DRG** — Diagnosis-Related Groups (inpatient classification)
- **NDC** — National Drug Codes

---

### 3.2 FHIR R4 EHR Data (Synthetic Bundles)

**FHIR** (Fast Healthcare Interoperability Resources) R4 is the modern standard for healthcare data exchange. Each patient generates a **Bundle** containing 15 linked resources:

| FHIR Resource | Description | Key Fields |
|---|---|---|
| `Patient` | Patient demographics | id, name, gender, birthDate, address, race, ethnicity |
| `Practitioner` | Healthcare provider | id, NPI, name, qualification/specialty |
| `Encounter` | Clinical visit | id, class (AMB/EMER/IMP), period, total cost |
| `Condition` | Diagnoses | id, ICD-10 code, SNOMED code, clinical status, chronic flag |
| `Observation` | Lab results & vitals | id, LOINC code, value, unit, reference range, abnormal flag |
| `MedicationRequest` | Prescriptions | id, RxNorm code, drug name, dosage, chronic flag |
| `Procedure` | Performed procedures | id, CPT code, SNOMED code, performed date, cost |
| `AllergyIntolerance` | Allergies | id, substance, reaction, severity |
| `Immunization` | Vaccines | id, CVX code, vaccine name, occurrence date |

**Medical coding standards used:**
- **ICD-10** — Diagnoses
- **SNOMED-CT** — Clinical terminology
- **LOINC** — Lab tests and observations
- **RxNorm** — Medications
- **CVX** — Vaccines
- **CPT** — Procedures

---

## 4. AWS Infrastructure Setup

All AWS services were created **manually via the AWS Console** (no CDK or Terraform). The region used throughout is **us-east-2 (Ohio)**.

### IAM Roles Created

| Role | Used By | Key Permissions |
|---|---|---|
| `healthcare-lambda-role` | All Lambda functions | S3 read/write, Lambda invoke, CloudWatch logs |
| `healthcare-glue-role` | Glue ETL jobs | S3 read/write (both raw + clean buckets), CloudWatch logs |
| `snowflake-s3-role` | Snowflake Storage Integration | S3 GetObject, ListBucket on clean buckets |

### S3 Buckets

| Bucket | Purpose |
|---|---|
| `healthcare-cms-claims-raw` | Raw CMS CSV files + Glue scripts |
| `healthcare-ehr-raw` | Raw FHIR R4 JSON bundles |
| `healthcare-cms-claims-clean` | Cleaned CMS Parquet files |
| `healthcare-ehr-clean` | Cleaned EHR Parquet files |

---

## 5. Data Ingestion — Lambda Functions

Three Lambda functions handle data generation and orchestration, all using **Python 3.11** and the `handler.handler` entry point.

### Lambda 1: `cms-claims-generator`

Generates synthetic CMS Claims data and uploads to S3.

- **Trigger:** Async invocation from `api-trigger`
- **Output:** 7 CSV files per invocation under `year=YYYY/month=MM/day=DD/`
- **Key environment variable:** `RAW_CMS_BUCKET`, `RECORDS_PER_BATCH` (default 500)
- **Libraries:** `boto3`, `faker`, `random`

**S3 key pattern:**
```
year=2026/month=06/day=15/beneficiary_summary_<uuid>.csv
year=2026/month=06/day=15/inpatient_claims_<uuid>.csv
year=2026/month=06/day=15/carrier_claims_<uuid>.csv
...
```

---

### Lambda 2: `fhir-ehr-generator`

Generates synthetic FHIR R4 Bundle JSON files and uploads to S3.

- **Trigger:** Async invocation from `api-trigger`
- **Output:** One JSON file per patient under `fhir/`
- **Key environment variable:** `RAW_EHR_BUCKET`, `PATIENTS_PER_BATCH` (default 200)
- **FHIR structure:** Each file is a `Bundle` resource containing all 9 resource types for one patient

---

### Lambda 3: `api-trigger`

Entry point exposed via API Gateway. Asynchronously invokes both generators in parallel.

- **Trigger:** HTTP POST via API Gateway
- **Invocation type:** `InvocationType=Event` (fire and forget — both generators run in parallel)
- **Environment variables:** `CMS_LAMBDA_NAME`, `FHIR_LAMBDA_NAME`

![Lambda Functions](../images/AWS/lambda function.jpeg)

---

## 6. API Gateway — Trigger Endpoint

An **HTTP API** (API Gateway v2) exposes a single POST endpoint that kicks off the entire pipeline.

**Endpoint:**
```
POST https://u0zg8lmc1c.execute-api.us-east-2.amazonaws.com/dev/trigger
```

**Request body:**
```json
{
  "records_per_batch": 500,
  "patients_per_batch": 200
}
```

**Response:**
```json
{
  "message": "Data generation triggered successfully.",
  "batchId": "2c8b7229-03c8-4748-b8c0-6eda01032cd0"
}
```

**How to call it (PowerShell):**
```powershell
Invoke-RestMethod `
  -Uri "https://u0zg8lmc1c.execute-api.us-east-2.amazonaws.com/dev/trigger" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"records_per_batch": 500, "patients_per_batch": 200}'
```

![API Gateway](../images/AWS/api gateway.jpeg)

![API Gateway Flow](../images/AWS/Api gateway image representation.jpeg)

---

## 7. Raw Data Storage — Amazon S3

Raw data lands in two S3 buckets with **date-partitioned prefixes** so Glue can process data by date range.

### CMS Raw Bucket Structure

```
healthcare-cms-claims-raw/
├── glue-scripts/
│   ├── cms_claims_etl.py
│   └── ehr_fhir_etl.py
├── year=2026/
│   └── month=06/
│       └── day=15/
│           ├── beneficiary_summary_<uuid>.csv
│           ├── providers_<uuid>.csv
│           ├── inpatient_claims_<uuid>.csv
│           ├── outpatient_claims_<uuid>.csv
│           ├── carrier_claims_<uuid>.csv
│           ├── prescription_drug_events_<uuid>.csv
│           └── diagnosis_codes_<uuid>.csv
```

### EHR Raw Bucket Structure

```
healthcare-ehr-raw/
└── fhir/
    ├── patient_<uuid>.json
    ├── patient_<uuid>.json
    └── ...
```

![S3 Buckets](../images/AWS/S3.jpeg)

![S3 Folder Structure](../images/AWS/S3-1.jpeg)

![S3 Folder Names](../images/AWS/s3 folder names.jpeg)

![S3 Folder Names Detail](../images/AWS/s3 folder names 2.jpeg)

---

## 8. ETL — AWS Glue

Two **AWS Glue 4.0** PySpark ETL jobs transform raw data into analytics-ready Parquet format.

### 8.1 CMS Claims ETL (`cms-claims-etl`)

**Script:** `src/glue/cms_claims_etl.py`  
**Runtime:** Glue 4.0, PySpark 3.3, Python 3.10  
**Input:** Raw CSVs from `healthcare-cms-claims-raw`  
**Output:** Parquet to `healthcare-cms-claims-clean`

**Job Parameters:**
```
--RAW_CMS_BUCKET    healthcare-cms-claims-raw
--CLEAN_CMS_BUCKET  healthcare-cms-claims-clean
```

**Transformations applied (9 groups):**

| Group | What it does |
|---|---|
| 1. Column rename | Maps raw CMS column names (e.g. `DESYNPUF_ID`) to clean names (`patient_id`) |
| 2. Type casting | Converts date strings (`yyyyMMdd`) to `DATE`, amounts to `DECIMAL(12,2)` |
| 3. Code decoding | Maps numeric gender/race codes to labels (`1` → `Male`, `2` → `White`) |
| 4. Null handling | Fills amount nulls with `0.0`, flags missing birth dates, sets `is_deceased` |
| 5. Deduplication | `dropDuplicates` on business keys (`patient_id`, `claim_id`, etc.) |
| 6. Date derivation | Extracts `year`, `quarter`, `month`, `week_of_year`, `date_key` from date columns |
| 7. Financial cleanup | Clips negative amounts to 0, rounds to 2dp, flags `is_high_cost` at 99th percentile |
| 8. Surrogate keys | SHA-256 hash of business key → `patient_key`, `claim_key`, etc. |
| 9. Risk flags | Sums 9 chronic condition flags → `risk_score`, `risk_tier` (Low/Medium/High) |

**Output tables:**

| Parquet Prefix | Description | Rows (sample) |
|---|---|---|
| `dim_patient/` | Patient dimension | 3,000 |
| `dim_provider/` | Provider dimension | 300 |
| `fact_claims/` | Inpatient + outpatient claims | 6,000 |
| `fact_carrier_claims/` | Carrier/physician claims | 3,000 |
| `fact_prescriptions/` | Drug events | 3,000 |

---

### 8.2 EHR FHIR ETL (`ehr-fhir-etl`)

**Script:** `src/glue/ehr_fhir_etl.py`  
**Runtime:** Glue 4.0, PySpark 3.3, Python 3.10  
**Input:** FHIR Bundle JSONs from `healthcare-ehr-raw`  
**Output:** Parquet to `healthcare-ehr-clean`

**Job Parameters:**
```
--RAW_EHR_BUCKET    healthcare-ehr-raw
--CLEAN_EHR_BUCKET  healthcare-ehr-clean
```

**Key challenge — FHIR Schema Conflicts:**

FHIR bundles contain mixed resource types in a single JSON array. Spark infers a single merged schema across all resources, causing type conflicts. Three specific conflicts were resolved:

1. **`name` field conflict** — `Organization.name` is a plain string; `Patient.name` is an array of structs. Fixed using `from_json()` with an explicit schema after filtering by `resourceType`.

2. **`valueMoney` vs `valueDecimal`** — The generator uses `valueMoney: {value, currency}` for costs but original ETL looked for `valueDecimal`. Fixed by changing to `extension[0]["valueMoney"]["value"]`.

3. **`category` field conflict** — `AllergyIntolerance.category` is `["food"]` (string array); `Observation.category` is `[{coding:[...]}]` (struct array). Spark infers `StringType`. Fixed using `get_json_object()` instead of struct access.

**Output tables:**

| Parquet Prefix | Description | Rows (sample) |
|---|---|---|
| `dim_patient/` | EHR patient dimension | 532 |
| `dim_provider/` | Practitioner dimension | ~50 |
| `fact_encounters/` | Clinical visits | 532 |
| `fact_conditions/` | Diagnoses | 0* |
| `fact_observations/` | Lab results & vitals | 1,596 |
| `fact_medications/` | Medication requests | 1,064 |

> *`fact_conditions` currently has 0 rows in this sample batch — this can vary by batch size.

![Glue Job Runs](../images/AWS/Glue runs.jpeg)

![CMS Glue Runs](../images/AWS/cms glue runs.jpeg)

![Glue Logs](../images/AWS/glue logs.jpeg)

---

## 9. Clean Data Storage — S3 Clean Buckets

After the Glue job completes, cleaned **Parquet** files land in the clean S3 buckets.

**Why Parquet?**
- Columnar format — fast for analytical queries
- Snappy compression — ~75% smaller than CSV
- Type-preserving — dates, decimals, booleans all stored correctly
- Native support in both Spark and Snowflake

**Clean bucket structure:**
```
healthcare-cms-claims-clean/
├── dim_patient/
│   └── part-00000-*.parquet
├── dim_provider/
├── fact_claims/
├── fact_carrier_claims/
└── fact_prescriptions/

healthcare-ehr-clean/
├── dim_patient/
├── dim_provider/
├── fact_encounters/
├── fact_conditions/
├── fact_observations/
└── fact_medications/
```

---

## 10. Snowflake — Data Warehouse

### 10.1 Account Details

| Field | Value |
|---|---|
| Account Identifier | `ABCIDUX-GP18792` |
| Organization | `ABCIDUX` |
| Account Name | `GP18792` |
| Login Name | `ARKALA` |
| Warehouse | `COMPUTE_WH` (X-Small) |
| Database | `healthcare` |
| Schema | `raw` |

### 10.2 Database Objects

**CMS Tables:**

| Table | Source | Rows |
|---|---|---|
| `dim_patient_cms` | beneficiary_summary | 3,000 |
| `dim_provider_cms` | providers | 300 |
| `fact_claims` | inpatient + outpatient | 6,000 |
| `fact_carrier_claims` | carrier_claims | 3,000 |
| `fact_prescriptions` | prescription_drug_events | 3,000 |

**EHR Tables:**

| Table | Source | Rows |
|---|---|---|
| `dim_patient_ehr` | FHIR Patient | 532 |
| `dim_provider_ehr` | FHIR Practitioner | ~50 |
| `fact_encounters` | FHIR Encounter | 532 |
| `fact_conditions` | FHIR Condition | 0* |
| `fact_observations` | FHIR Observation | 1,596 |
| `fact_medications` | FHIR MedicationRequest | 1,064 |

### 10.3 Storage Integration

A **Snowflake Storage Integration** (`s3_healthcare`) connects Snowflake to both clean S3 buckets using an IAM role trust relationship. This avoids storing AWS credentials in Snowflake.

```sql
CREATE STORAGE INTEGRATION s3_healthcare
    TYPE                      = EXTERNAL_STAGE
    STORAGE_PROVIDER          = 'S3'
    ENABLED                   = TRUE
    STORAGE_AWS_ROLE_ARN      = 'arn:aws:iam::109676855909:role/snowflake-s3-role'
    STORAGE_ALLOWED_LOCATIONS = (
        's3://healthcare-cms-claims-clean/',
        's3://healthcare-ehr-clean/'
    );
```

### 10.4 External Stages

Two stages point to the clean S3 buckets using the storage integration:

```sql
CREATE OR REPLACE STAGE cms_clean_stage
    URL = 's3://healthcare-cms-claims-clean/'
    STORAGE_INTEGRATION = s3_healthcare
    FILE_FORMAT = parquet_fmt;

CREATE OR REPLACE STAGE ehr_clean_stage
    URL = 's3://healthcare-ehr-clean/'
    STORAGE_INTEGRATION = s3_healthcare
    FILE_FORMAT = parquet_fmt;
```

![Snowflake Setup](../images/snowflake/snowflake.png)

---

## 11. Snowpipe — Auto-Ingest

**Snowpipe** automatically loads new Parquet files into Snowflake tables as soon as they appear in S3 — no manual COPY INTO needed.

### How It Works

```
Glue writes Parquet to S3 clean bucket
          ↓
S3 fires ObjectCreated event → SQS queue (owned by Snowflake)
          ↓  (~60 seconds)
Snowpipe reads SQS message, loads new files into target table
          ↓
Data available to query in Snowflake
```

### Pipes Created

**CMS Pipes (5):**

| Pipe | Source Prefix | Target Table |
|---|---|---|
| `pipe_dim_patient_cms` | `cms_clean_stage/dim_patient/` | `dim_patient_cms` |
| `pipe_dim_provider_cms` | `cms_clean_stage/dim_provider/` | `dim_provider_cms` |
| `pipe_fact_claims` | `cms_clean_stage/fact_claims/` | `fact_claims` |
| `pipe_fact_carrier` | `cms_clean_stage/fact_carrier_claims/` | `fact_carrier_claims` |
| `pipe_fact_prescriptions` | `cms_clean_stage/fact_prescriptions/` | `fact_prescriptions` |

**EHR Pipes (6):**

| Pipe | Source Prefix | Target Table |
|---|---|---|
| `pipe_dim_patient_ehr` | `ehr_clean_stage/dim_patient/` | `dim_patient_ehr` |
| `pipe_dim_provider_ehr` | `ehr_clean_stage/dim_provider/` | `dim_provider_ehr` |
| `pipe_fact_encounters` | `ehr_clean_stage/fact_encounters/` | `fact_encounters` |
| `pipe_fact_conditions` | `ehr_clean_stage/fact_conditions/` | `fact_conditions` |
| `pipe_fact_observations` | `ehr_clean_stage/fact_observations/` | `fact_observations` |
| `pipe_fact_medications` | `ehr_clean_stage/fact_medications/` | `fact_medications` |

### S3 Event Notifications

Each clean S3 bucket has **prefix-level event notifications** pointing to the Snowpipe SQS queue:

| Bucket | Prefix | SQS ARN |
|---|---|---|
| `healthcare-cms-claims-clean` | `dim_patient/` | `arn:aws:sqs:us-east-2:...:sf-snowpipe-...` |
| `healthcare-cms-claims-clean` | `fact_claims/` | same ARN |
| `healthcare-ehr-clean` | `dim_patient/` | same ARN |
| `healthcare-ehr-clean` | `fact_encounters/` | same ARN |
| … | … | … |

> All pipes share the same SQS ARN — Snowflake routes events internally based on the stage path.

### Verification Queries

```sql
-- Check all pipes are running
SHOW PIPES;

-- Check load history
SELECT * FROM TABLE(INFORMATION_SCHEMA.COPY_HISTORY(
    TABLE_NAME => 'FACT_CLAIMS',
    START_TIME => DATEADD(HOUR, -2, CURRENT_TIMESTAMP)
));
```

---

## 12. Streamlit Analytics Dashboard

An interactive **Streamlit** dashboard connects directly to Snowflake and renders charts from live data.

### Setup

```bash
cd streamlit_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

**Connection via `.env`:**
```
SNOWFLAKE_ACCOUNT=ABCIDUX-GP18792
SNOWFLAKE_USER=Arkala
SNOWFLAKE_PASSWORD=<password>
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=healthcare
SNOWFLAKE_SCHEMA=raw
```

### Dashboard Tabs

#### Overview Tab

Displays 8 pipeline KPI metrics at the top, followed by:
- **Patient Risk Distribution** — pie chart derived from `risk_score` (Low / Medium / High)
- **Patient Age Group** — bar chart with average risk score as color scale
- **Gender × Race Breakdown** — grouped bar chart

![Dashboard Overview](../images/streamlit%20dashboard/streamlitdashboard1.png)

---

#### CMS Claims Tab

- **Claims by Month** — bar (claim count) + line (total payment) using `YEAR/MONTH(admit_date)`
- **Payment Amount Buckets** — bar chart of claim count by payment range (< $500, $500–$2K, etc.)
- **Top 10 Prescribed Drugs** — horizontal bar colored by total cost
- **High-Cost Patients Scatter** — bubble chart: risk score vs total spend, sized by claim count

![CMS Claims Dashboard](../images/streamlit%20dashboard/streamlitdashboard2.png)

---

#### EHR Tab

- **Encounter Class Breakdown** — pie chart (AMB / EMER / IMP) + avg cost bar
- **Encounters by Month** — bar + line using `YEAR/MONTH(period_start)`
- **Top 10 Medications** — horizontal bar colored by chronic medication count
- **Chronic vs Acute Medication Split** — donut pie chart
- **Lab Tests by Volume** — horizontal bar colored by abnormal percentage
- **Abnormal Rate by Test** — horizontal bar showing % abnormal per lab test

![EHR Dashboard](../images/streamlit%20dashboard/streamlitdashboard3.png)

![EHR Dashboard Detail](../images/streamlit%20dashboard/streamlitdashboard4.png)

---

#### Diagnostics Tab

- **Row Counts per Table** — bar chart showing how many rows Snowpipe has loaded into each table
- **Sample Data Viewer** — dropdown to pick any table and preview 5 rows
- **Null Detection** — automatically highlights which columns have null values in the sample

---

### Key Technical Notes

**Why YEAR/MONTH derived from dates instead of partition columns?**

Spark's `partitionBy()` writes partition column values into the S3 folder path (e.g., `fact_claims/year=2026/claim_type=inpatient/`) and **removes them from the Parquet file schema**. Snowpipe reads the raw Parquet files without path inference, so those columns arrive as NULL in Snowflake. The dashboard derives `year`/`month` directly from `admit_date` and `period_start` as a workaround.

---

## 13. CI/CD — GitHub Actions

A GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically deploys code on every push to `main`.

### What It Deploys

**Job 1 — `deploy-lambdas`** (runs in parallel with Job 2):
- Packages and deploys all 3 Lambda functions with `aws lambda update-function-code`
- Creates the function if it doesn't exist yet

**Job 2 — `deploy-glue`**:
- Uploads `cms_claims_etl.py` and `ehr_fhir_etl.py` to `s3://healthcare-cms-claims-raw/glue-scripts/`
- Updates the Glue job script location via `aws glue update-job`

### Required GitHub Secrets / Variables

| Type | Name | Value |
|---|---|---|
| Secret | `AWS_ACCESS_KEY_ID` | IAM user access key |
| Secret | `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| Secret | `LAMBDA_ROLE_ARN` | `arn:aws:iam::109676855909:role/healthcare-lambda-role` |
| Variable | `CMS_RAW_BUCKET` | `healthcare-cms-claims-raw` |
| Variable | `EHR_RAW_BUCKET` | `healthcare-ehr-raw` |
| Variable | `CMS_LAMBDA_NAME` | `cms-claims-generator` |
| Variable | `FHIR_LAMBDA_NAME` | `fhir-ehr-generator` |
| Variable | `TRIGGER_LAMBDA_NAME` | `api-trigger` |
| Variable | `CMS_GLUE_JOB` | `cms-claims-etl` |
| Variable | `EHR_GLUE_JOB` | `ehr-fhir-etl` |

---

## 14. End-to-End Data Flow

Here is the complete journey of a single API trigger call:

```
1. User calls POST /trigger
   └─ API Gateway routes to api-trigger Lambda

2. api-trigger Lambda
   ├─ Async invokes cms-claims-generator
   └─ Async invokes fhir-ehr-generator
      (both run in parallel, response returned immediately)

3a. cms-claims-generator
    ├─ Generates 500 beneficiaries, 50 providers, 500 inpatient claims, etc.
    └─ Uploads 7 CSV files to:
       s3://healthcare-cms-claims-raw/year=2026/month=06/day=15/

3b. fhir-ehr-generator
    ├─ Generates 200 FHIR R4 Bundle JSONs (200 patients × 15 resources each)
    └─ Uploads to: s3://healthcare-ehr-raw/fhir/

4. Glue jobs run (manually triggered or scheduled)
   ├─ cms-claims-etl: reads CSVs → 9 transformation groups → writes 5 Parquet tables
   └─ ehr-fhir-etl: reads JSON bundles → flattens FHIR resources → writes 9 Parquet tables

5. Glue writes Parquet to clean S3 buckets
   ├─ s3://healthcare-cms-claims-clean/dim_patient/part-*.parquet
   └─ s3://healthcare-ehr-clean/fact_encounters/part-*.parquet

6. S3 fires ObjectCreated events → Snowflake SQS queues (~60 sec latency)

7. Snowpipe loads Parquet files into Snowflake tables
   └─ MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE maps Parquet columns to table columns

8. Data available in Snowflake → Streamlit dashboard queries and renders charts
```

---

## Project File Structure

```
Real-Time-Healthcare-Claims-EHR-Data-Engineering-Pipeline-on-AWS/
├── .github/
│   └── workflows/
│       └── deploy.yml              ← CI/CD pipeline
├── src/
│   ├── lambdas/
│   │   ├── api_trigger/            ← Lambda 3: HTTP entry point
│   │   ├── cms_claims_generator/   ← Lambda 1: CMS data generator
│   │   └── fhir_generator/         ← Lambda 2: FHIR data generator
│   └── glue/
│       ├── cms_claims_etl.py       ← PySpark CMS ETL
│       └── ehr_fhir_etl.py         ← PySpark FHIR ETL
├── streamlit_app/
│   ├── app.py                      ← Streamlit dashboard
│   ├── queries.py                  ← All SQL queries
│   ├── requirements.txt
│   └── .env                        ← Snowflake credentials (gitignored)
├── snowflake/
│   ├── 01_setup.sql                ← Database + schema
│   ├── 02_storage_integration.sql  ← S3 integration
│   ├── 03_stages.sql               ← File format + stages
│   ├── 04_tables_cms.sql           ← CMS table DDL
│   ├── 05_tables_ehr.sql           ← EHR table DDL
│   ├── 06_pipes_cms.sql            ← CMS Snowpipes
│   ├── 07_pipes_ehr.sql            ← EHR Snowpipes
│   └── 08_analytics_queries.sql    ← Dashboard SQL
├── docs/
│   └── pipeline_documentation.md   ← This document
└── images/
    ├── AWS/                        ← AWS console screenshots
    ├── snowflake/                  ← Snowflake screenshots
    └── streamlit dashboard/        ← Dashboard screenshots
```
