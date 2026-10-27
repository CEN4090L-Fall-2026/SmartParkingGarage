# Documentation archive

Historical material only. For current setup and integration behavior, use the [backend guide](../../Backend/README.md)
and [dashboard API reference](../frontend-api.md). Runtime `/docs` and `/openapi.json` expose the generated schemas.

These documents preserve earlier decisions, measurements, and handoffs. Their implementation status, test counts,
paths, API proposals, and future-work lists may be outdated. They are not current setup instructions or acceptance evidence.

## CCTV design and capture notes

| Document | Historical scope |
| --- | --- |
| [Backend CCTV plan](cctv/backend-plan.md) | Backend design, implementation notes, and proposed verification checklist; formerly root `CCTV_BACKEND_PLAN.md` |
| [Unity CCTV capture notes](cctv/unity-capture-notes.md) | Original capture description, reported performance measurements, and proposed dashboard transport; formerly root `CCTV_IMPLEMENTATION` |

The current implementation includes backend camera endpoints and Unity's `CCTVBackendPublisher`. References in these
archived documents to a missing publisher, missing backend endpoints, or generation tagging still to implement are historical.

## Original technical handoffs

Original DOCX files are preserved without content changes. They describe the cs:17 foundation, not the current API
or PostgreSQL storage implementation; they previously lived directly in `Backend/`.

| Document | Historical scope |
| --- | --- |
| [Backend handoff](handoffs/01_Backend_Handoff.docx) | Backend ownership, command lifecycle, state synchronization, and early verification |
| [Operator dashboard handoff](handoffs/02_Operator_Dashboard_Handoff.docx) | Operator UX responsibilities and suggested integration checkpoints |
| [Driver dashboard handoff](handoffs/03_Driver_Dashboard_Handoff.docx) | Driver request/assignment journey and proposed future guidance |
| [Shared architecture guide](handoffs/04_Shared_Architecture_Integration_Guide.docx) | Original cross-team boundaries, vocabulary, and demo scenarios |

## Status reports

| Document | Historical scope |
| --- | --- |
| [Backend status report #2](reports/backend-status-report-02.md) | Packaging and driver-request work before PostgreSQL and the Unity CCTV publisher; formerly `docs/reports/backend-status-report-02.md` |

## Maintenance

Keep current instructions in the two active guides rather than introducing another competing handoff or plan.
When a plan or report is superseded, retain it here, label its historical scope, and update inbound links.
Do not rewrite original results to imply that later features or verification existed at the time.
