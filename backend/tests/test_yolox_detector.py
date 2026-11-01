"""Unit and integration tests for YOLOX-M object detector and visual room forensics."""

import io
import numpy as np
from PIL import Image, ImageDraw
import pytest

from pramana.photos import detector


def test_yolox_model_availability_and_session():
    """Verify YOLOX-M weights exist in backend/models and session initializes on CPU."""
    assert detector.available() is True, "yolox_m.onnx must be present in models_dir"
    sess = detector._session()
    assert sess is not None
    input_name = sess.get_inputs()[0].name
    assert input_name == "images"


def test_yolox_inference_on_synthetic_photo():
    """Verify YOLOX inference produces normalized bounding boxes and meaningful scores."""
    # Create an image containing a simulated monitor/screen rectangle
    im = Image.new("RGB", (640, 480), (200, 200, 200))
    draw = ImageDraw.Draw(im)
    # Draw screen-like dark rectangle
    draw.rectangle([150, 100, 450, 350], fill=(20, 20, 30))
    # Draw a stand
    draw.rectangle([280, 350, 320, 420], fill=(50, 50, 50))
    buf = io.BytesIO()
    im.save(buf, "JPEG")

    res = detector.analyse(buf.getvalue())
    assert res["status"] == "analysed"
    assert res["model"]["name"] == "YOLOX-M"
    assert res["latency_ms"] > 0
    assert "counts" in res
    assert "room_type" in res

    for det in res["detections"]:
        assert 0.0 <= det["score"] <= 1.0
        assert len(det["box"]) == 4
        # Verify box coordinates are within [0, 1] range
        assert all(0.0 <= coord <= 1.0 for coord in det["box"])


def test_yolox_graceful_fallback_on_corrupted_input():
    """Verify detector reports not_analysed on invalid/corrupted data rather than fabricating."""
    corrupted_bytes = b"NOT_A_VALID_JPEG_IMAGE_DATA_STREAM"
    res = detector.analyse(corrupted_bytes)
    assert res["status"] == "not_analysed"
    assert "reason" in res
    assert len(res["reason"]) > 0


def test_yolox_graceful_fallback_when_model_missing(monkeypatch, tmp_path):
    """Verify detector reports not_analysed with clear explanation if model file is missing."""
    monkeypatch.setattr(detector, "model_path", lambda: tmp_path / "nonexistent_model.onnx")
    detector._session.cache_clear()
    try:
        im = Image.new("RGB", (100, 100), "white")
        b = io.BytesIO()
        im.save(b, "JPEG")
        res = detector.analyse(b.getvalue())
        assert res["status"] == "not_analysed"
        assert "not installed" in res["reason"] or "nonexistent_model" in res["reason"]
    finally:
        detector._session.cache_clear()


def test_room_type_classification_rules():
    """Verify room type determination logic based on object mix counts."""
    # Computer lab: >= 3 workstations
    room, basis = detector.room_reading({"workstation": 15, "seat": 15})
    assert room == "computer_lab"
    assert "15 visible workstations" in basis

    # Classroom: >= 6 seats/tables and <= 1 workstation
    room, basis = detector.room_reading({"seat": 20, "table": 5, "workstation": 0})
    assert room == "classroom"
    assert "20 chairs or benches" in basis

    # Library: >= 12 books
    room, basis = detector.room_reading({"book": 50, "workstation": 2})
    assert room == "library"
    assert "50 books" in basis

    # Unclear: sparse objects
    room, basis = detector.room_reading({"seat": 1})
    assert room == "unclear"

