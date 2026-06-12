"""
Lambda handler — FHIR EHR synthetic data generator.

Triggered by the api_trigger Lambda (InvocationType=Event, async).
Generates FHIR R4 Bundle JSON files (one per patient) and uploads them
to the raw EHR S3 bucket under date-partitioned prefixes.

Environment variables:
  RAW_EHR_BUCKET    - S3 bucket name for raw FHIR EHR output
  PATIENTS_PER_BATCH - Number of patient bundles to generate per invocation (default: 200)

S3 key pattern:
  fhir/year=YYYY/month=MM/day=DD/<batch_id>_<patient_id>.json
"""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3

from fhir_generator import generate_bundle


s3 = boto3.client("s3")


def _s3_key(patient_id: str, batch_id: str, now: datetime) -> str:
    return (
        f"fhir/year={now.year}/month={now.month:02d}/day={now.day:02d}"
        f"/{batch_id}_{patient_id}.json"
    )


def handler(event: dict, context) -> dict:
    bucket = os.environ["RAW_EHR_BUCKET"]
    n      = int(os.environ.get("PATIENTS_PER_BATCH", "200"))

    batch_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc)

    for _ in range(n):
        bundle     = generate_bundle()
        patient_id = bundle.get("id", str(uuid.uuid4()))
        key        = _s3_key(patient_id, batch_id, now)

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(bundle, default=str),
            ContentType="application/json",
        )

    return {
        "statusCode":   200,
        "batchId":      batch_id,
        "bucket":       bucket,
        "patientsWritten": n,
    }
