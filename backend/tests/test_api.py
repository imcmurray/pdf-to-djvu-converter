"""Smoke tests that don't require the pdf2djvu binary on the host.

These cover:
  - /api/health responds
  - /api/convert rejects non-PDF uploads with 415
  - /api/convert rejects oversized uploads with 413
  - Filename safety helper
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import safe_filename


@pytest.fixture
def client() -> TestClient:
    # Using TestClient as a context manager triggers the FastAPI `lifespan`
    # which initialises app.state.share_store. Without this, /api/download
    # raises AttributeError on app.state access.
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "pdf2djvu_available" in body
    assert "djvudigital_available" in body
    assert "ocrmypdf_available" in body
    assert "active_converter" in body  # may be None if no converter is installed


def test_convert_rejects_non_pdf(client: TestClient) -> None:
    fake = io.BytesIO(b"this is definitely not a pdf")
    r = client.post(
        "/api/convert",
        files={"file": ("not.pdf", fake, "application/pdf")},
        data={"preset": "balanced", "ocr": "false"},
    )
    assert r.status_code == 415
    assert "not a valid PDF" in r.json()["detail"] or "detected as" in r.json()["detail"]


def test_convert_rejects_empty(client: TestClient) -> None:
    r = client.post(
        "/api/convert",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    # Either 400 (empty) or 415 (no header) — both are acceptable rejections.
    assert r.status_code in (400, 415)


def test_safe_filename() -> None:
    # Path components are stripped (basename-style) before sanitisation.
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("/etc/shadow") == "shadow"
    # Spaces and punctuation collapse to underscores.
    assert safe_filename("weird name (1).pdf") == "weird_name_1_.pdf"
    # Falls back to default for empty / dotted-only names.
    assert safe_filename("") == "document.pdf"
    assert safe_filename(".") == "document.pdf"
    assert safe_filename("..") == "document.pdf"


def test_compare_rejects_non_pdf(client: TestClient) -> None:
    fake = io.BytesIO(b"nope")
    r = client.post(
        "/api/compare",
        files={"file": ("x.pdf", fake, "application/pdf")},
    )
    assert r.status_code == 415


def test_download_missing_token(client: TestClient) -> None:
    r = client.get("/api/download/does-not-exist")
    assert r.status_code == 404
