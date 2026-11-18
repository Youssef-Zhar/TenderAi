# TenderAI - Frontend

The TenderAI frontend is the React application for the public procurement analysis platform. It is built with React 19, TypeScript, Vite, Tailwind CSS 4, React Router, and Axios.

## Current capabilities

- Account registration and login through the FastAPI authentication API.
- Session-scoped JWT storage and authenticated API requests.
- Protected application routes and sign out.
- Dashboard statistics and recent tender records loaded from the authenticated user's API data.
- Tender listing, manual tender creation, and deletion.
- PDF upload and AI analysis with report and structured extraction display.
- Loading, empty, and API error states.

The frontend does not use hard-coded demo tender records for the dashboard. Data is loaded from the backend.

## Requirements

- Node.js 24 (or a Vite-supported newer LTS release).
- npm.
- The TenderAI FastAPI backend and configured MariaDB/MySQL database.

## Environment configuration

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Set the backend base URL:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Vite exposes variables prefixed with `VITE_` to browser code. Do not put passwords, API keys, or other secrets in frontend environment variables.

The backend must allow the frontend's exact origin through `CORS_ORIGINS` in `backend/.env`. For local Vite development, the default backend allowlist includes:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

For a deployed frontend, add its exact HTTPS origin to the backend configuration. Do not use a wildcard origin for an authenticated deployment.

## Getting started

Run these commands from the `frontend/` directory:

```bash
npm ci
npm run dev
```

Vite prints the local development URL in the terminal (usually `http://localhost:5173`).

## Available scripts

| Command | Description |
|---|---|
| `npm run dev` | Start the Vite development server |
| `npm run build` | Run TypeScript checks and create a production build |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview the production build locally |

## API integration

The Axios client uses `VITE_API_BASE_URL` and automatically attaches the session's Bearer token to API requests.

| Feature | API endpoint |
|---|---|
| Register | `POST /auth/register` |
| Login | `POST /auth/login` |
| Current user | `GET /auth/me` |
| List tenders | `GET /api/v1/tenders/?skip=0&limit=...` |
| Create tender | `POST /api/v1/tenders/` |
| Delete tender | `DELETE /api/v1/tenders/{tender_id}` |
| Analyse PDF | `POST /api/v1/tenders/analyze-pdf` |

All tender and PDF-analysis endpoints require a valid Bearer token. The API currently supports full tender replacement through `PUT`, but the frontend does not yet expose an edit workflow. The PDF analysis endpoint enforces its own file and document limits; the frontend performs an early 10 MB and PDF-extension check for usability.

## Project structure

```text
src/
|-- components/
|   `-- ProtectedRoute.tsx
|-- context/
|   `-- AuthContext.tsx
|-- layouts/
|-- lib/
|   `-- api.ts
|-- pages/
|   |-- Analysis.tsx
|   |-- Dashboard.tsx
|   |-- Login.tsx
|   `-- Tenders.tsx
|-- services/
|   |-- analysis.ts
|   |-- auth.ts
|   `-- tenders.ts
|-- App.tsx
|-- index.css
`-- main.tsx
```

## CI

GitHub Actions runs ESLint and a production build for the frontend, alongside the backend test suite, on pushes to the configured development branches and pull requests targeting `main`.

For backend setup, authentication details, and API limitations, see the [root README](../README.md).
