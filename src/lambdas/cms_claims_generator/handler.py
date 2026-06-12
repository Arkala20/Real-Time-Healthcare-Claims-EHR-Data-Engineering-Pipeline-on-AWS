"""
Lambda handler — CMS Claims synthetic data generator.

Triggered by the api_trigger Lambda (InvocationType=Event, async).
Generates all 7 CMS Claims CSV entities and uploads them to the raw S3 bucket
under date-partitioned prefixes.

Environment variables:
  RAW_CMS_BUCKET    - S3 bucket name for raw CMS Claims output
  RECORDS_PER_BATCH - Number of records per entity per invocation (default: 500)

S3 key pattern:
  year=YYYY/month=MM/day=DD/<entity>_<batch_id>.csv
"""

import csv
import io
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from cms_claims_generator import (
    generate_beneficiary,
    generate_carrier_claims,
    generate_diagnosis_codes,
    generate_inpatient_claims,
    generate_outpatient_claims,
    generate_prescription_drug_events,
    generate_providers,
)

s3 = boto3.client("s3")


def _s3_key(entity: str, batch_id: str, now: datetime) -> str:
    return (
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}"
        f"/{entity}_{batch_id}.csv"
    )


def _upload_csv(bucket: str, key: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue(), ContentType="text/csv")


def handler(event: dict, context) -> dict:
    bucket = os.environ["RAW_CMS_BUCKET"]
    n      = int(os.environ.get("RECORDS_PER_BATCH", "500"))

    batch_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc)

    beneficiaries = generate_beneficiary(n)
    providers     = generate_providers(max(n // 10, 10))
    diag_codes    = generate_diagnosis_codes()

    bene_ids     = [r["DESYNPUF_ID"] for r in beneficiaries]
    provider_ids = [r["PROVIDER_ID"]  for r in providers]

    inpatient  = generate_inpatient_claims(n, bene_ids, provider_ids)
    outpatient = generate_outpatient_claims(n, bene_ids, provider_ids)
    carrier    = generate_carrier_claims(n, bene_ids)
    rx         = generate_prescription_drug_events(n, bene_ids)

    entities = {
        "beneficiary_summary":       beneficiaries,
        "providers":                 providers,
        "diagnosis_codes":           diag_codes,
        "inpatient_claims":          inpatient,
        "outpatient_claims":         outpatient,
        "carrier_claims":            carrier,
        "prescription_drug_events":  rx,
    }

    for name, rows in entities.items():
        _upload_csv(bucket, _s3_key(name, batch_id, now), rows)

    return {
        "statusCode": 200,
        "batchId":    batch_id,
        "bucket":     bucket,
        "counts":     {k: len(v) for k, v in entities.items()},
    }
