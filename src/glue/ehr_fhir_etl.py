"""
EHR FHIR R4 PySpark ETL job — Glue 4.0 (PySpark 3.3, Python 3.10).

Reads raw FHIR R4 Bundle JSON files from S3, flattens nested resource arrays,
applies all EHR transformations, and writes analytics-ready Parquet files to
the clean S3 bucket.

FHIR resources processed (extracted from Bundle.entry[]):
  - Patient           → dim_patient
  - Practitioner      → dim_provider
  - Encounter         → fact_encounters
  - Condition         → fact_conditions
  - Observation       → fact_observations
  - MedicationRequest → fact_medications
  - Procedure         → fact_procedures
  - AllergyIntolerance→ fact_allergies
  - Immunization      → fact_immunizations

Job args:
  --RAW_EHR_BUCKET   S3 bucket name for raw FHIR JSON input
  --CLEAN_EHR_BUCKET S3 bucket name for clean Parquet output
  --JOB_NAME         Glue job name (injected by Glue runtime)
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T


# ---------------------------------------------------------------------------
# Glue job bootstrap
# ---------------------------------------------------------------------------

def init_glue_job() -> tuple[GlueContext, Job, dict]:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "RAW_EHR_BUCKET", "CLEAN_EHR_BUCKET"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    return glue_context, job, args


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_fhir_bundles(spark: SparkSession, bucket: str) -> DataFrame:
    return (
        spark.read
        .option("multiLine", "true")
        .option("recursiveFileLookup", "true")
        .json(f"s3://{bucket}/fhir/")
    )


# ---------------------------------------------------------------------------
# Transformation group 1: Bundle flattening
# ---------------------------------------------------------------------------

def flatten_bundle_entries(df: DataFrame) -> DataFrame:
    """Explode Bundle.entry[] — returns one row per FHIR resource."""
    return (
        df.select(
            F.col("id").alias("bundle_id"),
            F.col("timestamp").alias("bundle_timestamp"),
            F.explode("entry").alias("entry"),
        )
        .select(
            "bundle_id",
            "bundle_timestamp",
            F.col("entry.resource").alias("resource"),
            F.col("entry.resource.resourceType").alias("resource_type"),
        )
    )


def filter_by_resource_type(df: DataFrame, resource_type: str) -> DataFrame:
    return df.filter(F.col("resource_type") == resource_type)


# resource.name is inferred as string by Spark because Organization.name is a plain
# string while Patient/Practitioner.name is an array of structs — use from_json to
# re-parse it after filtering to the correct resource type.
_PATIENT_NAME_SCHEMA = T.ArrayType(T.StructType([
    T.StructField("family", T.StringType()),
    T.StructField("given",  T.ArrayType(T.StringType())),
]))

_PROVIDER_NAME_SCHEMA = T.ArrayType(T.StructType([
    T.StructField("family", T.StringType()),
    T.StructField("given",  T.ArrayType(T.StringType())),
    T.StructField("prefix", T.ArrayType(T.StringType())),
]))


# ---------------------------------------------------------------------------
# Transformation group 2: Patient flattening
# ---------------------------------------------------------------------------

def flatten_patient(df: DataFrame) -> DataFrame:
    name = F.from_json(F.col("resource.name").cast("string"), _PATIENT_NAME_SCHEMA)
    return filter_by_resource_type(df, "Patient").select(
        F.col("resource.id").alias("patient_id"),
        F.col("resource.identifier")[0]["value"].alias("mrn"),
        name[0]["family"].alias("family_name"),
        name[0]["given"][0].alias("given_name"),
        F.col("resource.gender").alias("gender"),
        F.col("resource.birthDate").alias("birth_date"),
        F.col("resource.address")[0]["line"][0].alias("address_line"),
        F.col("resource.address")[0]["city"].alias("city"),
        F.col("resource.address")[0]["state"].alias("state"),
        F.col("resource.address")[0]["postalCode"].alias("postal_code"),
        F.col("resource.extension")[0]["valueString"].alias("race"),
        F.col("resource.extension")[1]["valueString"].alias("ethnicity"),
    )


# ---------------------------------------------------------------------------
# Transformation group 3: Encounter flattening
# ---------------------------------------------------------------------------

def flatten_encounter(df: DataFrame) -> DataFrame:
    # `class` is a reserved word — use getField() to avoid parser issues
    # extension uses valueMoney (not valueDecimal) — generator outputs {"url":"totalCost","valueMoney":{...}}
    return filter_by_resource_type(df, "Encounter").select(
        F.col("resource.id").alias("encounter_id"),
        F.col("resource.status").alias("status"),
        F.col("resource").getField("class").getField("code").alias("encounter_class"),
        F.col("resource.subject.reference").alias("patient_ref"),
        F.col("resource.period.start").alias("period_start"),
        F.col("resource.period.end").alias("period_end"),
        F.col("resource.reasonCode")[0]["coding"][0]["code"].alias("reason_icd10"),
        F.col("resource.extension")[0]["valueMoney"]["value"].alias("total_cost"),
    )


# ---------------------------------------------------------------------------
# Transformation group 4: Condition flattening
# ---------------------------------------------------------------------------

def flatten_condition(df: DataFrame) -> DataFrame:
    return filter_by_resource_type(df, "Condition").select(
        F.col("resource.id").alias("condition_id"),
        F.col("resource.clinicalStatus.coding")[0]["code"].alias("clinical_status"),
        F.col("resource.code.coding")[0]["code"].alias("icd10_code"),
        F.col("resource.code.coding")[0]["display"].alias("icd10_display"),
        F.col("resource.code.coding")[1]["code"].alias("snomed_code"),
        F.col("resource.code.coding")[1]["display"].alias("snomed_display"),
        F.col("resource.subject.reference").alias("patient_ref"),
        F.col("resource.encounter.reference").alias("encounter_ref"),
        F.col("resource.onsetDateTime").alias("onset_datetime"),
        F.col("resource.abatementDateTime").alias("abatement_datetime"),
    )


# ---------------------------------------------------------------------------
# Transformation group 5: Observation flattening
# ---------------------------------------------------------------------------

def flatten_observation(df: DataFrame) -> DataFrame:
    # resource.category conflicts: AllergyIntolerance uses ["food"] (string array) while
    # Observation uses [{coding:[...]}] (struct array). Spark merges both to StringType,
    # so struct access fails. Use get_json_object on the string element instead.
    return filter_by_resource_type(df, "Observation").select(
        F.col("resource.id").alias("observation_id"),
        F.col("resource.status").alias("status"),
        F.get_json_object(F.col("resource.category")[0], "$.coding[0].code").alias("category"),
        F.col("resource.code.coding")[0]["code"].alias("loinc_code"),
        F.col("resource.code.coding")[0]["display"].alias("loinc_display"),
        F.col("resource.subject.reference").alias("patient_ref"),
        F.col("resource.encounter.reference").alias("encounter_ref"),
        F.col("resource.effectiveDateTime").alias("effective_datetime"),
        F.col("resource.valueQuantity.value").alias("value"),
        F.col("resource.valueQuantity.unit").alias("unit"),
        F.col("resource.referenceRange")[0]["low"]["value"].alias("ref_low"),
        F.col("resource.referenceRange")[0]["high"]["value"].alias("ref_high"),
        F.col("resource.interpretation")[0]["coding"][0]["code"].alias("interpretation_code"),
    )


# ---------------------------------------------------------------------------
# Transformation group 6: MedicationRequest flattening
# ---------------------------------------------------------------------------

def flatten_medication_request(df: DataFrame) -> DataFrame:
    return filter_by_resource_type(df, "MedicationRequest").select(
        F.col("resource.id").alias("medication_request_id"),
        F.col("resource.status").alias("status"),
        F.col("resource.medicationCodeableConcept.coding")[0]["code"].alias("rxnorm_code"),
        F.col("resource.medicationCodeableConcept.coding")[0]["display"].alias("drug_name"),
        F.col("resource.subject.reference").alias("patient_ref"),
        F.col("resource.encounter.reference").alias("encounter_ref"),
        F.col("resource.requester.reference").alias("provider_ref"),
        F.col("resource.authoredOn").alias("authored_on"),
        F.col("resource.dosageInstruction")[0]["text"].alias("dosage_text"),
        F.col("resource.dosageInstruction")[0]["doseAndRate"][0]["doseQuantity"]["value"].alias("dose_value"),
        F.col("resource.dosageInstruction")[0]["doseAndRate"][0]["doseQuantity"]["unit"].alias("dose_unit"),
    )


# ---------------------------------------------------------------------------
# Transformation group 7: PHI masking
# ---------------------------------------------------------------------------

def mask_phi(df: DataFrame, phi_cols: list[str]) -> DataFrame:
    for col in phi_cols:
        if col in df.columns:
            df = df.withColumn(col, F.sha2(F.col(col).cast(T.StringType()), 256))
    return df


# ---------------------------------------------------------------------------
# Transformation group 8: Medical code enrichment
# ---------------------------------------------------------------------------

def enrich_icd10_codes(df: DataFrame, code_col: str) -> DataFrame:
    icd10_lookup = [
        ("E11.9",  "Type 2 diabetes mellitus without complications",     "Endocrine"),
        ("I10",    "Essential (primary) hypertension",                   "Cardiovascular"),
        ("E78.5",  "Hyperlipidemia, unspecified",                        "Endocrine"),
        ("I25.10", "Atherosclerotic heart disease of native coronary artery", "Cardiovascular"),
        ("J44.1",  "COPD with acute exacerbation",                       "Respiratory"),
        ("N18.3",  "Chronic kidney disease, stage 3",                    "Renal"),
        ("F32.9",  "Major depressive disorder, single episode",          "Mental Health"),
        ("I50.9",  "Heart failure, unspecified",                         "Cardiovascular"),
        ("M06.9",  "Rheumatoid arthritis, unspecified",                  "Musculoskeletal"),
        ("I63.9",  "Cerebral infarction, unspecified",                   "Neurological"),
    ]
    schema = T.StructType([
        T.StructField("_code", T.StringType()),
        T.StructField("_description", T.StringType()),
        T.StructField("_category", T.StringType()),
    ])
    lookup_df = df.sparkSession.createDataFrame(icd10_lookup, schema)
    lookup_df = lookup_df.withColumnRenamed("_code", "lk_code")
    df = df.join(F.broadcast(lookup_df), df[code_col] == lookup_df["lk_code"], "left")
    df = df.withColumnRenamed("_description", "icd10_description")
    df = df.withColumnRenamed("_category", "icd10_category")
    df = df.drop("lk_code")
    return df


def enrich_loinc_codes(df: DataFrame, code_col: str) -> DataFrame:
    loinc_lookup = [
        ("2339-0",  "Glucose in Blood",          "laboratory"),
        ("4548-4",  "Hemoglobin A1c",             "laboratory"),
        ("2160-0",  "Creatinine in Serum",        "laboratory"),
        ("8310-5",  "Body temperature",           "vital-signs"),
        ("8867-4",  "Heart rate",                 "vital-signs"),
        ("55284-4", "Blood pressure systolic",    "vital-signs"),
        ("29463-7", "Body weight",                "vital-signs"),
        ("39156-5", "Body mass index",            "vital-signs"),
    ]
    schema = T.StructType([
        T.StructField("_code", T.StringType()),
        T.StructField("_display", T.StringType()),
        T.StructField("_cat", T.StringType()),
    ])
    lookup_df = df.sparkSession.createDataFrame(loinc_lookup, schema)
    df = df.join(F.broadcast(lookup_df), df[code_col] == lookup_df["_code"], "left")
    df = df.withColumnRenamed("_display", "loinc_display_enriched")
    df = df.withColumnRenamed("_cat", "loinc_category")
    df = df.drop("_code")
    return df


def enrich_rxnorm_codes(df: DataFrame, code_col: str) -> DataFrame:
    rxnorm_lookup = [
        ("860975", "metformin hydrochloride", "Antidiabetic"),
        ("314076", "lisinopril",              "ACE Inhibitor"),
        ("617310", "atorvastatin",            "Statin"),
        ("197361", "amlodipine",              "Calcium Channel Blocker"),
        ("197381", "furosemide",              "Loop Diuretic"),
        ("855332", "warfarin sodium",         "Anticoagulant"),
        ("966571", "levothyroxine sodium",    "Thyroid"),
        ("310429", "gabapentin",              "Anticonvulsant"),
    ]
    schema = T.StructType([
        T.StructField("_code", T.StringType()),
        T.StructField("_name", T.StringType()),
        T.StructField("_class", T.StringType()),
    ])
    lookup_df = df.sparkSession.createDataFrame(rxnorm_lookup, schema)
    df = df.join(F.broadcast(lookup_df), df[code_col] == lookup_df["_code"], "left")
    df = df.withColumnRenamed("_name", "drug_name_enriched")
    df = df.withColumnRenamed("_class", "drug_class")
    df = df.drop("_code")
    return df


# ---------------------------------------------------------------------------
# Transformation group 9: Timestamp normalization
# ---------------------------------------------------------------------------

def normalize_timestamps(df: DataFrame, datetime_cols: list[str]) -> DataFrame:
    for col in datetime_cols:
        if col in df.columns:
            df = df.withColumn(col, F.to_timestamp(F.col(col)))
    return df


# ---------------------------------------------------------------------------
# Transformation group 10: Derived fields
# ---------------------------------------------------------------------------

def derive_patient_fields(df: DataFrame) -> DataFrame:
    df = df.withColumn("birth_date_parsed", F.to_date(F.col("birth_date"), "yyyy-MM-dd"))
    df = df.withColumn("age",
        (F.datediff(F.current_date(), F.col("birth_date_parsed")) / 365.25).cast(T.IntegerType())
    )
    df = df.withColumn("age_group",
        F.when(F.col("age") < 18, "0-17")
         .when(F.col("age") < 35, "18-34")
         .when(F.col("age") < 50, "35-49")
         .when(F.col("age") < 65, "50-64")
         .otherwise("65+")
    )
    return df


def derive_encounter_fields(df: DataFrame) -> DataFrame:
    df = df.withColumn("encounter_duration_hours",
        (F.unix_timestamp("period_end") - F.unix_timestamp("period_start")) / 3600.0
    )
    df = df.withColumn("is_emergency", F.col("encounter_class") == "EMER")
    df = df.withColumn("visit_year", F.year(F.col("period_start")))
    df = df.withColumn("visit_month", F.month(F.col("period_start")))
    return df


def derive_observation_flags(df: DataFrame) -> DataFrame:
    return df.withColumn("is_abnormal",
        F.when(F.col("interpretation_code").isin("H", "L"), True).otherwise(False)
    )


def derive_condition_flags(df: DataFrame) -> DataFrame:
    chronic_codes = [
        "E11.9", "I10", "E78.5", "I25.10", "J44.1",
        "N18.3", "F32.9", "I50.9", "M06.9", "I63.9",
    ]
    df = df.withColumn("is_resolved", F.col("abatement_datetime").isNotNull())
    df = df.withColumn("is_chronic", F.col("icd10_code").isin(chronic_codes))
    return df


def derive_medication_flags(df: DataFrame) -> DataFrame:
    chronic_keywords = [
        "metformin", "lisinopril", "atorvastatin", "amlodipine",
        "furosemide", "warfarin", "levothyroxine", "omeprazole",
    ]
    is_chronic = F.lit(False)
    for kw in chronic_keywords:
        is_chronic = is_chronic | F.lower(F.col("drug_name")).contains(kw)
    return df.withColumn("is_chronic_med", is_chronic)


# ---------------------------------------------------------------------------
# Transformation group 11: Surrogate keys
# ---------------------------------------------------------------------------

def generate_surrogate_key(df: DataFrame, source_col: str, key_col: str) -> DataFrame:
    return df.withColumn(key_col, F.sha2(F.col(source_col).cast(T.StringType()), 256))


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_parquet(df: DataFrame, bucket: str, prefix: str, partition_cols: list[str]) -> None:
    (df.write
       .partitionBy(*partition_cols)
       .mode("overwrite")
       .parquet(f"s3://{bucket}/{prefix}"))


# ---------------------------------------------------------------------------
# Orchestration: full ETL pipeline per resource
# ---------------------------------------------------------------------------

def process_patients(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = flatten_patient(bundles_df)
    df = mask_phi(df, ["family_name", "given_name", "birth_date", "address_line", "mrn"])
    df = derive_patient_fields(df)
    df = generate_surrogate_key(df, "patient_id", "patient_key")
    write_parquet(df, clean_bucket, "dim_patient", ["gender"])


def flatten_practitioner(df: DataFrame) -> DataFrame:
    """Flatten FHIR Practitioner resource into tabular columns."""
    name = F.from_json(F.col("resource.name").cast("string"), _PROVIDER_NAME_SCHEMA)
    return df.select(
        F.col("resource.id").alias("provider_id"),
        name[0]["family"].alias("last_name"),
        name[0]["given"][0].alias("first_name"),
        name[0]["prefix"][0].alias("prefix"),
        F.col("resource.gender").alias("gender"),
        F.col("resource.identifier")[0]["value"].alias("npi"),
        F.col("resource.qualification")[0]["code"]["coding"][0]["code"].alias("specialty_code"),
    )


def process_practitioners(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    pract_df = filter_by_resource_type(bundles_df, "Practitioner")
    name = F.from_json(F.col("resource.name").cast("string"), _PROVIDER_NAME_SCHEMA)
    # qualification.code.coding has only {system, code} — no display field in generator output
    df = pract_df.select(
        F.col("resource.id").alias("practitioner_id"),
        F.col("resource.identifier")[0]["value"].alias("npi"),
        name[0]["family"].alias("family_name"),
        name[0]["given"][0].alias("given_name"),
        F.col("resource.qualification")[0]["code"]["coding"][0]["code"].alias("specialty_code"),
    )
    df = df.dropDuplicates(["npi"])
    df = generate_surrogate_key(df, "practitioner_id", "provider_key")
    write_parquet(df, clean_bucket, "dim_provider", ["specialty_code"])


def process_encounters(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = flatten_encounter(bundles_df)
    df = normalize_timestamps(df, ["period_start", "period_end"])
    df = derive_encounter_fields(df)
    df = generate_surrogate_key(df, "encounter_id", "encounter_key")
    write_parquet(df, clean_bucket, "fact_encounters", ["visit_year", "visit_month"])


def process_conditions(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = flatten_condition(bundles_df)
    df = normalize_timestamps(df, ["onset_datetime", "abatement_datetime"])
    df = enrich_icd10_codes(df, "icd10_code")
    df = derive_condition_flags(df)
    df = generate_surrogate_key(df, "condition_id", "condition_key")
    write_parquet(df, clean_bucket, "fact_conditions", ["is_chronic"])


def process_observations(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = flatten_observation(bundles_df)
    df = normalize_timestamps(df, ["effective_datetime"])
    df = derive_observation_flags(df)
    df = generate_surrogate_key(df, "observation_id", "observation_key")
    write_parquet(df, clean_bucket, "fact_observations", ["category"])


def process_medications(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = flatten_medication_request(bundles_df)
    df = normalize_timestamps(df, ["authored_on"])
    df = enrich_rxnorm_codes(df, "rxnorm_code")
    df = derive_medication_flags(df)
    df = generate_surrogate_key(df, "medication_request_id", "medication_key")
    write_parquet(df, clean_bucket, "fact_medications", ["is_chronic_med"])


def process_procedures(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = filter_by_resource_type(bundles_df, "Procedure").select(
        F.col("resource.id").alias("procedure_id"),
        F.col("resource.status").alias("status"),
        F.col("resource.code.coding")[0]["code"].alias("cpt_code"),
        F.col("resource.code.coding")[0]["display"].alias("cpt_display"),
        F.col("resource.subject.reference").alias("patient_ref"),
        F.col("resource.encounter.reference").alias("encounter_ref"),
        F.col("resource.performedDateTime").alias("performed_datetime"),
        F.col("resource.extension")[0]["valueMoney"]["value"].alias("procedure_cost"),
    )
    df = normalize_timestamps(df, ["performed_datetime"])
    df = generate_surrogate_key(df, "procedure_id", "procedure_key")
    write_parquet(df, clean_bucket, "fact_procedures", ["status"])


def process_allergies(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = filter_by_resource_type(bundles_df, "AllergyIntolerance").select(
        F.col("resource.id").alias("allergy_id"),
        F.col("resource.clinicalStatus.coding")[0]["code"].alias("clinical_status"),
        F.col("resource.code.coding")[0]["display"].alias("substance"),
        F.col("resource.patient.reference").alias("patient_ref"),
        F.col("resource.reaction")[0]["manifestation"][0]["coding"][0]["display"].alias("reaction"),
        F.col("resource.reaction")[0]["severity"].alias("severity"),
    )
    df = generate_surrogate_key(df, "allergy_id", "allergy_key")
    write_parquet(df, clean_bucket, "fact_allergies", ["severity"])


def process_immunizations(spark: SparkSession, bundles_df: DataFrame, clean_bucket: str) -> None:
    df = filter_by_resource_type(bundles_df, "Immunization").select(
        F.col("resource.id").alias("immunization_id"),
        F.col("resource.status").alias("status"),
        F.col("resource.vaccineCode.coding")[0]["code"].alias("cvx_code"),
        F.col("resource.vaccineCode.coding")[0]["display"].alias("vaccine_name"),
        F.col("resource.patient.reference").alias("patient_ref"),
        F.col("resource.occurrenceDateTime").alias("occurrence_datetime"),
        F.col("resource.lotNumber").alias("lot_number"),
    )
    df = normalize_timestamps(df, ["occurrence_datetime"])
    df = generate_surrogate_key(df, "immunization_id", "immunization_key")
    write_parquet(df, clean_bucket, "fact_immunizations", ["status"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    glue_context, job, args = init_glue_job()
    spark = glue_context.spark_session
    raw_bucket = args["RAW_EHR_BUCKET"]
    clean_bucket = args["CLEAN_EHR_BUCKET"]

    bundles_df = read_fhir_bundles(spark, raw_bucket)
    flat_df = flatten_bundle_entries(bundles_df)

    # Cache the flattened DataFrame — reused across all process_* calls
    flat_df.cache()

    process_patients(spark, flat_df, clean_bucket)
    process_practitioners(spark, flat_df, clean_bucket)
    process_encounters(spark, flat_df, clean_bucket)
    process_conditions(spark, flat_df, clean_bucket)
    process_observations(spark, flat_df, clean_bucket)
    process_medications(spark, flat_df, clean_bucket)
    process_procedures(spark, flat_df, clean_bucket)
    process_allergies(spark, flat_df, clean_bucket)
    process_immunizations(spark, flat_df, clean_bucket)

    flat_df.unpersist()
    job.commit()


if __name__ == "__main__":
    main()
