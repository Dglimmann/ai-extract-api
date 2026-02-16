import os
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

from app.llm import extract_json
from app.auth import require_api_key
from app.usage import check_and_increment, get_usage
from app.logging_middleware import LoggingMiddleware

# Optional: CORS (nur nötig, wenn Browser-Frontend direkt zugreifen soll)
from fastapi.middleware.cors import CORSMiddleware

MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.0"))

app = FastAPI(title="AI Data Extraction API", version="0.1.0")
logger = logging.getLogger("api")

# Middleware
app.add_middleware(LoggingMiddleware)

# OPTIONAL CORS
# Für Produktion: setz CORS_ORIGINS in .env, z.B. "https://deinfrontend.de,https://app.deinfrontend.de"
origins_raw = os.getenv("CORS_ORIGINS", "").strip()
if origins_raw:
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    schema: Dict[str, Any] = Field(..., description="JSON shape you want back")
    language: Optional[str] = Field(default="de")

class ExtractResponse(BaseModel):
    data: Dict[str, Any]
    warnings: List[str] = []
    confidence: float = Field(..., ge=0.0, le=1.0)
    model: str

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest, key_and_meta=Depends(require_api_key)):
    api_key, meta = key_and_meta

    # per-key usage + limit
    check_and_increment(api_key, meta)

    data, warnings, confidence, model = await extract_json(
        text=req.text,
        schema=req.schema,
        language=req.language or "de",
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

@app.get("/me/usage")
async def my_usage(key_and_meta=Depends(require_api_key)):
    api_key, meta = key_and_meta
    return get_usage(api_key, meta)