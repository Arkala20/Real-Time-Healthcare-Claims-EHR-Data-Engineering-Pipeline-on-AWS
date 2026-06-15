-- ============================================================
-- 03_stages.sql
-- Parquet file format + S3 external stages
-- Run after 02_storage_integration.sql
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

-- Parquet file format (Snappy compressed, as written by Glue)
CREATE OR REPLACE FILE FORMAT parquet_fmt
    TYPE             = PARQUET
    SNAPPY_COMPRESSION = TRUE;

-- Stage pointing to CMS clean bucket
CREATE OR REPLACE STAGE cms_clean_stage
    URL                 = 's3://healthcare-cms-claims-clean/'
    STORAGE_INTEGRATION = s3_healthcare
    FILE_FORMAT         = parquet_fmt;

-- Stage pointing to EHR clean bucket
CREATE OR REPLACE STAGE ehr_clean_stage
    URL                 = 's3://healthcare-ehr-clean/'
    STORAGE_INTEGRATION = s3_healthcare
    FILE_FORMAT         = parquet_fmt;

-- Verify stages
SHOW STAGES;

-- Test that Snowflake can list files in each stage
LIST @cms_clean_stage;
LIST @ehr_clean_stage;
