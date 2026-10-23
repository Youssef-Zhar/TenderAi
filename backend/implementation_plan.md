# TenderAI Backend — Audit Report & Phase 1 Plan

## Current State Summary

### What exists and is working (assumed — not yet runtime-tested)
| File | Status | Notes |
|---|---|---|
| [app/main.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/main.py) | ✅ Reasonable | DB auto-create on startup, `/` + `/health` routes, router included |
| [app/db/base.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/db/base.py) | ✅ Good | `DeclarativeBase` correctly set up |
| [app/db/session.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/db/session.py) | ✅ Good | Engine from env vars, [get_db()](file:///C:/xampp2/htdocs/tender-ai/backend/app/db/session.py#31-37) generator |
| [app/models/tender.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/models/tender.py) | ✅ Minimal but valid | [Tender](file:///C:/xampp2/htdocs/tender-ai/backend/app/models/tender.py#9-27) with `id`, `title`, `description`, `estimated_budget`, `deadline` |
| [app/schemas/tender.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py) | ✅ Good | [TenderInput](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py#6-11), [TenderCreate](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py#13-15), [TenderResponse](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py#17-21) with Pydantic |
| [app/api/routes/tenders.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/api/routes/tenders.py) | ⚠️ Partial | Only `/analyze-pdf` exists — **no CRUD routes at all** |
| [app/services/ai_analyzer.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/services/ai_analyzer.py) | ✅ Implemented | Chunked Ollama prompts, 2-pass analysis, French output |
| [app/schemas/analysis.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/analysis.py) | ❌ Empty | File exists but has zero content |
| [test_openai.py](file:///C:/xampp2/htdocs/tender-ai/backend/test_openai.py) | 🗑️ Legacy | Old OpenAI test script — safe to ignore |
| [tenders.py.bak](file:///C:/xampp2/htdocs/tender-ai/backend/app/api/routes/tenders.py.bak) | 🗑️ Backup | Old version without AI integration |
| `requirements.txt` | ❌ Missing | No dependency file exists |

### Confirmed problems
1. **No CRUD endpoints** — only `/analyze-pdf` is registered. There is no way to create, list, view, update, or delete tender records via the API.
2. **[analysis.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/analysis.py) is empty** — the file exists but has no schema content.
3. **`requirements.txt` is missing** — the project cannot be reproduced without it.
4. **Model name is hardcoded** in the route response (`"model": "qwen2.5:3b"` at line 122) and in [ai_analyzer.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/services/ai_analyzer.py) (`OLLAMA_MODEL = "qwen2.5:3b"`). Should come from [.env](file:///C:/xampp2/htdocs/tender-ai/backend/.env).
5. **[.env](file:///C:/xampp2/htdocs/tender-ai/backend/.env) has OpenAI keys but no Ollama config** — `OLLAMA_URL` and `OLLAMA_MODEL` are missing from [.env](file:///C:/xampp2/htdocs/tender-ai/backend/.env).
6. **Ollama is not running** — confirmed by connection refused at `http://127.0.0.1:11434`. Must be started before PDF analysis can work.
7. **No automated tests** — no pytest suite exists.

### What is NOT broken (currently)
- The FastAPI app structure is clean and consistent.
- DB session management follows good patterns.
- The PDF extraction logic in the route handler is solid.
- The [ai_analyzer.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/services/ai_analyzer.py) service is well-structured with timeouts and error handling.
- The [Tender](file:///C:/xampp2/htdocs/tender-ai/backend/app/models/tender.py#9-27) model is compatible with SQLAlchemy 2.x mapped columns.

---

## Proposed Changes — Phase 1: Stabilize + Add CRUD

### Priority order
1. Create `requirements.txt` (reproducibility)
2. Add `OLLAMA_URL` + `OLLAMA_MODEL` to [.env](file:///C:/xampp2/htdocs/tender-ai/backend/.env) and read them in [ai_analyzer.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/services/ai_analyzer.py)
3. Add complete CRUD routes to [app/api/routes/tenders.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/api/routes/tenders.py)
4. Fill in [app/schemas/analysis.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/analysis.py) with a minimal Pydantic schema
5. Fix hardcoded model name in the route response

---

### Component: Dependencies

#### [NEW] [requirements.txt](file:///C:/xampp2/htdocs/tender-ai/backend/requirements.txt)
Generated from the currently installed venv packages. No new packages needed for CRUD.

---

### Component: Configuration

#### [MODIFY] [.env](file:///C:/xampp2/htdocs/tender-ai/backend/.env)
Add two lines (values shown as placeholders):
```
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=qwen2.5:3b
```

#### [MODIFY] [ai_analyzer.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/services/ai_analyzer.py)
Read `OLLAMA_URL` and `OLLAMA_MODEL` from environment variables instead of hardcoding them at module level.

---

### Component: CRUD API

#### [MODIFY] [tenders.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/api/routes/tenders.py)
Add the following endpoints **in addition to** the existing `/analyze-pdf`:
- `POST /api/v1/tenders/` — create a tender record manually
- `GET /api/v1/tenders/` — list all tenders (with `skip`/`limit` pagination)
- `GET /api/v1/tenders/{tender_id}` — retrieve one tender
- `PUT /api/v1/tenders/{tender_id}` — update a tender
- `DELETE /api/v1/tenders/{tender_id}` — delete a tender

Use `Depends(get_db)` for session injection. Use existing [TenderCreate](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py#13-15) / [TenderResponse](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/tender.py#17-21) schemas.

---

### Component: Analysis Schema

#### [MODIFY] [analysis.py](file:///C:/xampp2/htdocs/tender-ai/backend/app/schemas/analysis.py)
Add a minimal `AnalysisResponse` Pydantic model describing the structured output from the AI analyzer. Fields will include `status`, `model`, `report` (free text for now), to be extended in Phase 6.

---

## Verification Plan

### Step 1 — Start MariaDB via XAMPP (manual)
Open XAMPP Control Panel → Start Apache and MySQL.

### Step 2 — Start the backend (PowerShell)
```powershell
cd C:\xampp2\htdocs\tender-ai\backend
.venv\Scripts\uvicorn.exe app.main:app --reload
```
**Expected:** Server starts with no errors. The `tenders` table is created automatically on first run.

### Step 3 — Test `/health` in browser or Swagger
Open `http://127.0.0.1:8000/health`
**Expected:** `{"status": "healthy"}`

### Step 4 — Test CRUD via Swagger UI
Open `http://127.0.0.1:8000/docs`

- `POST /api/v1/tenders/` with body `{"title": "Test Tender", "description": "A test tender for development purposes.", "estimated_budget": 1000.0, "deadline": "2025-12-31"}` → HTTP 201
- `GET /api/v1/tenders/` → HTTP 200, list containing the created tender
- `GET /api/v1/tenders/1` → HTTP 200, single tender
- `PUT /api/v1/tenders/1` with updated body → HTTP 200
- `DELETE /api/v1/tenders/1` → HTTP 204
- `GET /api/v1/tenders/999` → HTTP 404

### Step 5 — Test `/analyze-pdf` (requires Ollama running)
Start Ollama: `ollama serve` in a separate terminal.
Upload a real PDF via Swagger → `POST /api/v1/tenders/analyze-pdf`.
**Expected:** JSON with `status: "analysis_completed"` and an AI report.
