-- ============================================================
-- 06_pipes_cms.sql
-- Snowpipe auto-ingest pipes for CMS clean bucket
--
-- After running, do:
--   SHOW PIPES;
--   Copy notification_channel ARN for each pipe
--   → Add S3 Event Notifications on healthcare-cms-claims-clean
--     using those ARNs (one notification per prefix)
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

CREATE OR REPLACE PIPE pipe_dim_patient_cms AUTO_INGEST = TRUE AS
    COPY INTO dim_patient_cms
    FROM @cms_clean_stage/dim_patient/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_dim_provider_cms AUTO_INGEST = TRUE AS
    COPY INTO dim_provider_cms
    FROM @cms_clean_stage/dim_provider/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_claims AUTO_INGEST = TRUE AS
    COPY INTO fact_claims
    FROM @cms_clean_stage/fact_claims/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_carrier AUTO_INGEST = TRUE AS
    COPY INTO fact_carrier_claims
    FROM @cms_clean_stage/fact_carrier_claims/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

CREATE OR REPLACE PIPE pipe_fact_prescriptions AUTO_INGEST = TRUE AS
    COPY INTO fact_prescriptions
    FROM @cms_clean_stage/fact_prescriptions/
    FILE_FORMAT = parquet_fmt
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

-- Get SQS ARNs for S3 event notifications
SHOW PIPES LIKE 'pipe_%cms%';
SHOW PIPES LIKE 'pipe_fact_%';

-- Check pipe status after S3 events are wired up
SELECT SYSTEM$PIPE_STATUS('pipe_dim_patient_cms');
SELECT SYSTEM$PIPE_STATUS('pipe_fact_claims');
SELECT SYSTEM$PIPE_STATUS('pipe_fact_prescriptions');

-- Check load history (run after Glue job completes)
SELECT *
FROM TABLE(INFORMATION_SCHEMA.COPY_HISTORY(
    TABLE_NAME => 'FACT_CLAIMS',
    START_TIME => DATEADD(HOUR, -2, CURRENT_TIMESTAMP)
));
