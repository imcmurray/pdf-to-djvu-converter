"""Pydantic models used in API responses."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Preset(str, Enum):
    fast = "fast"
    balanced = "balanced"
    high_quality = "high-quality"
    max_compression = "max-compression"


class CompareResult(BaseModel):
    pdf_bytes: int = Field(..., description="Size of the input PDF in bytes.")
    djvu_bytes: int = Field(..., description="Size of the output DjVu in bytes.")
    compression_ratio: float = Field(..., description="pdf_bytes / djvu_bytes (1.0 = no change).")
    size_reduction_pct: float = Field(..., description="100 * (1 - djvu/pdf). Negative = output grew.")
    pages: int = Field(..., ge=0, description="Number of pages in the source PDF.")
    preset: Preset
    ocr: bool = Field(..., description="True if OCR ran during the conversion.")
    duration_ms: int = Field(..., ge=0, description="Wall-clock conversion time in milliseconds.")
    share_url: Optional[str] = Field(
        None,
        description="Tokenised URL for downloading the DjVu; present when `share=true` "
                    "or when the conversion was stored by the streaming endpoint.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pdf_bytes": 4837120,
                    "djvu_bytes": 712384,
                    "compression_ratio": 6.79,
                    "size_reduction_pct": 85.27,
                    "pages": 24,
                    "preset": "balanced",
                    "ocr": False,
                    "duration_ms": 3421,
                    "share_url": "http://localhost:8000/api/download/abcDEF123456",
                },
                {
                    "pdf_bytes": 48840,
                    "djvu_bytes": 93430,
                    "compression_ratio": 0.52,
                    "size_reduction_pct": -91.31,
                    "pages": 1,
                    "preset": "balanced",
                    "ocr": True,
                    "duration_ms": 6987,
                    "share_url": None,
                },
            ]
        }
    )


class BatchItemResult(BaseModel):
    filename: str = Field(..., description="Sanitised input filename.")
    success: bool
    error: Optional[str] = Field(None, description="Failure detail; null on success.")
    result: Optional[CompareResult] = Field(None, description="Per-file metadata on success.")


class BatchResult(BaseModel):
    items: list[BatchItemResult]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "filename": "chapter01.pdf",
                            "success": True,
                            "error": None,
                            "result": {
                                "pdf_bytes": 4200000,
                                "djvu_bytes": 612000,
                                "compression_ratio": 6.86,
                                "size_reduction_pct": 85.43,
                                "pages": 18,
                                "preset": "balanced",
                                "ocr": False,
                                "duration_ms": 2987,
                                "share_url": "http://localhost:8000/api/download/aaa",
                            },
                        },
                        {
                            "filename": "broken.pdf",
                            "success": False,
                            "error": "Upload exceeds the 100 MB limit.",
                            "result": None,
                        },
                    ]
                }
            ]
        }
    )


class HealthResult(BaseModel):
    status: str = "ok"
    version: str
    pdf2djvu_available: bool
    djvudigital_available: bool
    img2djvu_available: bool = Field(
        ..., description="Universal fallback: pdftoppm + c44 + djvm are installed."
    )
    ocrmypdf_available: bool
    active_converter: Optional[str] = Field(
        None, description="The converter actually used: pdf2djvu | djvudigital | pdftoppm+c44."
    )
    available_converters: list[str] = Field(default_factory=list)
    ocr_engine_preference: str = Field(
        "auto", description="Configured preference: auto | tesseract | easyocr."
    )
    ocr_engine_active: str = Field(
        "tesseract", description="Engine that will actually run."
    )
    easyocr_available: bool = Field(
        False, description="True if the easyocr Python package is importable."
    )
    gpu_available: bool = Field(
        False, description="True if torch detects a CUDA-capable device."
    )
    gpu_info: Optional[str] = Field(
        None, description="Human-readable GPU description, e.g. 'NVIDIA RTX 3050 (6 GB)'."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "pdf2djvu_available": False,
                    "djvudigital_available": True,
                    "img2djvu_available": True,
                    "ocrmypdf_available": True,
                    "active_converter": "pdftoppm+c44",
                    "available_converters": ["pdftoppm+c44"],
                    "ocr_engine_preference": "auto",
                    "ocr_engine_active": "easyocr",
                    "easyocr_available": True,
                    "gpu_available": True,
                    "gpu_info": "NVIDIA GeForce RTX 3050 (6 GB)",
                }
            ]
        }
    )


# --------------------------------------------------------------------------- #
# Documentation-only models for the ndjson stream events. These aren't used in
# response_model — the route returns StreamingResponse — but they appear in
# the OpenAPI schema so Swagger users can see the event shapes.
# --------------------------------------------------------------------------- #
class ProgressEvent(BaseModel):
    """One line emitted by the `POST /api/convert` ndjson stream.

    Each line is a single JSON object terminated by `\\n`. The `stage` field
    identifies the type; other fields are optional and stage-specific.
    """
    stage: str = Field(
        ...,
        description=(
            "One of: preflight, ocr, ocr_done, render, encode, assemble, "
            "textlayer, convert, done, error."
        ),
    )
    message: Optional[str] = Field(None, description="Human-readable status text.")
    current: Optional[int] = Field(None, description="Items processed so far in this stage.")
    total: Optional[int] = Field(None, description="Total items in this stage.")
    codec: Optional[str] = Field(None, description="On `encode` events: 'cjb2' or 'c44'.")
    engine: Optional[str] = Field(None, description="On `ocr` events: 'tesseract' or 'easyocr'.")
    pages: Optional[int] = Field(None, description="On `ocr_done`: pages OCR'd.")
    share_token: Optional[str] = Field(None, description="On `done`: token for /api/download/{token}.")
    filename: Optional[str] = Field(None, description="On `done`: suggested .djvu filename.")
    result: Optional[CompareResult] = Field(None, description="On `done`: final compare metadata.")
    ocr_engine: Optional[str] = Field(None, description="On `done`: engine that actually ran.")
    error: Optional[str] = Field(None, description="On `error`: failure detail.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"stage": "preflight", "message": "Using converter: pdftoppm+c44"},
                {"stage": "ocr", "engine": "easyocr", "message": "Running OCR with easyocr…"},
                {"stage": "encode", "current": 12, "total": 166, "codec": "cjb2",
                 "message": "Encoded page 12 of 166 (cjb2)"},
                {"stage": "textlayer", "message": "Embedding OCR text layer…"},
                {
                    "stage": "done",
                    "share_token": "abcDEF123456",
                    "filename": "scan-of-book.djvu",
                    "ocr_engine": "easyocr",
                    "result": {
                        "pdf_bytes": 592_300,
                        "djvu_bytes": 4_120_000,
                        "compression_ratio": 0.14,
                        "size_reduction_pct": -595.4,
                        "pages": 166,
                        "preset": "balanced",
                        "ocr": True,
                        "duration_ms": 148_321,
                    },
                },
                {"stage": "error", "error": "ocrmypdf failed: ..."},
            ]
        }
    )


class BornDigitalInspection(BaseModel):
    """Embedded inside the 409 body from `POST /api/convert`."""
    pages: int
    bytes_per_page: float
    text_chars_per_page: float
    reason: str


class BornDigitalDetail(BaseModel):
    """Schema of the `detail` field of the 409 response."""
    code: str = Field("BORN_DIGITAL_PDF")
    message: str
    inspection: BornDigitalInspection
    hint: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "BORN_DIGITAL_PDF",
                    "message": (
                        "This PDF appears to be born-digital (vector text, not "
                        "a scan). Converting to DjVu will almost certainly "
                        "INCREASE the file size and lose vector quality."
                    ),
                    "inspection": {
                        "pages": 12,
                        "bytes_per_page": 18_400.0,
                        "text_chars_per_page": 1_840.0,
                        "reason": (
                            "avg 18 KB/page and ~1840 text chars/page — looks "
                            "like vector text, not a scan"
                        ),
                    },
                    "hint": "Resubmit with force_born_digital=true to override.",
                }
            ]
        }
    )
