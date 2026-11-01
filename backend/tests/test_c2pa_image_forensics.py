"""Comprehensive test suite for C2PA Content Credentials and Image Forensics.

Tests:
1. Valid C2PA manifest (cryptographically verified provenance)
2. Missing C2PA manifest (neutral, missing provenance, never flagged as forgery)
3. Modified image after C2PA signing (tampered payload, hash mismatch)
4. Invalid/corrupted C2PA manifest (unverified/malformed structure)
5. Reused image detection via pHash and dHash (heuristic image similarity)
6. Unsupported/non-image format handling
7. Distinct provenance classification reporting
"""

from datetime import datetime, timedelta, timezone
import io
import pytest
from PIL import Image, ImageDraw
from cryptography.hazmat.primitives import serialization

from pramana.photos import credentials, demo_capture
from pramana.photos.findings import credential_status
from pramana.verification import base as vb
from pramana.forensics import fingerprints

IST = timezone(timedelta(hours=5, minutes=30))


def _make_image(size=(640, 480), color=(100, 150, 200)) -> bytes:
    im = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(im)
    draw.rectangle([50, 50, 250, 250], fill=(20, 40, 60))
    draw.text((60, 60), "Pramana Computer Lab", fill=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture(scope="module")
def ca_device():
    ca = demo_capture.build_ca()
    dev = demo_capture.device(ca, "Field Camera 01 (DEMO)", "Pramana Test Authority (DEMO)")
    ca_pem = ca[0].public_bytes(serialization.Encoding.PEM).decode()
    return ca_pem, dev


def test_c2pa_valid_cryptographic_provenance(monkeypatch, ca_device):
    """Test 1: Valid C2PA manifest achieves cryptographically verified provenance."""
    ca_pem, dev = ca_device
    monkeypatch.setattr(credentials, "_trust_pem", lambda: ca_pem)

    raw_img = _make_image()
    signed = demo_capture.sign_jpeg(raw_img, dev, "lab_photo.jpg", datetime(2026, 3, 15, 10, 0, tzinfo=IST))

    parsed = credentials.read(signed, "image/jpeg")
    assert parsed["present"] is True
    assert parsed["readable"] is True
    assert parsed["signature_valid"] is True
    assert parsed["trusted"] is True
    assert parsed["hash_matches"] is True
    assert parsed["signer"]["common_name"] == "Field Camera 01 (DEMO)"

    status, detail, _ = credential_status(parsed)
    assert status == vb.VERIFIED
    assert "DEMO" in detail
    assert "signed by" in detail


def test_c2pa_missing_provenance_is_never_forgery():
    """Test 2: Missing C2PA manifest is neutral missing provenance, NOT proof of forgery."""
    raw_img = _make_image()
    parsed = credentials.read(raw_img, "image/jpeg")

    assert parsed["present"] is False
    assert parsed.get("readable") is not True

    status, detail, _ = credential_status(parsed)
    assert status == vb.MANUAL_REVIEW or status is None
    # Must never describe missing credentials as forged or fraudulent
    assert "forged" not in detail.lower()
    assert "fake" not in detail.lower()
    assert "fraud" not in detail.lower()


def test_c2pa_modified_after_signing_tamper_detection(monkeypatch, ca_device):
    """Test 3: Pixels edited after signing triggers hash mismatch / modified status."""
    ca_pem, dev = ca_device
    monkeypatch.setattr(credentials, "_trust_pem", lambda: ca_pem)

    raw_img = _make_image()
    signed = demo_capture.sign_jpeg(raw_img, dev, "campus.jpg", datetime(2026, 3, 15, 11, 0, tzinfo=IST))

    def modify_pixels(im):
        ImageDraw.Draw(im).rectangle([200, 200, 350, 350], fill=(255, 0, 0))
        return im

    tampered = demo_capture.edit_after_signing(signed, modify_pixels)
    parsed = credentials.read(tampered, "image/jpeg")

    assert parsed["present"] is True
    assert parsed["readable"] is True
    assert parsed["signature_valid"] is True
    assert parsed["hash_matches"] is False

    status, detail, _ = credential_status(parsed)
    assert status == vb.MISMATCH
    assert "modified after capture" in detail


def test_c2pa_invalid_corrupted_manifest():
    """Test 4: Corrupted manifest bytes are detected as unreadable/invalid structure."""
    raw_img = _make_image()
    # Fake a corrupted C2PA header box
    corrupted = raw_img + b"\xff\xeb\x00\x14c2pa_invalid_manifest_bytes"
    parsed = credentials.read(corrupted, "image/jpeg")
    # If unparseable or rejected by parser
    assert parsed["present"] is False or parsed.get("readable") is False


def test_phash_and_dhash_duplicate_detection():
    """Test 5: Image duplicate detection via pHash and dHash."""
    img_data1 = _make_image(color=(120, 140, 180))
    # Slightly resaved/recompressed version of the same image
    im = Image.open(io.BytesIO(img_data1))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=75)
    img_data2 = buf.getvalue()

    # Completely different image
    img_different = _make_image(size=(800, 600), color=(10, 200, 30))

    # Compute fingerprints
    fp1 = fingerprints.compute(img_data1, "image/jpeg", "")
    fp2 = fingerprints.compute(img_data2, "image/jpeg", "")
    fp_diff = fingerprints.compute(img_different, "image/jpeg", "")

    # pHash distance
    p_dist_same = fingerprints.phash_distance(fp1["phash"], fp2["phash"])
    p_dist_diff = fingerprints.phash_distance(fp1["phash"], fp_diff["phash"])
    assert p_dist_same <= 5, "Near-duplicate images must have small pHash distance"
    assert p_dist_diff > 10, "Different images must have large pHash distance"

    # dHash distance
    d_dist_same = fingerprints.dhash_distance(fp1["dhash"], fp2["dhash"])
    d_dist_diff = fingerprints.dhash_distance(fp1["dhash"], fp_diff["dhash"])
    assert d_dist_same <= 6, "Near-duplicate images must have small dHash distance"
    assert d_dist_diff > 12, "Different images must have large dHash distance"


def test_unsupported_image_format_handling():
    """Test 6: Unsupported or arbitrary non-image files are handled gracefully without unhandled exceptions."""
    non_image = b"BM1234567890\x00\x00"
    res = credentials.read(non_image, "image/bmp")
    assert res["readable"] is False
    assert "unsupported" in res.get("error", "").lower() or "notsupported" in res.get("error", "").lower()
