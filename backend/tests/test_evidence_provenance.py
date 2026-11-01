"""Tests for Evidence Collection and Provenance (Module 2).

Verifies:
1. Structured evidence recording with SHA-256, pHash, and dHash calculation.
2. Exact duplicate evidence detection via SHA-256.
3. Near-duplicate evidence detection via perceptual image hashing.
4. Device event ID and timestamp recording.
5. Honest geolocation provenance (strictly labeling device-reported coordinates as unverified).
"""

import io
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.models import Application, Institution, User
from pramana.offline.evidence import (
    analyze_evidence_payload,
    detect_evidence_duplicates,
    record_field_evidence,
)
from pramana.offline.models import FieldInspectionCase, InspectionEvidence


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Seed minimal institution, application, and inspection case
        inst = Institution(id="INST-0001", aicte_id="1-0001", name="Test Engineering College")
        session.add(inst)
        app = Application(id="APP-2026-000101", institution_id="INST-0001", category="Engineering", academic_year="2026-27")
        session.add(app)
        user = User(id="usr-officer", username="officer_patil", role="officer", display_name="Officer Patil", password_hash="hash")
        session.add(user)
        
        insp = FieldInspectionCase(
            id="ins-test-01",
            case_number="INSP-2026-000101-01",
            application_id="APP-2026-000101",
            institution_id="INST-0001",
            assigned_officer_id="usr-officer",
            status="in_progress",
        )
        session.add(insp)
        session.commit()
        yield session


def _create_test_image(color=(200, 100, 50), text="Original"):
    img = Image.new("RGB", (200, 200), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_evidence_payload_fingerprinting():
    """Test 1: Payload analysis computes SHA-256, pHash, and dHash."""
    img_bytes = _create_test_image()
    res = analyze_evidence_payload(img_bytes, mime_type="image/jpeg")
    
    assert "sha256" in res
    assert len(res["sha256"]) == 64
    assert res["phash"] is not None
    assert res["dhash"] is not None
    assert res["size_bytes"] == len(img_bytes)


def test_record_evidence_with_honest_geolocation(memory_db):
    """Test 2: Records evidence and strictly marks device-reported GPS as unverified."""
    img_bytes = _create_test_image()
    
    # Record with coordinates
    evd = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="image",
        file_reference="campus_gate.jpg",
        file_bytes=img_bytes,
        mime_type="image/jpeg",
        description="Main entrance gate photograph",
        location_geo={"latitude": 19.0760, "longitude": 72.8777, "accuracy_meters": 4.5},
        device_metadata={"tablet_os": "Android 15"},
    )
    
    assert evd.id.startswith("evd_")
    assert evd.verification_status == "verified_valid"
    assert evd.metadata_json["geo"]["status"] == "device_reported"
    assert evd.metadata_json["geo"]["verification"] == "device_reported_unverified"
    assert evd.metadata_json["geo"]["latitude"] == 19.0760
    assert evd.device_event_id.startswith("dev-evt-")


def test_record_evidence_without_location(memory_db):
    """Test 3: Does not fabricate location when location is not available."""
    doc_bytes = b"%PDF-1.4 Official Affidavit Document"
    evd = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="document",
        file_reference="land_affidavit.pdf",
        file_bytes=doc_bytes,
        mime_type="application/pdf",
        description="Physical land affidavit copy",
        location_geo=None,
    )
    
    assert evd.metadata_json["geo"]["status"] == "no_location_reported"
    assert evd.metadata_json["geo"]["latitude"] is None


def test_exact_duplicate_evidence_detection(memory_db):
    """Test 4: Detects exact byte-for-byte duplicate evidence."""
    img_bytes = _create_test_image()
    
    # First upload
    evd1 = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="image",
        file_reference="lab_photo_1.jpg",
        file_bytes=img_bytes,
        mime_type="image/jpeg",
        description="First upload",
    )
    assert evd1.verification_status == "verified_valid"
    
    # Second upload of identical bytes
    evd2 = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="image",
        file_reference="lab_photo_duplicate.jpg",
        file_bytes=img_bytes,
        mime_type="image/jpeg",
        description="Second upload with identical bytes",
    )
    
    assert evd2.verification_status == "duplicate_flagged"
    duplicates = evd2.metadata_json["duplicates"]
    assert len(duplicates) >= 1
    assert duplicates[0]["match_type"] == "EXACT_HASH_MATCH"
    assert duplicates[0]["existing_evidence_id"] == evd1.id


def test_perceptual_duplicate_evidence_detection(memory_db):
    """Test 5: Detects re-saved or re-compressed near-duplicate image evidence."""
    img = Image.new("RGB", (300, 300), color=(120, 180, 240))
    buf1 = io.BytesIO()
    img.save(buf1, format="JPEG", quality=95)
    bytes1 = buf1.getvalue()
    
    # Save same visual image with slightly different quality (different SHA-256, matching pHash)
    buf2 = io.BytesIO()
    img.save(buf2, format="JPEG", quality=85)
    bytes2 = buf2.getvalue()
    
    assert bytes1 != bytes2  # Different byte representations
    
    evd1 = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="image",
        file_reference="server_rack_q95.jpg",
        file_bytes=bytes1,
        mime_type="image/jpeg",
        description="Original high quality photo",
    )
    assert evd1.verification_status == "verified_valid"
    
    evd2 = record_field_evidence(
        db=memory_db,
        inspection_id="ins-test-01",
        institution_id="INST-0001",
        officer_id="officer_patil",
        category="image",
        file_reference="server_rack_q85.jpg",
        file_bytes=bytes2,
        mime_type="image/jpeg",
        description="Re-compressed photo of same server rack",
    )
    
    assert evd2.verification_status == "duplicate_flagged"
    duplicates = evd2.metadata_json["duplicates"]
    assert any(d["match_type"] == "PERCEPTUAL_NEAR_DUPLICATE" for d in duplicates)
