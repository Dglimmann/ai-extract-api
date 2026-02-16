# AI Data Extraction API

Extract reliable, schema-validated JSON from messy text.

This API turns unstructured text (emails, invoices, documents, CRM exports, PDFs, etc.) into clean, predictable JSON using a schema you define — including:

- 🔒 API key authentication  
- 🧱 Schema-enforced output  
- ⚠️ Warnings for missing or uncertain fields  
- 📊 Confidence score (0.0–1.0)  
- 📈 Usage tracking per API key  
- 🚦 Daily request limits per plan  

---

## Base URL

**Local**  
`http://127.0.0.1:8000`

**Production**  
`https://YOUR_API_URL`

---

## Authentication (API Key)

All endpoints except `/health` require:

```
Authorization: Bearer YOUR_API_KEY
```

API keys are managed server-side and include plan-based limits.

---

## Endpoints

| Method | Endpoint     | Description                     |
|--------|-------------|---------------------------------|
| GET    | /health     | Health check                    |
| POST   | /extract    | Extract structured JSON         |
| GET    | /me/usage   | Check daily usage for your key  |

---

# Example: Extract Invoice Data

## Request

```bash
curl -X POST https://YOUR_API_URL/extract \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Rechnung Nr. 2026-001 von ACME GmbH vom 2026-02-01. Gesamt: 249,90 EUR. Fällig: 2026-02-15.",
    "schema": {
      "company": null,
      "invoice_number": null,
      "date": null,
      "due_date": null,
      "amount_total": null,
      "currency": null
    },
    "language": "de"
  }'
```

## Example Response

```json
{
  "data": {
    "company": "ACME GmbH",
    "invoice_number": "2026-001",
    "date": "2026-02-01",
    "due_date": "2026-02-15",
    "amount_total": 249.9,
    "currency": "EUR"
  },
  "warnings": [],
  "confidence": 1.0,
  "model": "gpt-4.1-mini"
}
```

---

# Usage & Limits

## Check your usage

```bash
curl https://YOUR_API_URL/me/usage \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Example Usage Response

```json
{
  "date": "2026-02-12",
  "plan": "free",
  "daily_limit": 50,
  "used_today": 12,
  "remaining_today": 38
}
```

---

# Confidence Gate

The API supports a configurable minimum confidence threshold.

If the extracted result falls below `MIN_CONFIDENCE`, the API returns:

```json
{
  "detail": {
    "error": "low_confidence",
    "min_confidence": 0.6,
    "confidence": 0.42,
    "warnings": [...],
    "data": {...}
  }
}
```

---

# Environment Variables

See `.env.example` for required configuration.

Example:

```
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1-mini
MIN_CONFIDENCE=0.6

API_KEYS_CONFIG={
  "your_key_here": {"plan": "free", "daily_limit": 50}
}
```

⚠️ Never commit your real `.env` file to GitHub.

---

# Local Setup

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Swagger docs:
```
http://127.0.0.1:8000/docs
```

---

# Plans (Example)

| Plan | Requests / day |
|------|----------------|
| Free | 50 |
| Pro  | 1000+ |
| Team | Custom |

---

# License

MIT

---

# Business Model

Customers do not receive your source code.

They receive:
- An API key  
- A daily limit  
- Access to your hosted API endpoint  

You manage keys and limits server-side.