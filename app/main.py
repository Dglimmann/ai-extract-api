import io
import os
import time
import logging
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    UploadFile,
    File,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.llm import extract_json
from app.auth import require_api_key
from app.usage import check_and_increment, get_usage
from app.logging_middleware import LoggingMiddleware


# --------------------------------------------------
# Config
# --------------------------------------------------

MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.0"))

# Demo / live tester
DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"
DEMO_MAX_FILE_MB = float(os.getenv("DEMO_MAX_FILE_MB", "2"))
DEMO_MAX_FILE_BYTES = int(DEMO_MAX_FILE_MB * 1024 * 1024)

# Rate limiting: X requests in Y seconds
DEMO_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("DEMO_RATE_LIMIT_WINDOW_SECONDS", "60"))
DEMO_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("DEMO_RATE_LIMIT_MAX_REQUESTS", "2"))

# Cleanup factor for stale IP buckets
DEMO_BUCKET_STALE_MULTIPLIER = int(os.getenv("DEMO_BUCKET_STALE_MULTIPLIER", "10"))


# --------------------------------------------------
# App / logging
# --------------------------------------------------

app = FastAPI(title="AI Data Extraction API", version="0.2.0")
logger = logging.getLogger("api")

app.add_middleware(LoggingMiddleware)


# --------------------------------------------------
# CORS
# --------------------------------------------------

origins_raw = os.getenv("CORS_ORIGINS", "").strip()
if origins_raw:
    origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# --------------------------------------------------
# Schemas / models
# --------------------------------------------------

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    schema: Dict[str, Any] = Field(..., description="JSON shape you want back")
    language: Optional[str] = Field(default="de")


class InvoiceExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: Optional[str] = Field(default="de")


class ExtractResponse(BaseModel):
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    model: str


INVOICE_SCHEMA: Dict[str, Any] = {
    "supplier_name": None,
    "invoice_number": None,
    "invoice_date": None,
    "due_date": None,
    "currency": None,
    "total_amount": None,
    "vat_amount": None,
}


# --------------------------------------------------
# In-memory demo rate limiter
# --------------------------------------------------
# Good enough for MVP / single instance Render.
# For multi-instance scaling, move this to Redis / Upstash / KV store.
_demo_hits: Dict[str, Deque[float]] = {}


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _client_ip(request: Request) -> str:
    """
    Best-effort client IP resolution behind proxies / Render.
    """
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        first_ip = x_forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _cleanup_demo_buckets(now: float) -> None:
    """
    Remove empty or very old IP buckets so memory does not grow forever.
    """
    stale_cutoff = now - (DEMO_RATE_LIMIT_WINDOW_SECONDS * DEMO_BUCKET_STALE_MULTIPLIER)
    stale_ips: List[str] = []

    for ip, bucket in _demo_hits.items():
        while bucket and now - bucket[0] > DEMO_RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()

        if not bucket:
            stale_ips.append(ip)
            continue

        if bucket[-1] < stale_cutoff:
            stale_ips.append(ip)

    for ip in stale_ips:
        _demo_hits.pop(ip, None)


def _enforce_demo_rate_limit(request: Request) -> None:
    """
    Allow X requests per Y seconds for the public demo endpoint.
    """
    now = time.monotonic()
    ip = _client_ip(request)

    bucket = _demo_hits.setdefault(ip, deque())

    # Remove timestamps outside the current time window
    while bucket and now - bucket[0] > DEMO_RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= DEMO_RATE_LIMIT_MAX_REQUESTS:
        oldest_relevant = bucket[0]
        retry_after = max(1, int(DEMO_RATE_LIMIT_WINDOW_SECONDS - (now - oldest_relevant)))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Demo rate limit exceeded "
                f"({DEMO_RATE_LIMIT_MAX_REQUESTS} requests / {DEMO_RATE_LIMIT_WINDOW_SECONDS}s). "
                f"Please wait {retry_after} seconds."
            ),
        )

    bucket.append(now)

    # Light cleanup after each request
    _cleanup_demo_buckets(now)


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from a text-based PDF.
    Does not support OCR / scanned image-only PDFs yet.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or unreadable PDF: {e}")

    texts: List[str] = []

    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read PDF page {i + 1}: {e}",
            )

        if page_text.strip():
            texts.append(page_text)

    full_text = "\n".join(texts).strip()

    if not full_text:
        raise HTTPException(
            status_code=422,
            detail=(
                "No extractable text found in PDF. "
                "This demo currently supports text-based PDFs only "
                "(no OCR/scanned PDFs yet)."
            ),
        )

    return full_text


async def _run_extraction(
    text: str,
    schema: Dict[str, Any],
    language: str,
) -> ExtractResponse:
    data, warnings, confidence, model = await extract_json(
        text=text,
        schema=schema,
        language=language or "de",
    )

    if confidence < MIN_CONFIDENCE:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "low_confidence",
                "min_confidence": MIN_CONFIDENCE,
                "confidence": confidence,
                "warnings": warnings,
                "data": data,
            },
        )

    return ExtractResponse(
        data=data,
        warnings=warnings,
        confidence=confidence,
        model=model,
    )


# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.get("/health")
async def health():
    return {
        "ok": True,
        "version": "0.2.0",
        "demo_enabled": DEMO_ENABLED,
        "min_confidence": MIN_CONFIDENCE,
        "demo_rate_limit_window_seconds": DEMO_RATE_LIMIT_WINDOW_SECONDS,
        "demo_rate_limit_max_requests": DEMO_RATE_LIMIT_MAX_REQUESTS,
        "demo_max_file_mb": DEMO_MAX_FILE_MB,
    }


@app.get("/")
async def root():
    return {
        "name": "GL API",
        "status": "online",
        "version": "0.2.0",
        "docs": "/docs",
        "endpoints": [
            "/extract",
            "/extract/invoice",
            "/me/usage",
            "/demo/invoice",
            "/health",
        ],
    }


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest, key_and_meta=Depends(require_api_key)):
    api_key, meta = key_and_meta

    # Per-key usage + limit
    check_and_increment(api_key, meta)

    return await _run_extraction(
        text=req.text,
        schema=req.schema,
        language=req.language or "de",
    )


@app.post("/extract/invoice", response_model=ExtractResponse)
async def extract_invoice(
    req: InvoiceExtractRequest,
    key_and_meta=Depends(require_api_key),
):
    """
    Simpler production endpoint for invoice extraction.
    Clients only send text (+ optional language), no custom schema needed.
    """
    api_key, meta = key_and_meta

    # Per-key usage + limit
    check_and_increment(api_key, meta)

    return await _run_extraction(
        text=req.text,
        schema=INVOICE_SCHEMA,
        language=req.language or "de",
    )


@app.post("/demo/invoice", response_model=ExtractResponse)
async def demo_invoice(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Public demo endpoint for glapi.dev live tester.
    No API key required, but rate-limited and file-size-limited.
    Supports text-based PDFs only.
    """
    if not DEMO_ENABLED:
        raise HTTPException(status_code=404, detail="Demo endpoint is disabled")

    _enforce_demo_rate_limit(request)

    if not file:
        raise HTTPException(status_code=400, detail="Missing file")

    filename = (file.filename or "").lower().strip()
    content_type = (file.content_type or "").lower().strip()

    allowed_types = {
        "application/pdf",
        "application/x-pdf",
    }

    if content_type not in allowed_types and not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

    try:
        pdf_bytes = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read uploaded file")

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(pdf_bytes) > DEMO_MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large. Max size is {DEMO_MAX_FILE_MB:.1f} MB.",
        )

    text = _extract_text_from_pdf_bytes(pdf_bytes)

    # Demo does not consume paid API key quota
    return await _run_extraction(
        text=text,
        schema=INVOICE_SCHEMA,
        language="de",
    )


@app.get("/me/usage")
async def my_usage(key_and_meta=Depends(require_api_key)):
    api_key, meta = key_and_meta
    return get_usage(api_key, meta)