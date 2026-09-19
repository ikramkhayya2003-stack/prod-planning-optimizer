# Production Planning Optimizer

Production-planning application with a React/Vite frontend and a FastAPI optimization backend.

## Project layout

```text
├── backend/             FastAPI application, optimizer, and source data
├── frontend/            React/Vite web application
├── docs/                Setup notes and change history
├── START_BACKEND.bat    Starts the local API on port 8000
└── START_FRONTEND.bat   Starts the Vite development server
```

## Start locally

1. Follow [the setup guide](docs/getting-started.md).
2. Start the backend with `START_BACKEND.bat`.
3. Start the frontend with `START_FRONTEND.bat`.
4. Open `http://localhost:5173`.

Generated folders such as `frontend/node_modules` and `frontend/dist` are ignored by Git and can be recreated at any time.

## Deploy to Render

The included `render.yaml` creates a FastAPI web service, PostgreSQL database,
and static frontend. Before the first deploy, set these two values in Render:

- `CORS_ORIGINS` on `production-optimizer-api` to the frontend URL, for example
  `https://production-optimizer-web.onrender.com`.
- `VITE_API_URL` on `production-optimizer-web` to the backend URL, for example
  `https://production-optimizer-api.onrender.com`.

Local development remains unchanged: without hosted environment variables, the
API accepts requests from the local Vite server and uses the local database URL.
