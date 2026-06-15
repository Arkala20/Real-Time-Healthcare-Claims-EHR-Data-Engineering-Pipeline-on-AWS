-- ============================================================
-- 01_setup.sql
-- Database, schema, and warehouse setup
-- Run this first before anything else
-- ============================================================

-- Create database and schema
CREATE DATABASE IF NOT EXISTS healthcare;
USE DATABASE healthcare;

CREATE SCHEMA IF NOT EXISTS raw;
USE SCHEMA raw;

-- Verify
SHOW DATABASES LIKE 'healthcare';
SHOW SCHEMAS;
