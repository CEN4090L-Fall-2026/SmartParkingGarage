# SmartParkingGarage

Team repository: <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>.

## Backend

The FastAPI backend lives in [`Backend/`](Backend/). It exposes Unity-reported garage state and queues
commands for Unity; assignments and vehicle movement remain Unity-owned. PostgreSQL persists requests, command outcomes,
session metadata, and the latest snapshot. CCTV frames and focus leases remain process-local.

## Documentation

- [Backend setup and Unity integration](Backend/README.md)
- [Dashboard API quick reference](docs/frontend-api.md)
- [Historical backend status report #2](docs/reports/backend-status-report-02.md)

## Source ownership

Unity remains in its separate UVCS workspace, and the dashboards are maintained separately.
Clone this GitHub repository outside the Unity workspace; do not copy backend changes into it.
