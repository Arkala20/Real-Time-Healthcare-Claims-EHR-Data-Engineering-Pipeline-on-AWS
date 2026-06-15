-- ============================================================
-- 07_pipes_ehr.sql
-- Snowpipe auto-ingest pipes for EHR clean bucket
--
-- After running, do:
--   SHOW PIPES;
--   Copy notification_channel ARN for each pipe
--   → Add S3 Event Notifications on healthcare-ehr-clean
--     using those ARNs (one notification per prefix)
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

CREATE OR REPLACE PIPE pipe_dim_patient_ehr AUTO_INGEST = TRUE AS
    COPY INTO dim_patient_ehr
    FROM @ehr_clean_stage/dim_patient/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_dim_provider_ehr AUTO_INGEST = TRUE AS
    COPY INTO dim_provider_ehr
    FROM @ehr_clean_stage/dim_provider/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_encounters AUTO_INGEST = TRUE AS
    COPY INTO fact_encounters
    FROM @ehr_clean_stage/fact_encounters/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_conditions AUTO_INGEST = TRUE AS
    COPY INTO fact_conditions
    FROM @ehr_clean_stage/fact_conditions/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_observations AUTO_INGEST = TRUE AS
    COPY INTO fact_observations
    FROM @ehr_clean_stage/fact_observations/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_medications AUTO_INGEST = TRUE AS
    COPY INTO fact_medications
    FROM @ehr_clean_stage/fact_medications/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_prescriptions_ehr AUTO_INGEST = TRUE AS
    COPY INTO fact_prescriptions
    FROM @ehr_clean_stage/fact_prescriptions/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

-- Get SQS ARNs for S3 event notifications
SHOW PIPES LIKE 'pipe_%ehr%';
SHOW PIPES LIKE 'pipe_fact_%';

-- Check pipe status
SELECT SYSTEM$PIPE_STATUS('pipe_fact_encounters');
SELECT SYSTEM$PIPE_STATUS('pipe_fact_observations');
SELECT SYSTEM$PIPE_STATUS('pipe_fact_medications');

-- Check load history
SELECT *
FROM TABLE(INFORMATION_SCHEMA.COPY_HISTORY(
    TABLE_NAME => 'FACT_ENCOUNTERS',
    START_TIME => DATEADD(HOUR, -2, CURRENT_TIMESTAMP)
));
