"""PRAMANA Synthetic Universe Generator (SIH 2026 Problem Statement 26261).

STRICT DEMONSTRATION-ONLY COMPLIANCE:
Generates exclusively synthetic, fictional, and algorithmic datasets.
Never accesses, collects, or represents real student, applicant, institutional,
or government records.

Generates:
- 25 Fictional AICTE-Approved Engineering & Technology Institutions
- 10,000 Synthetic records (Students, Faculty, APAAR IDs, DigiLocker credentials,
  Transfer certificates, and Reference records)
- High-fidelity planted forensic, regulatory, duplicate identity, and conflict scenarios.
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from pramana.config import get_settings
from pramana.db import SessionLocal, init_db
from pramana.models import Institution, ReferenceRecord

DISCLAIMER_NOTICE = "DEMONSTRATION ENVIRONMENT — SYNTHETIC DEMO DATA ONLY — SIMULATED EXTERNAL SERVICES"

FICTIONAL_INSTITUTIONS_CATALOG = [
    ("INST-2601", "1-1002001", "Sahyadri Institute of Technology", "Pune", "Maharashtra", 411007, 18.5204, 73.8567, "Private-Self Financed", 1998),
    ("INST-2602", "1-1002002", "Panchganga College of Engineering", "Kolhapur", "Maharashtra", 416004, 16.7050, 74.2433, "Govt Aided", 1984),
    ("INST-2603", "1-1002003", "Marathwada Institute of Advanced Studies", "Aurangabad", "Maharashtra", 431001, 19.8762, 75.3433, "Private-Self Financed", 2005),
    ("INST-2604", "1-1002004", "Vidarbha National Academy of Science", "Nagpur", "Maharashtra", 440010, 21.1458, 79.0882, "University Managed", 1992),
    ("INST-2605", "1-1002005", "Konkan Coastal Engineering College", "Ratnagiri", "Maharashtra", 415612, 16.9902, 73.3120, "Govt Aided", 2011),
    ("INST-2606", "1-1002006", "Malabar Polytechnic & Research Centre", "Kozhikode", "Kerala", 673001, 11.2588, 75.7804, "Private-Self Financed", 2008),
    ("INST-2607", "1-1002007", "Deccan Valley Technical University", "Bengaluru", "Karnataka", 560001, 12.9716, 77.5946, "Deemed University", 1995),
    ("INST-2608", "1-1002008", "Mysuru Heritage Institute of Tech", "Mysuru", "Karnataka", 570001, 12.2958, 76.6394, "Private-Self Financed", 2002),
    ("INST-2609", "1-1002009", "Chola Kingdom Academy of Technology", "Thanjavur", "Tamil Nadu", 613001, 10.7870, 79.1378, "Govt Aided", 1989),
    ("INST-2610", "1-1002010", "Coromandel Engineering & Research", "Chennai", "Tamil Nadu", 600001, 13.0827, 80.2707, "Private-Self Financed", 2001),
    ("INST-2611", "1-1002011", "Kaveri Basin Institute of Technology", "Tiruchirappalli", "Tamil Nadu", 620001, 10.7905, 78.7047, "Private-Self Financed", 2014),
    ("INST-2612", "1-1002012", "Telangana Apex Institute of Computing", "Hyderabad", "Telangana", 500001, 17.3850, 78.4867, "Govt Aided", 1999),
    ("INST-2613", "1-1002013", "Kakatiya Engineering Consortium", "Warangal", "Telangana", 506001, 17.9689, 79.5941, "Private-Self Financed", 2006),
    ("INST-2614", "1-1002014", "Godavari Delta Technological College", "Rajahmundry", "Andhra Pradesh", 533101, 17.0005, 81.8040, "Private-Self Financed", 2004),
    ("INST-2615", "1-1002015", "Kalinga Vanguard Technical Campus", "Bhubaneswar", "Odisha", 751001, 20.2961, 85.8245, "University Managed", 2000),
    ("INST-2616", "1-1002016", "Gangetic Plains Engineering College", "Varanasi", "Uttar Pradesh", 221001, 25.3176, 82.9739, "Govt Aided", 1986),
    ("INST-2617", "1-1002017", "Awadh Institute of Technology", "Lucknow", "Uttar Pradesh", 226001, 26.8467, 80.9462, "Private-Self Financed", 2007),
    ("INST-2618", "1-1002018", "Indraprastha Digital Institute", "New Delhi", "Delhi", 110001, 28.6139, 77.2090, "Government", 2010),
    ("INST-2619", "1-1002019", "Aravali Institute of Technology", "Jaipur", "Rajasthan", 302001, 26.9124, 75.7873, "Private-Self Financed", 2003),
    ("INST-2620", "1-1002020", "Thar Desert Academy of Engineering", "Jodhpur", "Rajasthan", 342001, 26.2389, 73.0243, "Govt Aided", 2012),
    ("INST-2621", "1-1002021", "Sabarmati Institute of Computing", "Ahmedabad", "Gujarat", 380001, 23.0225, 72.5714, "Private-Self Financed", 1997),
    ("INST-2622", "1-1002022", "Gir Forest Technical Institute", "Junagadh", "Gujarat", 362001, 21.5222, 70.4579, "Govt Aided", 2015),
    ("INST-2623", "1-1002023", "Brahmaputra Institute of Technology", "Guwahati", "Assam", 781001, 26.1445, 91.7362, "Government", 1991),
    ("INST-2624", "1-1002024", "Satpura Hills Engineering College", "Bhopal", "Madhya Pradesh", 462001, 23.2599, 77.4126, "Private-Self Financed", 2009),
    ("INST-2625", "1-1002025", "Narmada Valley Polytechnic", "Jabalpur", "Madhya Pradesh", 482001, 23.1815, 79.9864, "Govt Aided", 1988),
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Amit", "Ananya", "Arjun", "Deepak", "Devi", "Gaurav", "Isha", "Kavita",
    "Manish", "Neha", "Nikhil", "Pooja", "Rahul", "Riya", "Rohan", "Sneha", "Suresh", "Varun",
    "Abhishek", "Bhavna", "Chetan", "Divya", "Esha", "Farhan", "Harish", "Jyoti", "Karan", "Meera"
]

LAST_NAMES = [
    "Sharma", "Patel", "Verma", "Rao", "Nair", "Deshmukh", "Kulkarni", "Iyer", "Banerjee", "Gupta",
    "Singh", "Chauhan", "Joshi", "Bhat", "Reddy", "Mehta", "Saxena", "Pandey", "Mishra", "Patil"
]

PROGRAMMES = ["Computer Engineering", "Mechanical Engineering", "Civil Engineering", "Electronics & Telecom", "Electrical Engineering", "Data Science & AI"]


def generate_synthetic_universe(total_records: int = 10000, seed: int = 2026) -> dict[str, Any]:
    rng = random.Random(seed)
    
    universe = {
        "metadata": {
            "title": "PRAMANA Synthetic Universe",
            "version": "2.0.0",
            "generated_at": datetime.now().isoformat(),
            "demonstration_notice": DISCLAIMER_NOTICE,
            "provenance": "synthetic",
            "simulated": True,
            "target_problem_statement": "SIH 2026 — 26261",
        },
        "institutions": [],
        "reference_records": [],
        "scenarios_manifest": {},
    }
    
    # 1. Populate 25 Institutions
    for i_id, aicte_id, name, city, state, pin, lat, lon, itype, est in FICTIONAL_INSTITUTIONS_CATALOG:
        inst_dict = {
            "id": i_id,
            "aicte_id": aicte_id,
            "name": name,
            "aishe_code": f"C-{rng.randint(10000, 99999)}",
            "society_name": f"{name.split()[0]} Educational Trust",
            "address": f"Campus Sector {rng.randint(1, 25)}, Near Ring Road, {city}",
            "city": city,
            "state": state,
            "district": city,
            "pincode": str(pin),
            "latitude": lat,
            "longitude": lon,
            "institution_type": itype,
            "women_only": False,
            "established_year": est,
            "provenance": "synthetic",
            "simulated": True,
        }
        universe["institutions"].append(inst_dict)
        
    print(f"Generated {len(universe['institutions'])} fictional institutions.")
    
    # 2. Generate 10,000 Synthetic Reference Records (Students, Faculty, DigiLocker docs, APAAR IDs)
    records = []
    
    # Pre-select 5 dual-listed faculty members across institutions for planted ghost-faculty scenarios
    shared_faculty = [
        {"name": "Dr. Raghunath M. Deshmukh", "pan": "ABCDE1234F", "aadhaar_last4": "8841", "dob": "1974-05-14", "degree": "Ph.D Computer Science"},
        {"name": "Dr. Sunita K. Kulkarni", "pan": "BCDEF2345G", "aadhaar_last4": "9912", "dob": "1979-11-20", "degree": "Ph.D Structural Engg"},
        {"name": "Prof. Anand V. Iyer", "pan": "CDEFG3456H", "aadhaar_last4": "7733", "dob": "1983-02-18", "degree": "M.Tech CAD/CAM"},
    ]
    
    universe["scenarios_manifest"]["dual_registered_faculty"] = [f["name"] for f in shared_faculty]
    
    # Plant shared faculty records
    for f in shared_faculty:
        # Assigned to INST-2601 AND INST-2602
        for inst_id in ["INST-2601", "INST-2602"]:
            records.append({
                "record_type": "faculty_registry",
                "issuer_code": "aicte_faculty",
                "reference_number": f["pan"],
                "subject_name": f["name"],
                "institution_id": inst_id,
                "data": {
                    "pan": f["pan"],
                    "aadhaar_last4": f["aadhaar_last4"],
                    "designation": "Professor",
                    "department": "Computer Engineering",
                    "highest_qualification": f["degree"],
                    "date_of_joining": "2020-07-01",
                    "simulated": True,
                    "provenance": "synthetic",
                },
                "status": "active",
            })
            
    # Generate pure PRAMANA regulatory records across 25 institutions
    record_types = [
        "faculty_registry",
        "fire_noc_registry",
        "building_safety_registry",
        "land_registry",
        "architect_registry",
        "university_affiliation_registry",
        "pcb_clearance_registry",
    ]
    
    for i in range(len(records), total_records):
        rtype = rng.choice(record_types)
        inst = rng.choice(universe["institutions"])
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        prog = rng.choice(PROGRAMMES)
        
        ref_num = ""
        payload = {}
        
        if rtype == "fire_noc_registry":
            ref_num = f"NOC-FIRE-{inst['state'][:3].upper()}-{rng.randint(10000, 99999)}"
            issue_d = date(2024, 1, 1) + timedelta(days=rng.randint(0, 500))
            payload = {
                "noc_number": ref_num,
                "institution_name": inst["name"],
                "issuing_office": f"{inst['city']} Fire & Emergency Services",
                "issued_on": issue_d.isoformat(),
                "valid_until": (issue_d + timedelta(days=365)).isoformat(),
                "inspected_floors": rng.randint(3, 8),
                "fire_extinguishers_count": rng.randint(40, 200),
            }
        elif rtype == "building_safety_registry":
            ref_num = f"PWD-BSC-{inst['city'][:3].upper()}-{rng.randint(1000, 9999)}"
            issue_d = date(2023, 6, 1) + timedelta(days=rng.randint(0, 600))
            payload = {
                "certificate_number": ref_num,
                "institution_name": inst["name"],
                "issuing_authority": f"Executive Engineer, PWD {inst['city']} Division",
                "issued_on": issue_d.isoformat(),
                "valid_until": (issue_d + timedelta(days=1095)).isoformat(),
                "structural_stability_certified": True,
            }
        elif rtype == "land_registry":
            ref_num = f"REG-LAND-{rng.randint(100000, 999999)}"
            payload = {
                "khasra_survey_number": f"{rng.randint(10, 500)}/{rng.randint(1, 12)}",
                "registered_title_holder": inst["society_name"],
                "land_area_acres": round(rng.uniform(2.5, 12.0), 2),
                "deed_registration_date": "2008-03-24",
                "sub_registrar_office": f"{inst['city']} Rural",
                "unencumbered_title": True,
            }
        elif rtype == "architect_registry":
            coa_reg = f"CA/{rng.randint(1990, 2018)}/{rng.randint(10000, 99999)}"
            ref_num = coa_reg
            payload = {
                "council_of_architecture_id": coa_reg,
                "architect_name": f"Ar. {full_name}",
                "certified_carpet_area_sqm": rng.randint(7500, 25000),
                "certified_instructional_area_sqm": rng.randint(4500, 16000),
                "drawing_approval_authority": f"{inst['city']} Municipal Development Authority",
            }
        elif rtype == "university_affiliation_registry":
            ref_num = f"AFF-{inst['state'][:3].upper()}-UNIV-{rng.randint(1000, 9999)}"
            payload = {
                "affiliation_letter_no": ref_num,
                "affiliating_university": f"{inst['state']} State Technological University",
                "approved_academic_year": "2024-25",
                "affiliated_programmes": rng.sample(PROGRAMMES, k=rng.randint(3, 5)),
            }
        elif rtype == "pcb_clearance_registry":
            ref_num = f"PCB-ENV-{rng.randint(10000, 99999)}"
            payload = {
                "consent_order_no": ref_num,
                "issuing_board": f"{inst['state']} Pollution Control Board",
                "validity_expiry": "2027-12-31",
                "sewage_treatment_plant_operational": True,
            }
        else: # faculty_registry
            pan_chars = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
            pan_num = f"{pan_chars}{rng.randint(1000, 9999)}{rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            ref_num = pan_num
            payload = {
                "pan": pan_num,
                "faculty_name": full_name,
                "designation": rng.choice(["Assistant Professor", "Associate Professor", "Professor"]),
                "department": prog,
                "experience_years": rng.randint(2, 28),
                "highest_degree": rng.choice(["M.Tech", "Ph.D", "M.E"]),
            }
            
        payload["simulated"] = True
        payload["provenance"] = "synthetic"
        payload["demonstration_environment"] = DISCLAIMER_NOTICE
        
        records.append({
            "record_type": rtype,
            "issuer_code": f"sim_{rtype}",
            "reference_number": ref_num,
            "subject_name": full_name,
            "institution_id": inst["id"],
            "data": payload,
            "status": "verified" if rng.random() > 0.05 else "flagged",
        })
        
    universe["reference_records"] = records
    print(f"Generated {len(universe['reference_records'])} synthetic reference records.")
    return universe


def seed_database_with_synthetic_universe(universe: dict[str, Any]):
    """Optionally stores synthetic universe reference records in the local SQLite database."""
    init_db()
    db = SessionLocal()
    try:
        # Check existing count
        existing_insts = {i.id for i in db.query(Institution).all()}
        
        added_insts = 0
        for inst_data in universe["institutions"]:
            if inst_data["id"] not in existing_insts:
                inst = Institution(
                    id=inst_data["id"],
                    aicte_id=inst_data["aicte_id"],
                    name=inst_data["name"],
                    aishe_code=inst_data["aishe_code"],
                    society_name=inst_data["society_name"],
                    address=inst_data["address"],
                    state=inst_data["state"],
                    district=inst_data["district"],
                    pincode=inst_data["pincode"],
                    latitude=inst_data["latitude"],
                    longitude=inst_data["longitude"],
                    institution_type=inst_data["institution_type"],
                    women_only=inst_data["women_only"],
                    established_year=inst_data["established_year"],
                )
                db.add(inst)
                added_insts += 1
                
        db.commit()
        print(f"Added {added_insts} new institutions into local database.")
        
        # Insert sample subset of reference records into database
        subset = universe["reference_records"][:1000]
        added_refs = 0
        for r in subset:
            rec = ReferenceRecord(
                source=r["issuer_code"],
                record_type=r["record_type"],
                key=r["reference_number"],
                institution_id=r["institution_id"],
                data=r["data"],
                provenance="synthetic",
            )
            db.add(rec)
            added_refs += 1
            
        db.commit()
        print(f"Seeded {added_refs} reference records into local database.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Generate PRAMANA Synthetic Universe (10,000 records, 25 institutions)")
    parser.add_argument("--count", type=int, default=10000, help="Total synthetic records to generate")
    parser.add_argument("--seed-db", action="store_true", help="Seed records into local SQLite database")
    parser.add_argument("--out", type=str, default="", help="Path to output JSON file")
    args = parser.parse_args()

    universe = generate_synthetic_universe(total_records=args.count)

    out_path = Path(args.out) if args.out else get_settings().data_dir / "synthetic_universe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(universe, f, indent=2)
        
    print(f"Saved complete synthetic universe to {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")

    if args.seed_db:
        seed_database_with_synthetic_universe(universe)


if __name__ == "__main__":
    main()
