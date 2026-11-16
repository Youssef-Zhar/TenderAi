# TenderAI

**AI-assisted public procurement (Appel d'Offres) analysis API.**

TenderAI is a Python backend that accepts text-based tender PDFs, extracts their text, asks an LLM to produce a readable analysis and structured procurement data, verifies extracted evidence against the source document, and stores the resulting tender record in MariaDB/MySQL.

> **Project status:** Active development / prototype. TenderAI is an analysis assistant, not an official procurement authority, legal adviser, or substitute for checking the original tender dossier. AI output can be incomplete or incorrect and must always be reviewed against the source PDF.

---

## Contents

- [What it does](#what-it-does)
- [Current capabilities](#current-capabilities)
- [How analysis works](#how-analysis-works)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Repository structure](#repository-structure)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Environment configuration](#environment-configuration)
- [Database and migrations](#database-and-migrations)
- [Running the API](#running-the-api)
- [API reference](#api-reference)
- [Authentication and security](#authentication-and-security)
- [PDF validation and limitations](#pdf-validation-and-limitations)
- [Analysis quality and evidence](#analysis-quality-and-evidence)
- [Testing](#testing)
- [CI](#ci)
- [Known limitations and next steps](#known-limitations-and-next-steps)
- [Development notes](#development-notes)

---

## What it does

Public tender dossiers can be lengthy and contain important information spread across multiple pages: submission deadlines, estimated budgets, guarantees, eligibility requirements, mandatory documents, technical specifications, and evaluation criteria.

TenderAI aims to make this information easier to review by:

1. Accepting a tender PDF through an authenticated API endpoint.
2. Extracting selectable text page by page.
3. Generating a natural-language analysis report.
4. Extracting structured tender details, conditions, documents, evaluation criteria, and source evidence.
5. Checking submitted evidence against the extracted PDF text.
6. Saving the tender and its verified related records to the relational database.
7. Returning the report, structured extraction, processing metadata, and saved tender ID.

The current repository contains the backend API. A user-facing frontend is not included in this repository.

## Current capabilities

### Tender management

- Create a tender manually.
- List the authenticated user's tenders.
- Retrieve a tender by ID.
- Replace/update a tender's fields.
- Delete a tender.
- Paginate tender listings using `skip` and `limit`.

### PDF analysis

- Upload a PDF using multipart form data.
- Extract text with PyMuPDF.
- Preserve page numbers in the text sent to the analysis service.
- Generate a readable report using the configured OpenRouter model.
- Extract structured data, including:
  - Tender title and reference.
  - Contracting authority.
  - Estimated budget and currency.
  - Submission deadline.
  - Provisional guarantee, when extracted and supported.
  - Participation and eligibility conditions.
  - Required administrative documents.
  - Evaluation criteria and weights.
  - Evidence quotes, source pages, and extracted values.
  - Extraction conflicts and verification counts.
- Return analysis metadata describing partial or degraded processing.
- Save the report and structured child records in the database.

### Evidence verification

TenderAI does more than accept model-generated values at face value:

- Evidence items are checked against the extracted source text.
- Evidence/value mismatches and unsupported field labels can be rejected.
- Ambiguous evidence and extraction conflicts are tracked in analysis metadata.
- Scalar values that have supplied evidence are retained only when verified evidence supports the value.
- Only evidence with a source quote and page number is persisted by the PDF-analysis route.

This is a developing verification pipeline. A verified quote supports a particular extracted claim; it does not establish that the whole tender dossier is legally correct or internally consistent.

### Authentication

- User registration and login.
- Password hashing with Argon2id.
- Signed JWT access tokens using HS256.
- Authenticated user lookup through a Bearer token.
- User-owned tender access: list and individual tender operations are scoped to the authenticated owner.

### Operational endpoints

- `GET /` — basic application response.
- `GET /health` — process health check.
- `GET /ready` — database connectivity readiness check.

---

## How analysis works

The current PDF workflow is broadly:

```text
Client
  |
  | POST /api/v1/tenders/analyze-pdf (PDF + Bearer token)
  v
FastAPI route
  |
  +--> Validate extension, size, PDF signature and document readability
  |
  +--> Extract selectable text page by page (PyMuPDF)
  |
  +--> Generate natural-language report (OpenRouter)
  |
  +--> Extract structured tender data (OpenRouter)
  |
  +--> Verify evidence against extracted document text
  |
  +--> Calculate analysis status and degradation metadata
  |
  +--> Save tender + conditions + documents + criteria + evidence
  |      in one database transaction
  |
  v
JSON response with report, structured data, metadata and tender_id
```

The report is generated before structured extraction. This allows the API to preserve a valid report when structured extraction fails or degrades. In that situation, the response can indicate a partial analysis rather than treating the entire request as successful and complete.

The analyzer uses chunked document processing so that long tender dossiers can be handled in smaller sections. The analysis metadata records conditions such as report truncation, structured-output truncation or failure, fallback use, rejected evidence, ambiguous evidence, and extraction conflicts.

The exact output depends on the configured provider/model and the content and quality of the PDF.

---

## Technology stack

| Area | Technology |
|---|---|
| Language | Python 3.13 |
| API framework | FastAPI |
| ASGI server | Uvicorn |
| Data validation | Pydantic 2 / pydantic-settings |
| ORM | SQLAlchemy 2 |
| Database | MariaDB / MySQL |
| Database driver | PyMySQL |
| Migrations | Alembic |
| PDF text extraction | PyMuPDF |
| AI provider integration | OpenRouter API |
| HTTP client | HTTPX |
| Password hashing | Argon2id via argon2-cffi |
| Authentication | PyJWT, HTTP Bearer |
| Rate limiting | SlowAPI |
| Tests | pytest, pytest-asyncio, pytest-cov |
| CI | GitHub Actions |

Dependencies are pinned in `backend/requirements.txt`; development/testing dependencies are in `backend/requirements-dev.txt`.

---

## Architecture

The backend follows a small layered FastAPI structure:

- **API routes** handle HTTP requests, authentication dependencies, validation, and responses.
- **Core** contains application settings, password/JWT security, and rate-limit configuration.
- **Services** contain AI analysis and deadline parsing logic.
- **Schemas** define request and response data using Pydantic.
- **Models** define SQLAlchemy database tables.
- **Database** contains the SQLAlchemy base, engine, and session dependency.
- **Migrations** contain Alembic migration history.
- **Tests** cover API behavior, security, settings, database sessions, and AI analysis.

### Data model

The current database includes these main entities:

| Table | Purpose |
|---|---|
| `users` | Registered user accounts and password hashes |
| `tenders` | Main tender record, owner, report/description, estimated budget and deadline |
| `tender_conditions` | Extracted eligibility, financial, technical, delivery, and other conditions |
| `tender_documents` | Required or optional documents |
| `tender_criteria` | Evaluation criteria and weights |
| `tender_evidence` | Extracted values with source quote and page number |

A tender is related to its extracted conditions, documents, criteria, and evidence through `tender_id`. The tender's `owner_id` associates user-created records with their owner; it is nullable in the current schema to accommodate legacy records.

---

## Repository structure

```text
TenderAi/
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       └── tenders.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── rate_limit.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── tender.py
│   │   │   ├── tender_condition.py
│   │   │   ├── tender_criterion.py
│   │   │   ├── tender_document.py
│   │   │   ├── tender_evidence.py
│   │   │   └── user.py
│   │   ├── schemas/
│   │   │   ├── analysis.py
│   │   │   ├── auth.py
│   │   │   └── tender.py
│   │   ├── services/
│   │   │   ├── ai_analyzer.py
│   │   │   └── deadline_parser.py
│   │   ├── tests/
│   │   ├── migrations/
│   │   │   └── versions/
│   │   ├── .env.example
│   │   ├── alembic.ini
│   │   ├── pytest.ini
│   │   ├── requirements.txt
│   │   └── requirements-dev.txt
│   └── implementation_plan.md
└── .gitignore
```

---

## Requirements

- Windows, Linux, or macOS.
- Python 3.13 recommended (the CI workflow currently uses Python 3.13).
- MariaDB or MySQL server.
- An OpenRouter API key and a model available to that key.
- Git.

The commands below use Windows PowerShell and the repository's current Windows development workflow. Adjust activation commands for your shell if you are using Linux or macOS.

## Local setup

### 1. Clone the repository

```powershell
git clone https://github.com/Youssef-Zhar/TenderAi.git
cd TenderAi
```

### 2. Create and activate a virtual environment

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use the appropriate execution-policy setting for your environment or invoke the virtual-environment executables directly.

### 3. Install dependencies

For application use:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development and tests:

```powershell
python -m pip install -r requirements-dev.txt
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Edit `backend/.env` with your own database credentials, OpenRouter API key, model name, and a strong random JWT secret. See [Environment configuration](#environment-configuration).

### 5. Prepare the database

Create the database and a dedicated application database user in MariaDB/MySQL. Ensure the configured application user has the privileges required by the application.

Apply the Alembic migrations:

```powershell
alembic upgrade head
```

Run this command from the `backend` directory, where `alembic.ini` is located.

### 6. Start the API

```powershell
uvicorn app.main:app --reload
```

The development server is available at:

- API base: http://127.0.0.1:8000
- Interactive Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/ready

---

## Environment configuration

The backend reads its settings from `backend/.env` and environment variables. Never commit the real `.env` file or paste secrets, API keys, database passwords, or JWTs into issues, logs, screenshots, or public discussions.

| Variable | Purpose | Required |
|---|---|---|
| `DB_HOST` | MariaDB/MySQL host | Yes |
| `DB_PORT` | Database port (default example: `3306`) | Yes |
| `DB_NAME` | Database name | Yes |
| `DB_USER` | Application database username | Yes |
| `DB_PASSWORD` | Application database password | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API key | Required for live AI analysis |
| `OPENROUTER_MODEL` | Model identifier used for analysis | Required when API key is configured |
| `OPENROUTER_BASE_URL` | OpenRouter API base URL | Optional; defaults to `https://openrouter.ai/api/v1` |
| `SECRET_KEY` | JWT signing secret; use a random value of at least 32 characters | Yes |
| `JWT_ALGORITHM` | JWT algorithm; currently HS256 only | Yes |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime; accepted range is 1–60 minutes | Optional; default is 30 |

The example file contains placeholders only. Replace every placeholder with local values before running the application. Do not use example credentials in a deployed environment.

---

## Database and migrations

TenderAI uses SQLAlchemy 2 with a PyMySQL connection to MariaDB/MySQL. Alembic manages schema changes.

Current migration history includes:

- Initial users table.
- Tender-related tables for the structured analysis output.
- Tender ownership support.

Useful commands (run from `backend`):

```powershell
# Apply all migrations
alembic upgrade head

# Show the current database revision
alembic current

# Show migration history
alembic history

# Check whether model metadata differs from the migration state
alembic check
```

Before applying migrations to a database containing important data, create and verify a database backup. Do not assume that a migration is safe to reverse on production data.

---

## Running the API

Start MariaDB/MySQL first, then run the API from `backend`:

```powershell
uvicorn app.main:app --reload
```

The `--reload` option is intended for local development, not production.

FastAPI generates the OpenAPI documentation automatically. Use Swagger UI at `/docs` to register, authenticate, and exercise the protected endpoints.

---

## API reference

All routes are served by the FastAPI application.

### Authentication

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| `POST` | `/auth/register` | Create an account | No |
| `POST` | `/auth/login` | Authenticate and receive a JWT access token | No |
| `GET` | `/auth/me` | Return the current authenticated user | Bearer token |

Registration and login have rate limits configured in the backend.

### Tenders

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| `POST` | `/api/v1/tenders/` | Create a tender manually | Required |
| `GET` | `/api/v1/tenders/` | List the current user's tenders | Required |
| `GET` | `/api/v1/tenders/{tender_id}` | Retrieve one owned tender | Required |
| `PUT` | `/api/v1/tenders/{tender_id}` | Replace/update tender fields | Required |
| `DELETE` | `/api/v1/tenders/{tender_id}` | Delete an owned tender | Required |
| `POST` | `/api/v1/tenders/analyze-pdf` | Upload and analyse a PDF | Required |

Tender listing supports:

- `skip`: number of records to skip; default `0`.
- `limit`: page size; default `20`, maximum `100`.

The update endpoint currently uses `PUT` and expects the full tender input; partial `PATCH` updates are not implemented.

### Operational endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Basic welcome/status response |
| `GET` | `/health` | Application process health |
| `GET` | `/ready` | Checks database connectivity |

### Example: register and log in

Register:

```http
POST /auth/register
Content-Type: application/json

{
  "email": "developer@example.com",
  "password": "Use-A-Strong-Unique-Password"
}
```

Log in:

```http
POST /auth/login
Content-Type: application/json

{
  "email": "developer@example.com",
  "password": "Use-A-Strong-Unique-Password"
}
```

Use the returned `access_token` in the Authorization header for protected endpoints:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Do not commit or share real access tokens.

### Example: analyse a PDF

```http
POST /api/v1/tenders/analyze-pdf
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: multipart/form-data

file: <your-tender.pdf>
```

The successful response includes the uploaded filename, page count, pages containing selectable text, analysis report, structured data, metadata, and (when saved) `tender_id`.

---

## Authentication and security

Current security-related implementation includes:

- Argon2id password hashing.
- JWT access tokens signed with HS256.
- Required `sub`, `iat`, and `exp` token claims.
- Token expiry configured between 1 and 60 minutes.
- Active-account checks during authentication.
- Authenticated access to tender endpoints.
- Ownership filtering for tender records.
- Rate limits of 3 registration requests per hour and 5 login requests per minute.
- PDF upload validation and bounded document processing.
- Database rollback when tender persistence fails.
- Generic health/readiness responses that avoid returning database exception details.

### Important deployment considerations

- The current rate limiter uses in-process memory storage. Its counters are not shared across multiple workers or application instances and reset when the process restarts. Use a shared store such as Redis and review trusted-proxy/client-IP configuration before a multi-worker or multi-instance production deployment.
- Configure trusted reverse-proxy headers carefully. Do not trust arbitrary forwarded headers from untrusted clients.
- Configure CORS deliberately if a separate browser frontend is introduced. The current application entry point does not configure CORS middleware.
- Use HTTPS in deployed environments.
- Use a strong, unique `SECRET_KEY`; keep it private. Rotating it invalidates existing access tokens.
- Use separate, least-privilege database accounts for application runtime and schema migrations where appropriate.
- Do not expose database ports or development server reload mode publicly.
- Add deployment-specific monitoring, backups, secret management, and operational logging before production use.

This repository is a work in progress and should receive a deployment-focused security review before handling real procurement documents or production user data.

---

## PDF validation and limitations

The current upload endpoint enforces these limits:

| Validation | Current behavior |
|---|---|
| File extension | Must end in `.pdf` |
| File signature | Must start with the PDF signature `%PDF-` |
| Maximum file size | 10 MB |
| Maximum page count | 200 pages |
| Maximum extracted text | 300,000 characters |
| Encrypted PDFs | Rejected |
| Corrupted/unreadable PDFs | Rejected |
| Selectable text | Required for AI analysis |

**OCR is not implemented yet.** If a PDF contains no selectable text, the API returns an `ocr_required` analysis status and indicates that OCR processing is required but unsupported. Scanned/image-only documents therefore need OCR before they can be analysed.

The API also limits input size and document length to protect processing resources. A PDF that passes validation can still produce incomplete AI output.

---

## Analysis quality and evidence

The analysis response includes metadata to help callers distinguish a complete result from a degraded one. Depending on the processing outcome, metadata can include:

- `report_truncated`
- `structured_truncated`
- `structured_failed`
- `fallback_used`
- `rejected_evidence_count`
- `ambiguous_evidence_count`
- `extraction_conflict_count`
- `degradation_reasons`

A response status such as `analysis_partial` means the system returned useful output while detecting one or more limitations. It must not be interpreted as a guarantee that every field was extracted.

The evidence table stores the field name, extracted value, source page, and source quote. The current schema does not store a separate persisted status column for every rejected or ambiguous candidate; those verification counts are returned in the analysis response metadata.

For critical facts such as deadlines, financial amounts, provisional/definitive guarantees, retention percentages, and eligibility requirements, always compare the extracted result with the original PDF.

---

## Testing

Run the test suite from the `backend` directory with the development dependencies installed:

```powershell
python -m pytest -v
```

Run a specific test module:

```powershell
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_tenders_api.py -v
python -m pytest tests/test_ai_analyzer.py -v
python -m pytest tests/test_security.py -v
python -m pytest tests/test_config.py -v
```

Run with coverage:

```powershell
python -m pytest --cov=app --cov-report=term-missing
```

The test suite covers areas including:

- Authentication and rate limiting.
- Password hashing and JWT validation.
- Settings validation.
- API health/readiness behavior.
- Tender CRUD and PDF-analysis route behavior.
- PDF input validation and error handling.
- AI analyzer parsing, retries, chunking, evidence verification, and degraded responses.
- Database session behavior.

Tests that exercise the AI service should mock provider calls where appropriate; a live OpenRouter API key should not be required for the normal automated test suite.

---

## CI

GitHub Actions workflow: `.github/workflows/ci.yml`.

The current CI workflow:

1. Runs on pushes to `main` and `feature/**` branches.
2. Runs on pull requests targeting `main`.
3. Uses Ubuntu and Python 3.13.
4. Installs `backend/requirements-dev.txt`.
5. Runs `python -m pytest -v` from the backend directory.
6. Uses CI-only environment values; no production credentials should be stored in the workflow.

---

## Known limitations and next steps

The following are known development areas, not claims of already implemented functionality:

- **OCR:** scanned PDFs and image-only pages are not processed yet.
- **Structured extraction completeness:** the model can omit facts or return incomplete fields even when the narrative report mentions them.
- **Evidence coverage:** unsupported or mismatched evidence is rejected; additional deterministic extraction and regression tests may improve coverage for high-value fields.
- **Conflict handling:** conflicting values are recorded for review; the system does not automatically resolve every contradiction in a tender dossier.
- **Rate-limit storage:** replace in-memory storage with shared storage for multi-worker/production deployments.
- **Proxy configuration:** define trusted proxy behavior before deployment behind a reverse proxy.
- **Frontend:** no frontend application is currently included.
- **Production deployment:** no production hosting configuration is defined in this repository.
- **API shape:** tender detail responses currently expose the main tender record; related conditions, documents, criteria, and evidence are saved in separate tables and are not yet presented through a dedicated expanded-detail endpoint.
- **Observability:** production-grade structured logging, metrics, and monitoring need further work.

Potential next milestones include OCR integration, stronger extraction coverage for guarantees and other financial fields, more end-to-end PDF fixtures with ground-truth expectations, expanded read APIs for related records, shared rate-limit storage, and a deployment architecture.

---

## Development notes

- Keep secrets in the local `backend/.env`; commit only sanitized examples.
- Back up the database before schema migrations or destructive data operations.
- Add regression tests whenever extraction or evidence-verification behavior changes.
- Use synthetic tender PDFs for testing and clearly label them as fictional.
- Treat the original PDF as the source of truth when validating AI output.
- Do not describe synthetic test data as official procurement documentation.

## License

No license file is currently present in the repository. Unless and until a license is added, the project should not be assumed to be released under an open-source license.
