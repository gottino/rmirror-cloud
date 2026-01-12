# /dev

Start the local development environment with backend, agent, and dashboard services.

## Usage

```
/dev [component]
```

## Arguments

- `all` (default): Start all three services
- `backend`: Start only the backend API server
- `agent`: Start only the macOS agent
- `dashboard`: Start only the Next.js dashboard

## Instructions

### Starting All Services (default)

Run these three commands in **parallel background shells**:

1. **Backend** (FastAPI on port 8000):
   ```bash
   cd /Users/gabriele/Documents/Development/rmirror-cloud/backend && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Dashboard** (Next.js on port 3000):
   ```bash
   cd /Users/gabriele/Documents/Development/rmirror-cloud/dashboard && npm run dev
   ```

3. **Agent** (Flask web UI on port 5555):
   ```bash
   cd /Users/gabriele/Documents/Development/rmirror-cloud/agent && poetry run python -m app.main --foreground --debug
   ```

### Starting Individual Components

If a specific component is requested, only start that one in a background shell.

### After Starting

Report to the user:
- Which services were started
- The URLs to access them:
  - Backend API: http://localhost:8000 (docs at http://localhost:8000/docs)
  - Dashboard: http://localhost:3000
  - Agent Web UI: http://localhost:5555
- Remind them to use `/tasks` to see running background tasks
- Remind them they can use `KillShell` to stop individual services

## Examples

```
/dev              # Start all services
/dev all          # Start all services
/dev backend      # Start only backend
/dev dashboard    # Start only dashboard
/dev agent        # Start only agent
```

## Prerequisites

- Backend: Poetry installed, dependencies installed (`poetry install` in backend/)
- Dashboard: npm installed, dependencies installed (`npm install` in dashboard/)
- Agent: Poetry installed, dependencies installed (`poetry install` in agent/)

## Ports

| Service   | Port | URL                          |
|-----------|------|------------------------------|
| Backend   | 8000 | http://localhost:8000        |
| Dashboard | 3000 | http://localhost:3000        |
| Agent     | 9090 | http://localhost:5555        |
