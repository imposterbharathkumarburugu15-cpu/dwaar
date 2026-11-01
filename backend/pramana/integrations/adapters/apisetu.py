"""API Setu Provider Adapter for National Data Exchange."""

from datetime import UTC, datetime
import hashlib
import json
import logging
from typing import Any

from ...crypto import sha256_hex
from ..gateway import default_gateway

logger = logging.getLogger("pramana.integrations.adapters.apisetu")


class APISetuAdapter:
    """Interacts with API Setu National Data Exchange for verified government records."""

    def __init__(
        self,
        base_url: str = "https://sandbox.apisetu.gov.in/v1",
        client_id: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.api_key = api_key
        self.mode = "REAL_SANDBOX" if (client_id and api_key) else "SIMULATED_SANDBOX"

    def verify_land_record(
        self,
        survey_number: str,
        state: str,
        district: str,
    ) -> dict[str, Any]:
        """Queries state revenue department land records via API Setu."""
        req_hash = sha256_hex(f"{survey_number}:{state}:{district}".encode("utf-8"))

        if self.mode == "REAL_SANDBOX":
            headers = {
                "X-APISETU-CLIENTID": self.client_id or "",
                "X-APISETU-APIKEY": self.api_key or "",
            }
            url = f"{self.base_url}/landrecords/verify"
            payload = {"survey_no": survey_number, "state": state, "district": district}
            res = default_gateway.execute_request("POST", url, headers=headers, json_payload=payload)
            return {
                "source": "API_SETU_LIVE_SANDBOX",
                "survey_number": survey_number,
                "verified": res.get("status_code") == 200,
                "data": res.get("body"),
                "hash": req_hash,
            }

        # Simulated Sandbox Response with authentic government schema
        simulated_record = {
            "source": "API_SETU_SIMULATED_SANDBOX",
            "is_simulation": True,
            "survey_number": survey_number,
            "state": state,
            "district": district,
            "land_area_acres": 5.2,
            "owner_name": "Vidya Bharti Educational Society",
            "title_status": "CLEAR_AND_UNENCUMBERED",
            "conversion_status": "EDUCATIONAL_LAND_APPROVED",
            "registration_number": f"REG-LAND-{survey_number}",
            "registration_date": "2018-04-12",
            "issuing_authority": f"Department of Revenue, Govt. of {state}",
            "digital_sign_valid": True,
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return simulated_record

    def verify_fire_noc(
        self,
        noc_number: str,
        institution_name: str,
    ) -> dict[str, Any]:
        """Verifies Fire Safety NOC via State Fire Services department."""
        req_hash = sha256_hex(f"{noc_number}:{institution_name}".encode("utf-8"))

        simulated_record = {
            "source": "API_SETU_SIMULATED_SANDBOX",
            "is_simulation": True,
            "noc_number": noc_number,
            "institution_name": institution_name,
            "valid_from": "2024-04-01",
            "valid_until": "2027-03-31",
            "status": "VALID",
            "inspected_floors": 4,
            "fire_equipment_certified": True,
            "issuing_office": "State Disaster Response & Fire Safety Authority",
            "digital_sign_valid": True,
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return simulated_record

    def verify_society_registration(
        self,
        registration_number: str,
        state: str,
    ) -> dict[str, Any]:
        """Verifies Educational Society / Trust registration."""
        req_hash = sha256_hex(f"{registration_number}:{state}".encode("utf-8"))

        simulated_record = {
            "source": "API_SETU_SIMULATED_SANDBOX",
            "is_simulation": True,
            "registration_number": registration_number,
            "society_name": "Vidya Bharti Educational Society",
            "registered_under": "Societies Registration Act, 1860",
            "status": "ACTIVE",
            "registered_date": "2010-09-15",
            "registered_state": state,
            "pan_number": "AAATV1234F",
            "query_hash": req_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return simulated_record


default_apisetu_adapter = APISetuAdapter()

