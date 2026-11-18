# TenderAI - Frontend

The TenderAI frontend is a React dashboard for the public procurement analysis platform. It is built with React 19, TypeScript, Vite, and Tailwind CSS 4.

## Current status

The initial dashboard interface is implemented. It currently displays mock data and is not yet connected to the FastAPI backend. API integration, authentication, and live tender data are planned work.

## Current interface

- Dark SaaS dashboard layout.
- Sidebar navigation and application header.
- Dashboard summary statistics.
- Recent tenders overview.
- Quick actions and upcoming deadline panel.
- Responsive styling.

## Tech stack

| Technology | Purpose |
|---|---|
| React 19 | UI components |
| TypeScript | Static typing |
| Vite | Development server and build tooling |
| Tailwind CSS 4 | Styling |
| React Router | Client-side routing |
| Axios | HTTP client for planned API integration |
| TanStack Query | Server-state management for planned API integration |
| Lucide React | Icons |

## Getting started

Use Node.js and npm, then run these commands from the `frontend/` directory:

```bash
npm install
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

## Project structure

```text
src/
|-- assets/
|-- components/
|   |-- shared/
|   `-- ui/
|-- features/
|   |-- auth/
|   `-- dashboard/
|-- hooks/
|-- layouts/
|-- lib/
|-- pages/
|-- services/
|-- types/
|-- App.tsx
|-- index.css
`-- main.tsx
```

## Backend integration

The backend API is a FastAPI application in the repository's `backend/` directory. Browser-based integration will require the backend to configure CORS with an explicit allowlist for the frontend origin. No live API integration or frontend authentication is implemented yet.

For backend setup and API details, see the [root README](../README.md).
