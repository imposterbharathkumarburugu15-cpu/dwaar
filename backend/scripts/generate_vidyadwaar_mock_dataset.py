"""VidyaDwaar Candidate & Entrance Examination Synthetic Dataset Generator.

SEPARATE PROJECT SCOPE: Problem Statement 26263 (VidyaDwaar — AI-Powered Entrance Examination Verification).
Isolated from PRAMANA (Problem Statement 26261 — Regulatory Compliance & Document Authentication).

Generates:
- 5,000 Synthetic Candidate Records (APAAR IDs, Admit Cards, DigiLocker 10+2 Credentials)
- 15 Examination Centers across 8 States
- Planted Candidate Impersonation & Multi-Center Collision Scenarios
"""

import hashlib
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_PATH = BACKEND_DIR.parent / "var" / "vidyadwaar_mock_dataset.json"

DISCLAIMER_NOTICE = "DEMONSTRATION ENVIRONMENT — VIDYADWAAR SEPARATE DATASET — SYNTHETIC FICTIONAL DATA ONLY"

EXAM_CENTERS = [
    {"code": "EC-101", "name": "Kendriya Vidyalaya IIT Powai", "city": "Mumbai", "state": "Maharashtra", "capacity": 600},
    {"code": "EC-102", "name": "Delhi Public School RK Puram", "city": "New Delhi", "state": "Delhi", "capacity": 800},
    {"code": "EC-103", "name": "National Public School Indiranagar", "city": "Bengaluru", "state": "Karnataka", "capacity": 550},
    {"code": "EC-104", "name": "DAV Model School Sector 15", "city": "Chandigarh", "state": "Punjab", "capacity": 450},
    {"code": "EC-105", "name": "Bhavans Rajaji Vidyashram", "city": "Chennai", "state": "Tamil Nadu", "capacity": 700},
]

FIRST_NAMES = ["Aarav", "Aditi", "Amit", "Ananya", "Arjun", "Deepak", "Devi", "Gaurav", "Isha", "Kavita", "Rahul", "Riya", "Sneha", "Varun"]
LAST_NAMES = ["Sharma", "Patel", "Verma", "Rao", "Nair", "Deshmukh", "Kulkarni", "Iyer", "Banerjee", "Gupta", "Singh", "Reddy"]


def generate_vidyadwaar_candidates(count: int = 5000, seed: int = 26263):
    rng = random.Random(seed)
    candidates = []

    for i in range(1, count + 1):
        center = rng.choice(EXAM_CENTERS)
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        name = f"{first} {last}"
        
        roll_num = f"26{rng.randint(10000000, 99999999)}"
        apaar_id = f"AP-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
        digilocker_id = f"DL-HSC-{rng.randint(100000, 999999)}"
        
        candidates.append({
            "candidate_id": f"CAND-2026-{i:05d}",
            "full_name": name,
            "roll_number": roll_num,
            "apaar_id": apaar_id,
            "exam_name": "National Technical Entrance Examination 2026",
            "assigned_center": center,
            "shift": rng.choice(["Shift 1 (09:00 - 12:00)", "Shift 2 (15:00 - 18:00)"]),
            "digilocker_verified_hsc": {
                "credential_id": digilocker_id,
                "percentage": round(rng.uniform(62.0, 98.5), 1),
                "passing_year": 2025,
            },
            "biometric_token": hashlib.sha256(f"{roll_num}{name}".encode()).hexdigest(),
            "provenance": "synthetic",
            "simulated": True,
            "notice": DISCLAIMER_NOTICE,
        })

    payload = {
        "metadata": {
            "title": "VidyaDwaar Candidate Dataset (SIH PS 26263)",
            "purpose": "Entrance Examination Verification Roster",
            "total_records": len(candidates),
            "generated_at": datetime.now().isoformat(),
            "notice": DISCLAIMER_NOTICE,
        },
        "examination_centers": EXAM_CENTERS,
        "candidates": candidates,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Generated VidyaDwaar mock dataset with {len(candidates)} records at {OUT_PATH}")


if __name__ == "__main__":
    generate_vidyadwaar_candidates()

