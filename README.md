# Real-Time Healthcare Claims & EHR Data Engineering Pipeline on AWS

End-to-end data engineering pipeline that ingests synthetic CMS Claims and FHIR EHR data, transforms it into a star schema, and lands analytics-ready Parquet files in S3.

## Architecture

```
[Generator] → [S3 Raw] → [Glue PySpark ETL] → [S3 Clean] → [Step Functions]
```

- **Generators**: Synthetic CMS Claims (CSV) and FHIR R4 EHR (JSON) via Python + Faker
- **ETL**: AWS Glue PySpark jobs flatten, clean, and transform data into star schema Parquet
- **Infrastructure**: AWS services provisioned manually via console/CLI

## Project Structure

```
src/
  generator/  Synthetic data generators (CMS Claims + FHIR EHR)
  glue/       PySpark ETL jobs
tests/        Unit tests for generators and ETL transforms
```

## Setup

```bash
pip install -r requirements.txt
python src/generator/cms_claims_generator.py --records 1000 --output ./data/raw/cms/
python src/generator/fhir_generator.py --patients 500 --output ./data/raw/ehr/
```

## Running Tests

```bash
pytest tests/
```
