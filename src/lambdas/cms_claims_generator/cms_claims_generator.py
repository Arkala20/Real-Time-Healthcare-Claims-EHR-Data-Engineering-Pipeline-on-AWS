"""
CMS Claims synthetic data generator.

Generates realistic CSV files matching the CMS DE-SynPUF schema for:
  - beneficiary_summary  (patient demographics, chronic condition flags)
  - providers            (provider IDs, NPI, specialty, location)
  - diagnosis_codes      (ICD-10 codes with descriptions and categories)
  - inpatient_claims     (hospital admissions, dates, costs, DRG, length of stay)
  - outpatient_claims    (outpatient visits, dates, costs, procedure codes)
  - carrier_claims       (carrier-level claims with denial codes)
  - prescription_drug_events (prescription fills, drug codes, days supply, costs)

Usage:
    python cms_claims_generator.py --records 1000 --output ./data/raw/cms/

Output files land in the specified output directory with filenames like:
    beneficiary_summary_<timestamp>.csv
    inpatient_claims_<timestamp>.csv
    ...
"""

import argparse
import csv
import os
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

# ---------------------------------------------------------------------------
# Module-level reference data
# ---------------------------------------------------------------------------

_ICD10_CODES = [
    ("E11.9",   "Type 2 diabetes mellitus without complications",        "Endocrine"),
    ("E11.65",  "Type 2 diabetes mellitus with hyperglycemia",           "Endocrine"),
    ("N18.3",   "Chronic kidney disease, stage 3",                       "Renal"),
    ("N18.4",   "Chronic kidney disease, stage 4",                       "Renal"),
    ("C34.10",  "Malignant neoplasm of upper lobe, bronchus or lung",    "Neoplasm"),
    ("J44.1",   "COPD with acute exacerbation",                         "Respiratory"),
    ("J44.0",   "COPD with acute lower respiratory infection",           "Respiratory"),
    ("F32.9",   "Major depressive disorder, single episode, unspecified","Mental Health"),
    ("I25.10",  "Atherosclerotic heart disease of native coronary artery","Cardiovascular"),
    ("I50.9",   "Heart failure, unspecified",                            "Cardiovascular"),
    ("I10",     "Essential (primary) hypertension",                      "Cardiovascular"),
    ("M81.0",   "Age-related osteoporosis without pathological fracture", "Musculoskeletal"),
    ("M06.9",   "Rheumatoid arthritis, unspecified",                     "Musculoskeletal"),
    ("I63.9",   "Cerebral infarction, unspecified",                      "Neurological"),
    ("E78.5",   "Hyperlipidemia, unspecified",                           "Endocrine"),
    ("J18.9",   "Pneumonia, unspecified organism",                       "Respiratory"),
    ("K21.0",   "Gastro-esophageal reflux disease with esophagitis",     "Digestive"),
    ("Z87.39",  "Personal history of other endocrine, nutritional",      "History"),
    ("I48.91",  "Unspecified atrial fibrillation",                       "Cardiovascular"),
    ("E11.40",  "Type 2 diabetes with diabetic neuropathy, unspecified", "Endocrine"),
]

_ICD10_CODE_ONLY = [row[0] for row in _ICD10_CODES]

_PROCEDURE_CODES = [
    "0016070", "0016071", "02100Z3", "02100Z4",
    "0B110Z4", "0B110ZZ", "0D110Z4", "0F140ZZ",
    "0GBC0ZZ", "0JWT0ZZ", "0LB00ZZ", "0RG10Z3",
]

_DRG_CODES = ["470", "291", "392", "603", "194", "065", "871", "190",
              "292", "378", "247", "683", "372", "177", "313"]

_HCPCS_CODES = ["99213", "99214", "99215", "93000", "71046", "80053",
                "36415", "99232", "85025", "93005", "76700", "99283",
                "71045", "80061", "83036"]

_NDC_DRUGS = [
    ("00093721401", "metformin hydrochloride",     "Glucophage",   "Antidiabetic"),
    ("00710222023", "lisinopril",                   "Zestril",      "ACE Inhibitor"),
    ("00710157023", "atorvastatin calcium",          "Lipitor",      "Statin"),
    ("59762152001", "amlodipine besylate",           "Norvasc",      "Calcium Channel Blocker"),
    ("00093003298", "omeprazole",                    "Prilosec",     "PPI"),
    ("00074721513", "levothyroxine sodium",          "Synthroid",    "Thyroid"),
    ("00850001302", "albuterol sulfate",             "ProAir HFA",   "Bronchodilator"),
    ("00168017260", "furosemide",                    "Lasix",        "Loop Diuretic"),
    ("00006089268", "warfarin sodium",               "Coumadin",     "Anticoagulant"),
    ("00071031668", "gabapentin",                    "Neurontin",    "Anticonvulsant"),
    ("00093104978", "sertraline hydrochloride",      "Zoloft",       "SSRI"),
    ("68180051301", "clopidogrel bisulfate",         "Plavix",       "Antiplatelet"),
]

_STATE_CODES = [f"{i:02d}" for i in range(1, 53)]
_PLAN_TYPES  = [10, 11, 12, 13]
_SPECIALTIES = [
    "01", "02", "03", "04", "05", "06", "07", "08", "10", "11",
    "13", "14", "15", "16", "17", "18", "19", "20", "21", "22",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_date(start: date, end: date) -> date:
    """Return a random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _fmt(d: date) -> str:
    """Format date as YYYYMMDD string (CMS standard)."""
    return d.strftime("%Y%m%d")


def _npi() -> str:
    """Generate a fake 10-digit NPI string."""
    return str(random.randint(1000000000, 9999999999))


def _claim_id() -> str:
    """Generate a unique 12-character alphanumeric claim ID."""
    return uuid.uuid4().hex[:12].upper()


# ---------------------------------------------------------------------------
# Beneficiary / Patient
# ---------------------------------------------------------------------------

def generate_beneficiary(n: int) -> list[dict[str, Any]]:
    """Generate n beneficiary_summary rows.

    Columns: DESYNPUF_ID, BENE_BIRTH_DT, BENE_DEATH_DT, BENE_SEX_IDENT_CD,
             BENE_RACE_CD, BENE_STATE_CD, BENE_COUNTY_CD, PLAN_TYPE,
             SP_DIABETES, SP_CHRNKIDN, SP_CNCR, SP_COPD, SP_DEPRESSN,
             SP_ISCHMCHT, SP_OSTEOPRS, SP_RA_OA, SP_STRKETIA, BENE_HI_CVRAGE_TOT_MONS
    """
    rows = []
    claim_date_start = date(2020, 1, 1)
    claim_date_end   = date(2024, 12, 31)

    for _ in range(n):
        birth_dt = _random_date(date(1930, 1, 1), date(1959, 12, 31))

        # ~8% of beneficiaries have a recorded death date
        if random.random() < 0.08:
            death_dt = _random_date(
                max(birth_dt + timedelta(days=365 * 65), claim_date_start),
                claim_date_end,
            )
            death_str = _fmt(death_dt)
        else:
            death_str = ""

        rows.append({
            "DESYNPUF_ID":             uuid.uuid4().hex[:16].upper(),
            "BENE_BIRTH_DT":           _fmt(birth_dt),
            "BENE_DEATH_DT":           death_str,
            "BENE_SEX_IDENT_CD":       random.choice([1, 2]),
            "BENE_RACE_CD":            random.choices([1, 2, 3, 4, 5, 6], weights=[70, 12, 6, 4, 6, 2])[0],
            "BENE_STATE_CD":           random.choice(_STATE_CODES),
            "BENE_COUNTY_CD":          f"{random.randint(1, 999):03d}",
            "PLAN_TYPE":               random.choice(_PLAN_TYPES),
            "SP_DIABETES":             random.choices([0, 1], weights=[60, 40])[0],
            "SP_CHRNKIDN":             random.choices([0, 1], weights=[75, 25])[0],
            "SP_CNCR":                 random.choices([0, 1], weights=[85, 15])[0],
            "SP_COPD":                 random.choices([0, 1], weights=[80, 20])[0],
            "SP_DEPRESSN":             random.choices([0, 1], weights=[70, 30])[0],
            "SP_ISCHMCHT":             random.choices([0, 1], weights=[65, 35])[0],
            "SP_OSTEOPRS":             random.choices([0, 1], weights=[75, 25])[0],
            "SP_RA_OA":                random.choices([0, 1], weights=[70, 30])[0],
            "SP_STRKETIA":             random.choices([0, 1], weights=[88, 12])[0],
            "BENE_HI_CVRAGE_TOT_MONS": random.randint(0, 12),
        })

    return rows


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def generate_providers(n: int) -> list[dict[str, Any]]:
    """Generate n provider rows.

    Columns: PROVIDER_ID, NPI, PRVDR_SPCLTY, PRVDR_STATE_CD, ORG_NAME,
             PRVDR_FIRST_NAME, PRVDR_LAST_NAME, PRVDR_GRP_PRTCPTN_FLAG
    """
    rows = []
    for _ in range(n):
        rows.append({
            "PROVIDER_ID":          uuid.uuid4().hex[:8].upper(),
            "NPI":                  _npi(),
            "PRVDR_SPCLTY":         random.choice(_SPECIALTIES),
            "PRVDR_STATE_CD":       random.choice(_STATE_CODES),
            "ORG_NAME":             fake.company(),
            "PRVDR_FIRST_NAME":     fake.first_name(),
            "PRVDR_LAST_NAME":      fake.last_name(),
            "PRVDR_GRP_PRTCPTN_FLAG": random.choice(["Y", "N"]),
        })
    return rows


# ---------------------------------------------------------------------------
# Diagnosis codes
# ---------------------------------------------------------------------------

def generate_diagnosis_codes() -> list[dict[str, Any]]:
    """Return a fixed set of ICD-10 diagnosis code rows used across claims.

    Columns: DGNS_CD, DGNS_DESC, DGNS_CATEGORY, CODE_SYSTEM
    """
    return [
        {
            "DGNS_CD":       code,
            "DGNS_DESC":     desc,
            "DGNS_CATEGORY": category,
            "CODE_SYSTEM":   "ICD10",
        }
        for code, desc, category in _ICD10_CODES
    ]


# ---------------------------------------------------------------------------
# Inpatient claims
# ---------------------------------------------------------------------------

def generate_inpatient_claims(
    n: int,
    beneficiary_ids: list[str],
    provider_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate n inpatient_claims rows.

    Columns: CLM_ID, DESYNPUF_ID, PROVIDER_ID, CLM_FROM_DT, CLM_THRU_DT,
             AT_PHYSN_NPI, OP_PHYSN_NPI, ICD_DGNS_CD1..10, ICD_PRCDR_CD1..6,
             CLM_DRG_CD, CLM_PMT_AMT, CLM_PASS_THRU_PER_DIEM_AMT,
             NCH_BENE_IP_DDCTBL_AMT, NCH_BENE_PTA_COINSRNC_LBLTY_AM,
             CLM_UTLZTN_DAY_CNT
    """
    rows = []
    start_range = date(2020, 1, 1)
    end_range   = date(2024, 12, 1)

    for _ in range(n):
        admit_dt    = _random_date(start_range, end_range)
        los         = random.randint(1, 14)
        discharge_dt = admit_dt + timedelta(days=los)

        # 1-10 diagnosis codes; pad remainder with empty string
        n_diag  = random.randint(1, 10)
        diag_codes = random.choices(_ICD10_CODE_ONLY, k=n_diag)
        diag_codes += [""] * (10 - n_diag)

        # 0-6 procedure codes
        n_proc  = random.randint(0, 6)
        proc_codes = random.choices(_PROCEDURE_CODES, k=n_proc) if n_proc else []
        proc_codes += [""] * (6 - n_proc)

        payment = round(random.uniform(3000, 80000), 2)

        rows.append({
            "CLM_ID":                          _claim_id(),
            "DESYNPUF_ID":                     random.choice(beneficiary_ids),
            "PROVIDER_ID":                     random.choice(provider_ids),
            "CLM_FROM_DT":                     _fmt(admit_dt),
            "CLM_THRU_DT":                     _fmt(discharge_dt),
            "AT_PHYSN_NPI":                    _npi(),
            "OP_PHYSN_NPI":                    _npi(),
            "ICD_DGNS_CD1":                    diag_codes[0],
            "ICD_DGNS_CD2":                    diag_codes[1],
            "ICD_DGNS_CD3":                    diag_codes[2],
            "ICD_DGNS_CD4":                    diag_codes[3],
            "ICD_DGNS_CD5":                    diag_codes[4],
            "ICD_DGNS_CD6":                    diag_codes[5],
            "ICD_DGNS_CD7":                    diag_codes[6],
            "ICD_DGNS_CD8":                    diag_codes[7],
            "ICD_DGNS_CD9":                    diag_codes[8],
            "ICD_DGNS_CD10":                   diag_codes[9],
            "ICD_PRCDR_CD1":                   proc_codes[0],
            "ICD_PRCDR_CD2":                   proc_codes[1],
            "ICD_PRCDR_CD3":                   proc_codes[2],
            "ICD_PRCDR_CD4":                   proc_codes[3],
            "ICD_PRCDR_CD5":                   proc_codes[4],
            "ICD_PRCDR_CD6":                   proc_codes[5],
            "CLM_DRG_CD":                      random.choice(_DRG_CODES),
            "CLM_PMT_AMT":                     payment,
            "CLM_PASS_THRU_PER_DIEM_AMT":      round(payment / los, 2),
            "NCH_BENE_IP_DDCTBL_AMT":          round(random.uniform(0, 1600), 2),
            "NCH_BENE_PTA_COINSRNC_LBLTY_AM":  round(random.uniform(0, 500), 2),
            "CLM_UTLZTN_DAY_CNT":              los,
        })

    return rows


# ---------------------------------------------------------------------------
# Outpatient claims
# ---------------------------------------------------------------------------

def generate_outpatient_claims(
    n: int,
    beneficiary_ids: list[str],
    provider_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate n outpatient_claims rows.

    Columns: CLM_ID, DESYNPUF_ID, PROVIDER_ID, CLM_FROM_DT, CLM_THRU_DT,
             AT_PHYSN_NPI, ICD_DGNS_CD1..10, HCPCS_CD1..5,
             CLM_PMT_AMT, NCH_CARR_CLM_SBMTD_CHRG_AMT, NCH_CARR_CLM_ALWD_AMT
    """
    rows = []
    start_range = date(2020, 1, 1)
    end_range   = date(2024, 12, 31)

    for _ in range(n):
        visit_dt = _random_date(start_range, end_range)

        n_diag = random.randint(1, 10)
        diag_codes = random.choices(_ICD10_CODE_ONLY, k=n_diag)
        diag_codes += [""] * (10 - n_diag)

        n_hcpcs = random.randint(1, 5)
        hcpcs_codes = random.choices(_HCPCS_CODES, k=n_hcpcs)
        hcpcs_codes += [""] * (5 - n_hcpcs)

        submitted = round(random.uniform(200, 5000), 2)
        allowed   = round(submitted * random.uniform(0.6, 0.9), 2)
        payment   = round(allowed  * random.uniform(0.7, 1.0), 2)

        rows.append({
            "CLM_ID":                       _claim_id(),
            "DESYNPUF_ID":                  random.choice(beneficiary_ids),
            "PROVIDER_ID":                  random.choice(provider_ids),
            "CLM_FROM_DT":                  _fmt(visit_dt),
            "CLM_THRU_DT":                  _fmt(visit_dt),
            "AT_PHYSN_NPI":                 _npi(),
            "ICD_DGNS_CD1":                 diag_codes[0],
            "ICD_DGNS_CD2":                 diag_codes[1],
            "ICD_DGNS_CD3":                 diag_codes[2],
            "ICD_DGNS_CD4":                 diag_codes[3],
            "ICD_DGNS_CD5":                 diag_codes[4],
            "ICD_DGNS_CD6":                 diag_codes[5],
            "ICD_DGNS_CD7":                 diag_codes[6],
            "ICD_DGNS_CD8":                 diag_codes[7],
            "ICD_DGNS_CD9":                 diag_codes[8],
            "ICD_DGNS_CD10":                diag_codes[9],
            "HCPCS_CD1":                    hcpcs_codes[0],
            "HCPCS_CD2":                    hcpcs_codes[1],
            "HCPCS_CD3":                    hcpcs_codes[2],
            "HCPCS_CD4":                    hcpcs_codes[3],
            "HCPCS_CD5":                    hcpcs_codes[4],
            "CLM_PMT_AMT":                  payment,
            "NCH_CARR_CLM_SBMTD_CHRG_AMT":  submitted,
            "NCH_CARR_CLM_ALWD_AMT":        allowed,
        })

    return rows


# ---------------------------------------------------------------------------
# Carrier claims
# ---------------------------------------------------------------------------

def generate_carrier_claims(
    n: int,
    beneficiary_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate n carrier_claims rows.

    Carrier claims are physician-billed and reference providers by NPI only,
    not by facility PROVIDER_ID.

    Columns: CLM_ID, DESYNPUF_ID, CLM_FROM_DT, CLM_THRU_DT,
             PRF_PHYSN_NPI, ICD_DGNS_CD1..8, HCPCS_CD,
             LINE_NCH_PMT_AMT, LINE_BENE_PTB_DDCTBL_AMT,
             LINE_COINSRNC_AMT, LINE_SRVC_CNT, LINE_PRCSG_IND_CD
    """
    rows = []
    start_range = date(2020, 1, 1)
    end_range   = date(2024, 12, 31)

    for _ in range(n):
        svc_dt = _random_date(start_range, end_range)

        n_diag = random.randint(1, 8)
        diag_codes = random.choices(_ICD10_CODE_ONLY, k=n_diag)
        diag_codes += [""] * (8 - n_diag)

        payment = round(random.uniform(50, 2000), 2)

        rows.append({
            "CLM_ID":                    _claim_id(),
            "DESYNPUF_ID":               random.choice(beneficiary_ids),
            "CLM_FROM_DT":               _fmt(svc_dt),
            "CLM_THRU_DT":               _fmt(svc_dt),
            "PRF_PHYSN_NPI":             _npi(),
            "ICD_DGNS_CD1":              diag_codes[0],
            "ICD_DGNS_CD2":              diag_codes[1],
            "ICD_DGNS_CD3":              diag_codes[2],
            "ICD_DGNS_CD4":              diag_codes[3],
            "ICD_DGNS_CD5":              diag_codes[4],
            "ICD_DGNS_CD6":              diag_codes[5],
            "ICD_DGNS_CD7":              diag_codes[6],
            "ICD_DGNS_CD8":              diag_codes[7],
            "HCPCS_CD":                  random.choice(_HCPCS_CODES),
            "LINE_NCH_PMT_AMT":          payment,
            "LINE_BENE_PTB_DDCTBL_AMT":  round(random.uniform(0, 185), 2),
            "LINE_COINSRNC_AMT":         round(payment * 0.2, 2),
            "LINE_SRVC_CNT":             random.randint(1, 5),
            "LINE_PRCSG_IND_CD":         random.choices(["A", "N"], weights=[85, 15])[0],
        })

    return rows


# ---------------------------------------------------------------------------
# Prescription drug events
# ---------------------------------------------------------------------------

def generate_prescription_drug_events(
    n: int,
    beneficiary_ids: list[str],
) -> list[dict[str, Any]]:
    """Generate n prescription_drug_events rows.

    Columns: PDE_ID, DESYNPUF_ID, SRVC_DT, PROD_SRVC_ID, GNN, BNN,
             DAYS_SUPLY_NUM, QTY_DSPNSD_NUM, PTNT_PAY_AMT,
             TOT_RX_CST_AMT, PLAN_PAY_AMT
    """
    rows = []
    start_range = date(2020, 1, 1)
    end_range   = date(2024, 12, 31)

    for _ in range(n):
        ndc, generic, brand, _ = random.choice(_NDC_DRUGS)
        days_supply = random.choice([7, 14, 30, 60, 90])
        total_cost  = round(random.uniform(10, 800), 2)
        patient_pay = round(total_cost * random.uniform(0.05, 0.30), 2)
        plan_pay    = round(total_cost - patient_pay, 2)

        rows.append({
            "PDE_ID":          uuid.uuid4().hex[:10].upper(),
            "DESYNPUF_ID":     random.choice(beneficiary_ids),
            "SRVC_DT":         _fmt(_random_date(start_range, end_range)),
            "PROD_SRVC_ID":    ndc,
            "GNN":             generic,
            "BNN":             brand,
            "DAYS_SUPLY_NUM":  days_supply,
            "QTY_DSPNSD_NUM":  days_supply * random.randint(1, 4),
            "PTNT_PAY_AMT":    patient_pay,
            "TOT_RX_CST_AMT":  total_cost,
            "PLAN_PAY_AMT":    plan_pay,
        })

    return rows


# ---------------------------------------------------------------------------
# CSV write helper
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict[str, Any]], filepath: str) -> None:
    """Write a list of dicts to a CSV file."""
    if not rows:
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic CMS Claims CSV data.")
    parser.add_argument("--records", type=int, default=1000, help="Number of records per table")
    parser.add_argument("--output",  type=str, default="./data/raw/cms/", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Generating {args.records} records per table → {args.output}")

    beneficiaries = generate_beneficiary(args.records)
    write_csv(beneficiaries, os.path.join(args.output, f"beneficiary_summary_{ts}.csv"))
    print(f"  beneficiary_summary:       {len(beneficiaries)} rows")

    providers = generate_providers(max(args.records // 10, 10))
    write_csv(providers, os.path.join(args.output, f"providers_{ts}.csv"))
    print(f"  providers:                 {len(providers)} rows")

    diag_codes = generate_diagnosis_codes()
    write_csv(diag_codes, os.path.join(args.output, f"diagnosis_codes_{ts}.csv"))
    print(f"  diagnosis_codes:           {len(diag_codes)} rows")

    bene_ids     = [r["DESYNPUF_ID"] for r in beneficiaries]
    provider_ids = [r["PROVIDER_ID"] for r in providers]

    inpatient = generate_inpatient_claims(args.records, bene_ids, provider_ids)
    write_csv(inpatient, os.path.join(args.output, f"inpatient_claims_{ts}.csv"))
    print(f"  inpatient_claims:          {len(inpatient)} rows")

    outpatient = generate_outpatient_claims(args.records, bene_ids, provider_ids)
    write_csv(outpatient, os.path.join(args.output, f"outpatient_claims_{ts}.csv"))
    print(f"  outpatient_claims:         {len(outpatient)} rows")

    carrier = generate_carrier_claims(args.records, bene_ids)
    write_csv(carrier, os.path.join(args.output, f"carrier_claims_{ts}.csv"))
    print(f"  carrier_claims:            {len(carrier)} rows")

    rx = generate_prescription_drug_events(args.records, bene_ids)
    write_csv(rx, os.path.join(args.output, f"prescription_drug_events_{ts}.csv"))
    print(f"  prescription_drug_events:  {len(rx)} rows")

    print("Done.")


if __name__ == "__main__":
    main()
