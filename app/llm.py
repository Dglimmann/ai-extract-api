import os
import json
from dotenv import load_dotenv
from typing import Any, Dict, List, Tuple
from app.validate import enforce_shape

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in environment (.env)")

from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM = (
    "You extract structured data from messy text.\n"
    "Return ONLY valid JSON with the following structure:\n"
    "{ \"data\": object, \"warnings\": string[], \"confidence\": number }\n\n"
    "Rules:\n"
    "- data MUST match the requested shape exactly\n"
    "- If a field is missing, use null\n"
    "- Do NOT invent facts\n"
    "- warnings: explain uncertainties or inferred values\n"
    "- confidence: number between 0.0 and 1.0 representing overall certainty\n"
    "- Dates must be ISO 8601 (YYYY-MM-DD)\n"
)

async def extract_json(
    text: str,
    schema: Dict[str, Any],
    language: str
) -> Tuple[Dict[str, Any], List[str], float, str]:

    user_msg = f"""Language: {language}

Target JSON shape for data:
{json.dumps(schema, ensure_ascii=False)}

Text to extract from:
{text}
"""

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    payload = json.loads(content)

    if not isinstance(payload, dict):
        raise ValueError("Model did not return a JSON object")

    data = payload.get("data")
    warnings = payload.get("warnings", [])
    confidence = payload.get("confidence", 0.5)

    if not isinstance(data, dict):
        raise ValueError("Missing or invalid 'data' field")

    if not isinstance(warnings, list):
        warnings = ["warnings field invalid (expected list)"]

    if not isinstance(confidence, (int, float)):
        confidence = 0.5

    # ✅ HIER FEHLTE ES: Shape enforce + warnings erweitern
    data, shape_warnings = enforce_shape(schema, data)
    warnings = (warnings if isinstance(warnings, list) else []) + shape_warnings

    # clamp confidence just in case
    confidence = max(0.0, min(1.0, float(confidence)))

    return data, warnings, confidence, OPENAI_MODEL