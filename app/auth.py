import os, json
from typing import Dict, Any, Tuple

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

def _load_keys_config() -> Dict[str, Any]:
    raw = os.getenv("API_KEYS_CONFIG", "").strip()
    if not raw:
        return {}
    try:
        cfg = json.loads(raw)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}

KEYS_CONFIG = _load_keys_config()

# ✅ Swagger erkennt dadurch "Authorize" (Bearer)
security = HTTPBearer(auto_error=False)

def require_api_key(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> Tuple[str, Dict[str, Any]]:
    """
    Expect: Authorization: Bearer <API_KEY>
    Returns: (api_key, meta) where meta includes plan/daily_limit
    """
    if not KEYS_CONFIG:
        raise HTTPException(status_code=500, detail="API_KEYS_CONFIG not configured or invalid JSON")

    if creds is None or (creds.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    key = (creds.credentials or "").strip()
    if not key:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    meta = KEYS_CONFIG.get(key)
    if not meta:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if not isinstance(meta, dict):
        meta = {}

    # defaults (in case config is incomplete)
    meta.setdefault("plan", "free")
    meta.setdefault("daily_limit", 50)

    return key, meta