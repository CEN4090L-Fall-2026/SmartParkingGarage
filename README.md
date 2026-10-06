# SmartParkingGarage

Team repository: <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>.

## Backend

The FastAPI backend lives in [`Backend/`](Backend/). It exposes Unity-reported garage state and queues
commands for Unity; assignments and vehicle movement remain Unity-owned. State is currently in memory.

From this repository's root:

```bash
cd Backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

See [the backend README](Backend/README.md) for API contracts, quality checks, and integration details.

## Source ownership

Unity remains in its separate UVCS workspace. Clone this GitHub repository outside that workspace;
do not copy these backend changes into the Unity project. Operator and driver dashboards remain planned.