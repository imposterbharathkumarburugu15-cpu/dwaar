"""Regulatory Authority Data Exchange Adapters (AICTE, UGC, NBA)."""

from datetime import UTC, datetime
from typing import Any

from ...crypto import sha256_hex


class RegulatoryAuthorityAdapter:
    """Interfaces with higher education regulatory bodies for accreditation and approval status."""

    def verify_aicte_approval(self, aicte_permanent_id: str, academic_year: str = "2025-2026") -> dict[str, Any]:
        """Queries AICTE central portal for Extension of Approval (EoA) history."""
        req_hash = sha256_hex(f"{aicte_permanent_id}:{academic_year}".encode("utf-8"))
        return {
            "source": "AICTE_CENTRAL_EXCHANGE_SANDBOX",
            "is_simulation": True,
            "aicte_permanent_id": aicte_permanent_id,
            "academic_year": academic_year,
            "approval_status": "APPROVED",
            "eoa_reference": f"F.No. Western/{aicte_permanent_id}/2025/EOA",
            "approved_programs": [
                {"program": "Engineering & Technology", "intake": 420},
                {"program": "Management", "intake": 60},
            ],
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def verify_nba_accreditation(self, program_code: str, institution_code: str) -> dict[str, Any]:
        """Queries National Board of Accreditation for valid program accreditation tier."""
        req_hash = sha256_hex(f"{program_code}:{institution_code}".encode("utf-8"))
        return {
            "source": "NBA_ACCREDITATION_REGISTRY_SANDBOX",
            "is_simulation": True,
            "program_code": program_code,
            "institution_code": institution_code,
            "accreditation_tier": "Tier-I (Washington Accord)",
            "accreditation_status": "ACCREDITED",
            "valid_until": "2028-06-30",
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def verify_ugc_status(self, university_id: str) -> dict[str, Any]:
        """Queries UGC 2(f) and 12(B) recognition status."""
        req_hash = sha256_hex(university_id.encode("utf-8"))
        return {
            "source": "UGC_RECOGNITION_SANDBOX",
            "is_simulation": True,
            "university_id": university_id,
            "section_2f_status": "RECOGNIZED",
            "section_12b_status": "ELIGIBLE_FOR_CENTRAL_ASSISTANCE",
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }


default_regulatory_adapter = RegulatoryAuthorityAdapter()

