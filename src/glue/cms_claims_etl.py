"""
CMS Claims PySpark ETL job — Glue 4.0 (PySpark 3.3, Python 3.10).

Reads raw CMS Claims CSV files from S3, applies all transformations defined
in the plan, and writes analytics-ready Parquet files to the clean S3 bucket.

Source tables processed:
  - beneficiary_summary      → dim_patient
  - providers                → dim_provider
  - inpatient_claims         → fact_claims (merged with outpatient)
  - outpatient_claims        → fact_claims (merged with inpatient)
  - carrier_claims           → fact_carrier_claims
  - prescription_drug_events → fact_prescriptions

Job args:
  --RAW_CMS_BUCKET   S3 bucket name for raw CSV input
  --CLEAN_CMS_BUCKET S3 bucket name for clean Parquet output
  --JOB_NAME         Glue job name (injected by Glue runtime)
"""

import sys
from functools import reduce

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

_CHRONIC_COLS = [
    "chronic_diabetes", "chronic_kidney", "chronic_cancer", "chronic_copd",
    "chronic_depression", "chronic_ischemic_heart", "chronic_osteoporosis",
    "chronic_ra_oa", "chronic_stroke",
]


# ---------------------------------------------------------------------------
# Glue job bootstrap
# ---------------------------------------------------------------------------

def init_glue_job() -> tuple[GlueContext, Job, dict]:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "RAW_CMS_BUCKET", "CLEAN_CMS_BUCKET"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    return glue_context, job, args


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_csv(spark: SparkSession, bucket: str, prefix: str) -> DataFrame:
    return (
        spark.read
        .option("header", "true")
        .option("inferSchema", "true")
        .csv(f"s3://{bucket}/{prefix}*.csv")
    )


# ---------------------------------------------------------------------------
# Transformation group 1: Column renaming
# ---------------------------------------------------------------------------

def rename_beneficiary_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "DESYNPUF_ID":             "patient_id",
        "BENE_BIRTH_DT":           "birth_date",
        "BENE_DEATH_DT":           "death_date",
        "BENE_SEX_IDENT_CD":       "gender_code",
        "BENE_RACE_CD":            "race_code",
        "BENE_STATE_CD":           "state_code",
        "BENE_COUNTY_CD":          "county_code",
        "PLAN_TYPE":               "plan_type",
        "SP_DIABETES":             "chronic_diabetes",
        "SP_CHRNKIDN":             "chronic_kidney",
        "SP_CNCR":                 "chronic_cancer",
        "SP_COPD":                 "chronic_copd",
        "SP_DEPRESSN":             "chronic_depression",
        "SP_ISCHMCHT":             "chronic_ischemic_heart",
        "SP_OSTEOPRS":             "chronic_osteoporosis",
        "SP_RA_OA":                "chronic_ra_oa",
        "SP_STRKETIA":             "chronic_stroke",
        "BENE_HI_CVRAGE_TOT_MONS": "coverage_months",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


def rename_provider_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "PROVIDER_ID":            "provider_id",
        "NPI":                    "npi",
        "PRVDR_SPCLTY":           "specialty_code",
        "PRVDR_STATE_CD":         "state_code",
        "ORG_NAME":               "org_name",
        "PRVDR_FIRST_NAME":       "first_name",
        "PRVDR_LAST_NAME":        "last_name",
        "PRVDR_GRP_PRTCPTN_FLAG": "group_participation_flag",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


def rename_inpatient_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "CLM_ID":                         "claim_id",
        "DESYNPUF_ID":                    "patient_id",
        "PROVIDER_ID":                    "provider_id",
        "CLM_FROM_DT":                    "admit_date",
        "CLM_THRU_DT":                    "discharge_date",
        "AT_PHYSN_NPI":                   "attending_npi",
        "OP_PHYSN_NPI":                   "operating_npi",
        "ICD_DGNS_CD1":                   "diag_code_1",
        "ICD_DGNS_CD2":                   "diag_code_2",
        "ICD_DGNS_CD3":                   "diag_code_3",
        "ICD_DGNS_CD4":                   "diag_code_4",
        "ICD_DGNS_CD5":                   "diag_code_5",
        "ICD_DGNS_CD6":                   "diag_code_6",
        "ICD_DGNS_CD7":                   "diag_code_7",
        "ICD_DGNS_CD8":                   "diag_code_8",
        "ICD_DGNS_CD9":                   "diag_code_9",
        "ICD_DGNS_CD10":                  "diag_code_10",
        "ICD_PRCDR_CD1":                  "procedure_code_1",
        "ICD_PRCDR_CD2":                  "procedure_code_2",
        "ICD_PRCDR_CD3":                  "procedure_code_3",
        "ICD_PRCDR_CD4":                  "procedure_code_4",
        "ICD_PRCDR_CD5":                  "procedure_code_5",
        "ICD_PRCDR_CD6":                  "procedure_code_6",
        "CLM_DRG_CD":                     "drg_code",
        "CLM_PMT_AMT":                    "payment_amount",
        "CLM_PASS_THRU_PER_DIEM_AMT":     "per_diem_amount",
        "NCH_BENE_IP_DDCTBL_AMT":         "deductible_amount",
        "NCH_BENE_PTA_COINSRNC_LBLTY_AM": "coinsurance_amount",
        "CLM_UTLZTN_DAY_CNT":             "utilization_days",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


def rename_outpatient_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "CLM_ID":                       "claim_id",
        "DESYNPUF_ID":                  "patient_id",
        "PROVIDER_ID":                  "provider_id",
        "CLM_FROM_DT":                  "admit_date",
        "CLM_THRU_DT":                  "discharge_date",
        "AT_PHYSN_NPI":                 "attending_npi",
        "ICD_DGNS_CD1":                 "diag_code_1",
        "ICD_DGNS_CD2":                 "diag_code_2",
        "ICD_DGNS_CD3":                 "diag_code_3",
        "ICD_DGNS_CD4":                 "diag_code_4",
        "ICD_DGNS_CD5":                 "diag_code_5",
        "ICD_DGNS_CD6":                 "diag_code_6",
        "ICD_DGNS_CD7":                 "diag_code_7",
        "ICD_DGNS_CD8":                 "diag_code_8",
        "ICD_DGNS_CD9":                 "diag_code_9",
        "ICD_DGNS_CD10":                "diag_code_10",
        "HCPCS_CD1":                    "hcpcs_code_1",
        "HCPCS_CD2":                    "hcpcs_code_2",
        "HCPCS_CD3":                    "hcpcs_code_3",
        "HCPCS_CD4":                    "hcpcs_code_4",
        "HCPCS_CD5":                    "hcpcs_code_5",
        "CLM_PMT_AMT":                  "payment_amount",
        "NCH_CARR_CLM_SBMTD_CHRG_AMT":  "submitted_amount",
        "NCH_CARR_CLM_ALWD_AMT":        "allowed_amount",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


def rename_carrier_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "CLM_ID":                   "claim_id",
        "DESYNPUF_ID":              "patient_id",
        "CLM_FROM_DT":              "service_date",
        "CLM_THRU_DT":              "service_end_date",
        "PRF_PHYSN_NPI":            "performing_npi",
        "ICD_DGNS_CD1":             "diag_code_1",
        "ICD_DGNS_CD2":             "diag_code_2",
        "ICD_DGNS_CD3":             "diag_code_3",
        "ICD_DGNS_CD4":             "diag_code_4",
        "ICD_DGNS_CD5":             "diag_code_5",
        "ICD_DGNS_CD6":             "diag_code_6",
        "ICD_DGNS_CD7":             "diag_code_7",
        "ICD_DGNS_CD8":             "diag_code_8",
        "HCPCS_CD":                 "hcpcs_code",
        "LINE_NCH_PMT_AMT":         "payment_amount",
        "LINE_BENE_PTB_DDCTBL_AMT": "deductible_amount",
        "LINE_COINSRNC_AMT":        "coinsurance_amount",
        "LINE_SRVC_CNT":            "service_count",
        "LINE_PRCSG_IND_CD":        "claim_status_code",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


def rename_prescription_columns(df: DataFrame) -> DataFrame:
    mapping = {
        "PDE_ID":         "prescription_id",
        "DESYNPUF_ID":    "patient_id",
        "SRVC_DT":        "service_date",
        "PROD_SRVC_ID":   "drug_code",
        "GNN":            "generic_name",
        "BNN":            "brand_name",
        "DAYS_SUPLY_NUM": "days_supply",
        "QTY_DSPNSD_NUM": "quantity_dispensed",
        "PTNT_PAY_AMT":   "patient_pay_amount",
        "TOT_RX_CST_AMT": "total_cost",
        "PLAN_PAY_AMT":   "plan_pay_amount",
    }
    for old, new in mapping.items():
        df = df.withColumnRenamed(old, new)
    return df


# ---------------------------------------------------------------------------
# Transformation group 2: Type casting
# ---------------------------------------------------------------------------

def cast_beneficiary_types(df: DataFrame) -> DataFrame:
    df = df.withColumn("birth_date", F.to_date(F.col("birth_date"), "yyyyMMdd"))
    df = df.withColumn("death_date",
        F.when(F.col("death_date").isNull() | (F.col("death_date") == ""), F.lit(None))
         .otherwise(F.to_date(F.col("death_date"), "yyyyMMdd"))
    )
    df = df.withColumn("gender_code", F.col("gender_code").cast(T.IntegerType()))
    df = df.withColumn("race_code", F.col("race_code").cast(T.IntegerType()))
    df = df.withColumn("coverage_months", F.col("coverage_months").cast(T.IntegerType()))
    for col in _CHRONIC_COLS:
        df = df.withColumn(col, F.col(col).cast(T.BooleanType()))
    return df


def cast_claims_types(df: DataFrame) -> DataFrame:
    for date_col in ["admit_date", "discharge_date", "service_date", "service_end_date"]:
        if date_col in df.columns:
            df = df.withColumn(date_col, F.to_date(F.col(date_col), "yyyyMMdd"))
    for amount_col in ["payment_amount", "deductible_amount", "coinsurance_amount",
                       "per_diem_amount", "submitted_amount", "allowed_amount"]:
        if amount_col in df.columns:
            df = df.withColumn(amount_col, F.col(amount_col).cast(T.DecimalType(12, 2)))
    if "utilization_days" in df.columns:
        df = df.withColumn("utilization_days", F.col("utilization_days").cast(T.IntegerType()))
    if "service_count" in df.columns:
        df = df.withColumn("service_count", F.col("service_count").cast(T.IntegerType()))
    return df


def cast_prescription_types(df: DataFrame) -> DataFrame:
    df = df.withColumn("service_date", F.to_date(F.col("service_date"), "yyyyMMdd"))
    for col in ["patient_pay_amount", "total_cost", "plan_pay_amount"]:
        df = df.withColumn(col, F.col(col).cast(T.DecimalType(10, 2)))
    df = df.withColumn("days_supply", F.col("days_supply").cast(T.IntegerType()))
    df = df.withColumn("quantity_dispensed", F.col("quantity_dispensed").cast(T.IntegerType()))
    return df


# ---------------------------------------------------------------------------
# Transformation group 3: Code decoding
# ---------------------------------------------------------------------------

def decode_gender(df: DataFrame) -> DataFrame:
    return df.withColumn("gender_label",
        F.when(F.col("gender_code") == 1, "Male")
         .when(F.col("gender_code") == 2, "Female")
         .otherwise("Unknown")
    )


def decode_race(df: DataFrame) -> DataFrame:
    return df.withColumn("race_label",
        F.when(F.col("race_code") == 1, "White")
         .when(F.col("race_code") == 2, "Black")
         .when(F.col("race_code") == 3, "Other")
         .when(F.col("race_code") == 4, "Asian")
         .when(F.col("race_code") == 5, "Hispanic")
         .when(F.col("race_code") == 6, "North American Native")
         .otherwise("Unknown")
    )


def decode_claim_status(df: DataFrame) -> DataFrame:
    return df.withColumn("claim_status",
        F.when(F.col("claim_status_code") == "A", "Assigned")
         .when(F.col("claim_status_code") == "N", "Non-assigned")
         .otherwise("Unknown")
    )


# ---------------------------------------------------------------------------
# Transformation group 4: Null handling
# ---------------------------------------------------------------------------

def handle_beneficiary_nulls(df: DataFrame) -> DataFrame:
    df = df.withColumn("is_deceased", F.col("death_date").isNotNull())
    df = df.withColumn("missing_birth_date_flag", F.col("birth_date").isNull())
    for col in _CHRONIC_COLS:
        df = df.withColumn(col, F.coalesce(F.col(col), F.lit(False)))
    return df


def handle_claims_nulls(df: DataFrame) -> DataFrame:
    amount_cols = [
        "payment_amount", "deductible_amount", "coinsurance_amount",
        "per_diem_amount", "submitted_amount", "allowed_amount",
        "patient_pay_amount", "total_cost", "plan_pay_amount",
    ]
    if "payment_amount" in df.columns:
        df = df.withColumn("is_payment_missing", F.col("payment_amount").isNull())
    for col in amount_cols:
        if col in df.columns:
            df = df.withColumn(col,
                F.coalesce(F.col(col), F.lit(0.0).cast(T.DecimalType(12, 2)))
            )
    return df


# ---------------------------------------------------------------------------
# Transformation group 5: Deduplication
# ---------------------------------------------------------------------------

def deduplicate(df: DataFrame, business_key: list[str]) -> DataFrame:
    return df.dropDuplicates(business_key)


# ---------------------------------------------------------------------------
# Transformation group 6: Date field derivation
# ---------------------------------------------------------------------------

def derive_date_fields(df: DataFrame, date_col: str) -> DataFrame:
    df = df.withColumn("year", F.year(F.col(date_col)))
    df = df.withColumn("quarter", F.quarter(F.col(date_col)))
    df = df.withColumn("month", F.month(F.col(date_col)))
    df = df.withColumn("week_of_year", F.weekofyear(F.col(date_col)))
    df = df.withColumn("date_key",
        F.date_format(F.col(date_col), "yyyyMMdd").cast(T.IntegerType())
    )
    return df


def derive_patient_age(df: DataFrame) -> DataFrame:
    df = df.withColumn("age",
        (F.datediff(F.current_date(), F.col("birth_date")) / 365.25).cast(T.IntegerType())
    )
    df = df.withColumn("age_group",
        F.when(F.col("age") < 18, "0-17")
         .when(F.col("age") < 35, "18-34")
         .when(F.col("age") < 50, "35-49")
         .when(F.col("age") < 65, "50-64")
         .otherwise("65+")
    )
    return df


def derive_length_of_stay(df: DataFrame) -> DataFrame:
    return df.withColumn("length_of_stay",
        F.datediff(F.col("discharge_date"), F.col("admit_date"))
    )


# ---------------------------------------------------------------------------
# Transformation group 7: Financial cleanup
# ---------------------------------------------------------------------------

def clean_financials(df: DataFrame, amount_cols: list[str]) -> DataFrame:
    primary_col = amount_cols[0]
    if primary_col not in df.columns:
        return df
    quantiles = df.approxQuantile(primary_col, [0.99], 0.01)
    threshold = float(quantiles[0]) if quantiles else 999999.0
    for col in amount_cols:
        if col not in df.columns:
            continue
        df = df.withColumn(f"is_negative_{col}", F.col(col) < 0)
        df = df.withColumn(col,
            F.when(F.col(col) < 0, F.lit(0.0).cast(T.DecimalType(12, 2)))
             .otherwise(F.round(F.col(col), 2).cast(T.DecimalType(12, 2)))
        )
    df = df.withColumn("is_high_cost", F.col(primary_col) > F.lit(threshold))
    return df


# ---------------------------------------------------------------------------
# Transformation group 8: Surrogate key generation
# ---------------------------------------------------------------------------

def generate_surrogate_key(df: DataFrame, source_col: str, key_col: str) -> DataFrame:
    return df.withColumn(key_col, F.sha2(F.col(source_col).cast(T.StringType()), 256))


# ---------------------------------------------------------------------------
# Transformation group 9: Risk flags
# ---------------------------------------------------------------------------

def add_patient_risk_flags(df: DataFrame) -> DataFrame:
    risk_cols = [F.col(c).cast(T.IntegerType()) for c in _CHRONIC_COLS]
    risk_expr = reduce(lambda a, b: a + b, risk_cols)
    df = df.withColumn("risk_score", risk_expr)
    df = df.withColumn("risk_tier",
        F.when(F.col("risk_score") <= 2, "Low")
         .when(F.col("risk_score") <= 5, "Medium")
         .otherwise("High")
    )
    df = df.withColumn("is_chronic", F.col("risk_score") >= 3)
    return df


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_parquet(df: DataFrame, bucket: str, prefix: str, partition_cols: list[str]) -> None:
    (df.write
       .partitionBy(*partition_cols)
       .mode("overwrite")
       .parquet(f"s3://{bucket}/{prefix}"))


# ---------------------------------------------------------------------------
# Orchestration: full ETL pipeline per entity
# ---------------------------------------------------------------------------

def process_beneficiary(spark: SparkSession, raw_bucket: str, clean_bucket: str) -> None:
    df = read_csv(spark, raw_bucket, "year=*/month=*/day=*/beneficiary_summary_")
    df = rename_beneficiary_columns(df)
    df = cast_beneficiary_types(df)
    df = decode_gender(df)
    df = decode_race(df)
    df = handle_beneficiary_nulls(df)
    df = deduplicate(df, ["patient_id"])
    df = derive_date_fields(df, "birth_date")
    df = derive_patient_age(df)
    df = add_patient_risk_flags(df)
    df = generate_surrogate_key(df, "patient_id", "patient_key")
    write_parquet(df, clean_bucket, "dim_patient", ["year"])


def process_providers(spark: SparkSession, raw_bucket: str, clean_bucket: str) -> None:
    df = read_csv(spark, raw_bucket, "year=*/month=*/day=*/providers_")
    df = rename_provider_columns(df)
    df = deduplicate(df, ["provider_id"])
    df = generate_surrogate_key(df, "provider_id", "provider_key")
    write_parquet(df, clean_bucket, "dim_provider", ["state_code"])


def process_inpatient_claims(spark: SparkSession, raw_bucket: str, clean_bucket: str) -> None:
    inp = read_csv(spark, raw_bucket, "year=*/month=*/day=*/inpatient_claims_")
    inp = rename_inpatient_columns(inp)
    inp = inp.withColumn("claim_type", F.lit("inpatient"))

    out = read_csv(spark, raw_bucket, "year=*/month=*/day=*/outpatient_claims_")
    out = rename_outpatient_columns(out)
    out = out.withColumn("claim_type", F.lit("outpatient"))

    # allowMissingColumns fills absent columns with null on each side
    df = inp.unionByName(out, allowMissingColumns=True)
    df = cast_claims_types(df)
    df = handle_claims_nulls(df)
    df = deduplicate(df, ["claim_id"])
    df = derive_date_fields(df, "admit_date")
    df = derive_length_of_stay(df)
    df = clean_financials(df, ["payment_amount"])
    df = generate_surrogate_key(df, "claim_id", "claim_key")
    write_parquet(df, clean_bucket, "fact_claims", ["year", "claim_type"])


def process_carrier_claims(spark: SparkSession, raw_bucket: str, clean_bucket: str) -> None:
    df = read_csv(spark, raw_bucket, "year=*/month=*/day=*/carrier_claims_")
    df = rename_carrier_columns(df)
    df = cast_claims_types(df)
    df = decode_claim_status(df)
    df = handle_claims_nulls(df)
    df = deduplicate(df, ["claim_id"])
    df = derive_date_fields(df, "service_date")
    df = clean_financials(df, ["payment_amount"])
    df = generate_surrogate_key(df, "claim_id", "claim_key")
    write_parquet(df, clean_bucket, "fact_carrier_claims", ["year", "month"])


def process_prescriptions(spark: SparkSession, raw_bucket: str, clean_bucket: str) -> None:
    df = read_csv(spark, raw_bucket, "year=*/month=*/day=*/prescription_drug_events_")
    df = rename_prescription_columns(df)
    df = cast_prescription_types(df)
    df = handle_claims_nulls(df)
    df = deduplicate(df, ["prescription_id"])
    df = derive_date_fields(df, "service_date")
    df = clean_financials(df, ["total_cost"])
    df = generate_surrogate_key(df, "prescription_id", "prescription_key")
    write_parquet(df, clean_bucket, "fact_prescriptions", ["year", "month"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    glue_context, job, args = init_glue_job()
    spark = glue_context.spark_session
    raw_bucket = args["RAW_CMS_BUCKET"]
    clean_bucket = args["CLEAN_CMS_BUCKET"]

    process_beneficiary(spark, raw_bucket, clean_bucket)
    process_providers(spark, raw_bucket, clean_bucket)
    process_inpatient_claims(spark, raw_bucket, clean_bucket)
    process_carrier_claims(spark, raw_bucket, clean_bucket)
    process_prescriptions(spark, raw_bucket, clean_bucket)

    job.commit()


if __name__ == "__main__":
    main()
