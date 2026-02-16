import os, json
from datetime import date
from fastapi import HTTPException
from typing import Dict, Any

USAGE_FILE = os.getenv("USAGE_FILE", "usage.json")

def _load() -> dict:
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(data: dict) -> None:
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _today() -> str:
    return date.today().isoformat()

def get_usage(api_key: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    today = _today()
    data = _load()
    day = data.get(today, {})
    used = int(day.get(api_key, 0))

    limit = int(meta.get("daily_limit", 50))
    plan = str(meta.get("plan", "free"))

    return {
        "date": today,
        "plan": plan,
        "daily_limit": limit,
        "used_today": used,
        "remaining_today": max(0, limit - used),
    }

def check_and_increment(api_key: str, meta: Dict[str, Any]) -> None:
    today = _today()
    data = _load()
    day = data.get(today, {})
    used = int(day.get(api_key, 0))

    limit = int(meta.get("daily_limit", 50))

    if used >= limit:
        raise HTTPException(status_code=429, detail=f"Daily limit exceeded ({limit}/day)")

    day[api_key] = used + 1
    data[today] = day
    _save(data)