"""Unit and integration tests for Devanagari (Hindi) OCR pipeline."""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest

from pramana.pipeline import devanagari


def test_devanagari_model_integrity():
    """Verify that the bundled Devanagari PP-OCRv5 model file exists and matches the pinned SHA-256."""
    p = devanagari.model_path()
    assert p is not None, "Devanagari model path must exist in backend/models"
    assert p.name == devanagari.MODEL["name"]
    assert devanagari._sha256(p) == devanagari.MODEL["sha256"]


def test_devanagari_engine_initialization():
    """Verify that RapidOCR initializes with the Devanagari weights."""
    eng = devanagari.engine()
    assert eng is not None, f"Devanagari engine must initialize cleanly: {devanagari.unavailable_reason()}"


def test_devanagari_bilingual_recognition():
    """Verify OCR on a synthetic bilingual image containing Hindi and English text."""
    eng = devanagari.engine()
    assert eng is not None

    font_path = Path("C:/Windows/Fonts/Nirmala.ttc")
    if not font_path.exists():
        pytest.skip("Nirmala font not found on host for bilingual test")

    font = ImageFont.truetype(str(font_path), 28)
    img = Image.new("RGB", (700, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.text((25, 25), "अखिल भारतीय तकनीकी शिक्षा परिषद", fill="black", font=font)
    draw.text((25, 85), "प्रमाण पत्र: AICTE-2026", fill="black", font=font)

    res = devanagari._call(eng, np.array(img))
    lines = devanagari.lines_of(res)
    assert len(lines) >= 2, "Must recognize at least two text lines"

    full_text = " ".join(l["text"] for l in lines)
    assert devanagari.has_devanagari(full_text), "Must identify Devanagari characters in extracted text"
    assert "AICTE" in full_text or "2026" in full_text, "Must extract English alphanumeric tokens"

    # Verify bounding boxes and confidence scores
    for l in lines:
        assert len(l["box"]) == 4, "Line box must have 4 coordinates [x0, y0, x1, y1]"
        assert l["score"] > 0.5, "Line score must be above threshold"
        for w_text, w_box, w_score in l["words"]:
            assert isinstance(w_text, str) and len(w_text) > 0
            assert len(w_box) == 4
            assert w_score > 0.4


def test_text_layer_hint_detection():
    """Verify detection of corrupted Devanagari text layers (PUA code points and reversed vowel marks)."""
    # 1. PUA corrupted text
    pua_words = ["\uE001\uE002", "\uE003\uE004", "NormalText"]
    hint = devanagari.text_layer_hint(pua_words)
    assert hint is not None
    assert "Private Use Area" in hint

    # 2. Vowel sign leading words (visual order encoding)
    sign_words = ["िहन्दी", "िशक्षा", "िवद्या", "सामान्य"]
    hint = devanagari.text_layer_hint(sign_words)
    assert hint is not None
    assert "visual order" in hint

    # 3. Clean standard words
    clean_words = ["Engineering", "College", "AICTE"]
    assert devanagari.text_layer_hint(clean_words) is None

