"""
FHIR R4 EHR synthetic data generator.

Generates FHIR R4 Bundle JSON files containing linked resources that mirror
the EHR relational schema from the plan:
  - Patient        (demographics, identifiers, address)
  - Organization   (hospital/clinic details)
  - Practitioner   (provider name, specialty)
  - Encounter      (visit with type, period, reason, charges)
  - Condition      (ICD-10/SNOMED diagnosis with onset/abatement dates)
  - Observation    (lab results and vitals with LOINC codes, values, units)
  - MedicationRequest (active medications with RxNorm codes, dosage, frequency)
  - Procedure      (surgical/procedural records with CPT codes)
  - AllergyIntolerance (allergic substances, reactions, severity)
  - Immunization   (vaccine records with CVX codes)

Each call to generate_bundle() returns one FHIR Bundle (type: collection) for a
single patient with all linked resources.

Usage:
    python fhir_generator.py --patients 500 --output ./data/raw/ehr/
"""

import argparse
import json
import os
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from faker import Faker

fake = Faker()
Faker.seed(0)
random.seed(0)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

_ICD10 = [
    ("E11.9",  "Type 2 diabetes mellitus without complications"),
    ("I10",    "Essential (primary) hypertension"),
    ("E78.5",  "Hyperlipidemia, unspecified"),
    ("I25.10", "Atherosclerotic heart disease of native coronary artery"),
    ("J44.1",  "COPD with acute exacerbation"),
    ("N18.3",  "Chronic kidney disease, stage 3"),
    ("F32.9",  "Major depressive disorder, single episode, unspecified"),
    ("I50.9",  "Heart failure, unspecified"),
    ("M06.9",  "Rheumatoid arthritis, unspecified"),
    ("I63.9",  "Cerebral infarction, unspecified"),
]

_SNOMED = [
    ("44054006",  "Diabetes mellitus type 2"),
    ("38341003",  "Hypertensive disorder"),
    ("55822004",  "Hyperlipidemia"),
    ("53741008",  "Coronary arteriosclerosis"),
    ("13645005",  "Chronic obstructive lung disease"),
    ("709044004", "Chronic kidney disease"),
    ("35489007",  "Depressive disorder"),
    ("84114007",  "Heart failure"),
    ("69896004",  "Rheumatoid arthritis"),
    ("230690007", "Cerebrovascular accident"),
]

_LAB_LOINC = [
    ("2339-0",  "Glucose [Mass/volume] in Blood",          70, 100,  "mg/dL"),
    ("4548-4",  "Hemoglobin A1c/Hemoglobin.total in Blood", 4,   5.7, "%"),
    ("2160-0",  "Creatinine [Mass/volume] in Serum",       0.6,  1.2, "mg/dL"),
    ("2823-3",  "Potassium [Moles/volume] in Serum",       3.5,  5.0, "mmol/L"),
    ("2951-2",  "Sodium [Moles/volume] in Serum",          136, 145,  "mmol/L"),
    ("718-7",   "Hemoglobin [Mass/volume] in Blood",       12,   17,  "g/dL"),
    ("6690-2",  "Leukocytes [#/volume] in Blood",          4.5, 11.0, "10*3/uL"),
    ("2085-9",  "Cholesterol in HDL [Mass/volume] in Serum", 40, 60,  "mg/dL"),
    ("13457-7", "Cholesterol in LDL [Mass/volume] in Serum", 0, 100,  "mg/dL"),
    ("3094-0",  "Urea nitrogen [Mass/volume] in Serum",    7,   20,   "mg/dL"),
]

_VITAL_LOINC = [
    ("8310-5", "Body temperature",          36.1, 37.2, "Cel"),
    ("8867-4", "Heart rate",                60,   100,  "/min"),
    ("9279-1", "Respiratory rate",          12,   20,   "/min"),
    ("55284-4","Blood pressure systolic",   90,   120,  "mm[Hg]"),
    ("8302-2", "Body height",               150,  190,  "cm"),
    ("29463-7","Body weight",               50,   100,  "kg"),
    ("39156-5","Body mass index",           18.5, 24.9, "kg/m2"),
    ("59408-5","Oxygen saturation",         95,   100,  "%"),
]

_RXNORM_DRUGS = [
    ("860975", "metformin hydrochloride 500 MG",  "Take 1 tablet twice daily with meals",  500,  "mg"),
    ("314076", "lisinopril 10 MG",                "Take 1 tablet once daily",               10,   "mg"),
    ("617310", "atorvastatin 40 MG",              "Take 1 tablet once daily at bedtime",    40,   "mg"),
    ("197361", "amlodipine 5 MG",                 "Take 1 tablet once daily",               5,    "mg"),
    ("311725", "omeprazole 20 MG",                "Take 1 capsule once daily before meal",  20,   "mg"),
    ("966571", "levothyroxine sodium 50 UG",      "Take 1 tablet once daily on empty stomach", 50, "ug"),
    ("745276", "albuterol 90 MCG/ACTUAT",         "Inhale 2 puffs every 4-6 hours as needed", 90, "ug"),
    ("197381", "furosemide 40 MG",                "Take 1 tablet once daily in the morning",  40, "mg"),
    ("855332", "warfarin sodium 5 MG",            "Take as directed per INR monitoring",    5,    "mg"),
    ("310429", "gabapentin 300 MG",               "Take 1 capsule three times daily",       300,  "mg"),
]

_CPT_PROCEDURES = [
    ("99213", "Office visit, established patient, low complexity"),
    ("93000", "Electrocardiogram, routine ECG"),
    ("71046", "Chest X-ray, 2 views"),
    ("80053", "Comprehensive metabolic panel"),
    ("36415", "Routine venipuncture"),
    ("93306", "Echocardiography with spectral Doppler"),
    ("45378", "Colonoscopy, diagnostic"),
    ("70553", "MRI brain with contrast"),
    ("27447", "Total knee arthroplasty"),
    ("33533", "Coronary artery bypass, arterial, single"),
]

_ALLERGIES = [
    ("372687004", "Amoxicillin",  "Hives",              "moderate"),
    ("372687004", "Penicillin",   "Anaphylaxis",         "severe"),
    ("387458008", "Aspirin",      "Gastrointestinal upset","mild"),
    ("372756006", "Sulfonamide",  "Rash",               "moderate"),
    ("372528001", "Codeine",      "Nausea and vomiting", "mild"),
    ("256277009", "Peanuts",      "Anaphylaxis",         "severe"),
    ("227493005", "Shellfish",    "Hives",              "moderate"),
    ("412071004", "Latex",        "Contact dermatitis",  "mild"),
]

_VACCINES = [
    ("140", "Influenza, seasonal, injectable"),
    ("20",  "DTaP"),
    ("115", "Tdap"),
    ("08",  "Hepatitis B, adolescent or pediatric"),
    ("62",  "HPV, quadrivalent"),
    ("03",  "MMR"),
    ("21",  "Varicella"),
    ("33",  "Pneumococcal polysaccharide PPV23"),
    ("121", "Zoster live"),
    ("207", "COVID-19, mRNA, LNP-S, PF, 100 mcg/0.5 mL dose"),
]

_ENCOUNTER_CLASSES = ["AMB", "IMP", "EMER", "AMB", "AMB"]  # weighted toward outpatient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _random_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def _fhir_dt(d: date) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _fhir_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Resource builders
# ---------------------------------------------------------------------------

def build_patient(patient_id: str) -> dict[str, Any]:
    birth = _random_date(date(1940, 1, 1), date(1975, 12, 31))
    gender = random.choice(["male", "female"])
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [{"system": "urn:oid:2.16.840.1.113883.4.3", "value": fake.numerify("MRN#######")}],
        "name": [{"family": fake.last_name(), "given": [fake.first_name()]}],
        "gender": gender,
        "birthDate": _fhir_date(birth),
        "address": [{
            "line": [fake.street_address()],
            "city": fake.city(),
            "state": fake.state_abbr(),
            "postalCode": fake.zipcode(),
            "country": "US",
        }],
        "telecom": [{"system": "phone", "value": fake.phone_number(), "use": "home"}],
        "extension": [
            {
                "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
                "valueString": random.choice(["White", "Black or African American", "Asian", "Hispanic or Latino", "Other"]),
            },
            {
                "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
                "valueString": random.choice(["Hispanic or Latino", "Not Hispanic or Latino"]),
            },
        ],
    }


def build_organization(org_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Organization",
        "id": org_id,
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": fake.numerify("##########")}],
        "name": fake.company() + " Medical Center",
        "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type", "code": "prov", "display": "Healthcare Provider"}]}],
        "address": [{"line": [fake.street_address()], "city": fake.city(), "state": fake.state_abbr(), "postalCode": fake.zipcode()}],
        "telecom": [{"system": "phone", "value": fake.phone_number()}],
    }


def build_practitioner(provider_id: str) -> dict[str, Any]:
    gender = random.choice(["male", "female"])
    specialty = random.choice(["207Q00000X", "207R00000X", "208000000X", "207RC0000X", "207RG0100X"])
    return {
        "resourceType": "Practitioner",
        "id": provider_id,
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": fake.numerify("##########")}],
        "name": [{"family": fake.last_name(), "given": [fake.first_name()], "prefix": ["Dr."]}],
        "gender": gender,
        "qualification": [{"code": {"coding": [{"system": "http://nucc.org/provider-taxonomy", "code": specialty}]}}],
    }


def build_encounter(encounter_id: str, patient_id: str, provider_id: str, org_id: str) -> dict[str, Any]:
    enc_class = random.choice(_ENCOUNTER_CLASSES)
    start_dt  = _random_date(date(2020, 1, 1), date(2024, 12, 1))
    duration  = timedelta(hours=random.randint(1, 72) if enc_class == "IMP" else random.randint(1, 4))
    end_dt    = start_dt + duration
    icd, desc = random.choice(_ICD10)
    return {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": enc_class},
        "type": [{"coding": [{"system": "http://snomed.info/sct", "code": "11429006", "display": "Consultation"}]}],
        "subject": {"reference": f"Patient/{patient_id}"},
        "participant": [{"individual": {"reference": f"Practitioner/{provider_id}"}}],
        "serviceProvider": {"reference": f"Organization/{org_id}"},
        "period": {"start": _fhir_dt(start_dt), "end": _fhir_dt(end_dt)},
        "reasonCode": [{"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": icd, "display": desc}]}],
        "extension": [{"url": "totalCost", "valueMoney": {"value": round(random.uniform(200, 15000), 2), "currency": "USD"}}],
    }


def build_condition(condition_id: str, patient_id: str, encounter_id: str) -> dict[str, Any]:
    idx       = random.randint(0, len(_ICD10) - 1)
    icd_code, icd_desc   = _ICD10[idx]
    sno_code, sno_display = _SNOMED[idx]
    onset = _random_date(date(2015, 1, 1), date(2023, 12, 31))
    abatement = _random_date(onset + timedelta(days=30), date(2024, 12, 31)) if random.random() < 0.3 else None
    return {
        "resourceType": "Condition",
        "id": condition_id,
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active" if not abatement else "resolved"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
        "code": {"coding": [
            {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": icd_code, "display": icd_desc},
            {"system": "http://snomed.info/sct",             "code": sno_code, "display": sno_display},
        ]},
        "subject":   {"reference": f"Patient/{patient_id}"},
        "encounter":  {"reference": f"Encounter/{encounter_id}"},
        "onsetDateTime": _fhir_date(onset),
        **({"abatementDateTime": _fhir_date(abatement)} if abatement else {}),
    }


def build_observation(obs_id: str, patient_id: str, encounter_id: str, obs_type: str = "lab") -> dict[str, Any]:
    pool = _LAB_LOINC if obs_type == "lab" else _VITAL_LOINC
    code, display, low, high, unit = random.choice(pool)
    value = round(random.uniform(low * 0.8, high * 1.2), 2)
    interp = "N" if low <= value <= high else ("H" if value > high else "L")
    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                   "code": "laboratory" if obs_type == "lab" else "vital-signs"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
        "subject":          {"reference": f"Patient/{patient_id}"},
        "encounter":         {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": _fhir_dt(_random_date(date(2020, 1, 1), date(2024, 12, 31))),
        "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
        "referenceRange": [{"low": {"value": low, "unit": unit}, "high": {"value": high, "unit": unit}}],
        "interpretation": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": interp}]}],
    }


def build_medication_request(med_id: str, patient_id: str, encounter_id: str, provider_id: str) -> dict[str, Any]:
    rxnorm, display, instructions, dose_val, dose_unit = random.choice(_RXNORM_DRUGS)
    authored = _fhir_date(_random_date(date(2020, 1, 1), date(2024, 12, 31)))
    return {
        "resourceType": "MedicationRequest",
        "id": med_id,
        "status": random.choice(["active", "active", "active", "stopped"]),
        "intent": "order",
        "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": rxnorm, "display": display}]},
        "subject":   {"reference": f"Patient/{patient_id}"},
        "encounter":  {"reference": f"Encounter/{encounter_id}"},
        "requester":  {"reference": f"Practitioner/{provider_id}"},
        "authoredOn": authored,
        "dosageInstruction": [{"text": instructions, "doseAndRate": [{"doseQuantity": {"value": dose_val, "unit": dose_unit}}]}],
    }


def build_procedure(proc_id: str, patient_id: str, encounter_id: str) -> dict[str, Any]:
    cpt, desc = random.choice(_CPT_PROCEDURES)
    icd, icd_desc = random.choice(_ICD10)
    return {
        "resourceType": "Procedure",
        "id": proc_id,
        "status": "completed",
        "code": {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": cpt, "display": desc}]},
        "subject":           {"reference": f"Patient/{patient_id}"},
        "encounter":          {"reference": f"Encounter/{encounter_id}"},
        "performedDateTime":  _fhir_dt(_random_date(date(2020, 1, 1), date(2024, 12, 31))),
        "reasonCode": [{"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": icd, "display": icd_desc}]}],
        "extension": [{"url": "procedureCost", "valueMoney": {"value": round(random.uniform(100, 5000), 2), "currency": "USD"}}],
    }


def build_allergy_intolerance(allergy_id: str, patient_id: str) -> dict[str, Any]:
    code, substance, reaction, severity = random.choice(_ALLERGIES)
    return {
        "resourceType": "AllergyIntolerance",
        "id": allergy_id,
        "clinicalStatus":      {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
        "verificationStatus":  {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "confirmed"}]},
        "type": random.choice(["allergy", "intolerance"]),
        "category": [random.choice(["food", "medication", "environment"])],
        "criticality": random.choice(["low", "high", "unable-to-assess"]),
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": substance}]},
        "patient":      {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": _fhir_date(_random_date(date(2000, 1, 1), date(2020, 12, 31))),
        "reaction": [{"manifestation": [{"coding": [{"display": reaction}]}], "severity": severity}],
    }


def build_immunization(imm_id: str, patient_id: str) -> dict[str, Any]:
    cvx, vaccine_name = random.choice(_VACCINES)
    return {
        "resourceType": "Immunization",
        "id": imm_id,
        "status": "completed",
        "vaccineCode": {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": cvx, "display": vaccine_name}]},
        "patient":            {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": _fhir_date(_random_date(date(2010, 1, 1), date(2024, 12, 31))),
        "lotNumber":    fake.bothify("LOT-????-####"),
        "primarySource": True,
    }


# ---------------------------------------------------------------------------
# Bundle assembler
# ---------------------------------------------------------------------------

def generate_bundle(patient_id: str | None = None) -> dict[str, Any]:
    """Assemble a FHIR R4 Bundle (type: collection) for one patient."""
    patient_id   = patient_id or _uid()
    org_id       = _uid()
    provider_id  = _uid()
    encounter_id = _uid()

    resources = [
        build_patient(patient_id),
        build_organization(org_id),
        build_practitioner(provider_id),
        build_encounter(encounter_id, patient_id, provider_id, org_id),
        build_condition(_uid(), patient_id, encounter_id),
        build_condition(_uid(), patient_id, encounter_id),
        build_observation(_uid(), patient_id, encounter_id, "lab"),
        build_observation(_uid(), patient_id, encounter_id, "lab"),
        build_observation(_uid(), patient_id, encounter_id, "vital"),
        build_medication_request(_uid(), patient_id, encounter_id, provider_id),
        build_medication_request(_uid(), patient_id, encounter_id, provider_id),
        build_procedure(_uid(), patient_id, encounter_id),
        build_allergy_intolerance(_uid(), patient_id),
        build_immunization(_uid(), patient_id),
        build_immunization(_uid(), patient_id),
    ]

    return {
        "resourceType": "Bundle",
        "id": patient_id,
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "entry": [{"resource": r} for r in resources],
    }


# ---------------------------------------------------------------------------
# JSON write helper
# ---------------------------------------------------------------------------

def write_bundle(bundle: dict[str, Any], filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic FHIR R4 EHR bundle JSON files.")
    parser.add_argument("--patients", type=int, default=500, help="Number of patient bundles to generate")
    parser.add_argument("--output",   type=str, default="./data/raw/ehr/", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    print(f"Generating {args.patients} FHIR bundles → {args.output}")

    for i in range(args.patients):
        bundle = generate_bundle()
        pid    = bundle["id"]
        write_bundle(bundle, os.path.join(args.output, f"fhir_bundle_{pid}.json"))

    print(f"Done. {args.patients} bundles written.")


if __name__ == "__main__":
    main()
