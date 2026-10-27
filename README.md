# SmartParkingGarage

Team repository: <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>.

## Backend

The FastAPI backend lives in [`Backend/`](Backend/). It exposes Unity-reported garage state and queues
commands for Unity; assignments and vehicle movement remain Unity-owned. PostgreSQL persists requests, command outcomes,
session metadata, and the latest snapshot. CCTV frames and focus leases remain process-local.

## Documentation

| Guide | Purpose |
| --- | --- |
| [Backend setup and Unity integration](Backend/README.md) | Installation, PostgreSQL, restart behavior, Unity bridge, and CCTV publishing |
| [Dashboard API quick reference](docs/frontend-api.md) | Client endpoints, command tracking, freshness, and camera viewing |
| [Documentation archive](docs/archive/README.md) | Superseded plans, original handoffs, and historical status reports |

The two current guides describe the implemented contract. `/docs` and `/openapi.json` on a running backend expose
the generated request/response schemas. Archived documents retain historical assumptions and are not setup instructions.

## Source ownership

Unity remains in its separate UVCS workspace, and the dashboards are maintained separately.
Clone this GitHub repository outside the Unity workspace; do not copy backend changes into it.
