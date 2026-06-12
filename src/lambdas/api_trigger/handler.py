"""
Lambda handler — API trigger for the healthcare data pipeline.

Exposed via API Gateway (HTTP API, POST /trigger).
Asynchronously invokes the two generator Lambdas, then returns immediately
so the caller doesn't wait for data generation to complete.

Request body (JSON, all fields optional):
  {
    "records_per_batch": 500,   // overrides CMS Lambda env var
    "patients_per_batch": 200   // overrides FHIR Lambda env var
  }

Environment variables:
  CMS_LAMBDA_NAME  - Name/ARN of the cms-claims-generator Lambda
  FHIR_LAMBDA_NAME - Name/ARN of the fhir-generator Lambda

Response:
  202 Accepted — generation is in progress; check S3 for output.
"""

import json

import os
import uuid

import boto3

lambda_client = boto3.client("lambda")


def handler(event: dict, context) -> dict:
    cms_lambda  = os.environ["CMS_LAMBDA_NAME"]
    fhir_lambda = os.environ["FHIR_LAMBDA_NAME"]

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            pass

    trigger_id = str(uuid.uuid4())

    cms_payload = {}
    if "records_per_batch" in body:
        cms_payload["records_per_batch"] = body["records_per_batch"]

    fhir_payload = {}
    if "patients_per_batch" in body:
        fhir_payload["patients_per_batch"] = body["patients_per_batch"]

    # Invoke both generators asynchronously (fire-and-forget)
    lambda_client.invoke(
        FunctionName=cms_lambda,
        InvocationType="Event",           # async — does not wait for result
        Payload=json.dumps(cms_payload),
    )

    lambda_client.invoke(
        FunctionName=fhir_lambda,
        InvocationType="Event",
        Payload=json.dumps(fhir_payload),
    )

    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message":   "Data generation triggered successfully.",
            "triggerId": trigger_id,
        }),
    }
