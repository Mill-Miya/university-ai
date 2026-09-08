# University AI — MVP 1

Local-first Windows resident application for managing courses, assignments, exams, and deterministic deadline notifications. MVP 1 has no LLM or external service dependency.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m university_ai.app.main
```

Run tests with `pytest`.

## Architecture

`ui -> application/core -> domain models -> infrastructure (SQLite, Windows adapters)`.
Database access is limited to repositories. Notifications are persisted and deduplicated in SQLite.

