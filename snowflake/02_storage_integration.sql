-- ============================================================
-- 02_storage_integration.sql
-- Snowflake Storage Integration with AWS S3
--
-- Steps:
--   1. Run CREATE STORAGE INTEGRATION below
--   2. Run DESC INTEGRATION to get IAM ARN + External ID
--   3. Go to AWS IAM → Role → snowflake-s3-role → Trust relationships
--      and update with the values from step 2
-- ============================================================

USE DATABASE healthcare;
USE SCHEMA raw;

-- Step 1: Create integration (replace <YOUR_AWS_ACCOUNT_ID>)
CREATE STORAGE INTEGRATION s3_healthcare
    TYPE                      = EXTERNAL_STAGE
    STORAGE_PROVIDER          = 'S3'
    ENABLED                   = TRUE
    STORAGE_AWS_ROLE_ARN      = 'arn:aws:iam::109676855909:role/snowflake-s3-role'
    STORAGE_ALLOWED_LOCATIONS = (
        's3://healthcare-cms-claims-clean/',
        's3://healthcare-ehr-clean/'
    );

-- Step 2: Get Snowflake IAM details — copy STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID
DESC INTEGRATION s3_healthcare;

-- Step 3 (AWS Console — not SQL):
-- IAM → Roles → snowflake-s3-role → Trust relationships → Edit trust policy:
-- {
--   "Version": "2012-10-17",
--   "Statement": [{
--     "Effect": "Allow",
--     "Principal": { "AWS": "<STORAGE_AWS_IAM_USER_ARN>" },
--     "Action": "sts:AssumeRole",
--     "Condition": {
--       "StringEquals": { "sts:ExternalId": "<STORAGE_AWS_EXTERNAL_ID>" }
--     }
--   }]
-- }

-- Verify integration is active
SHOW INTEGRATIONS LIKE 's3_healthcare';
