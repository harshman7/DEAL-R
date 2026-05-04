# DEAL-R

**Event-sourced No-Limit Texas Hold’em** engine and server: a deterministic, test-heavy core (`engine/`) with FastAPI adapters (`server/`), PostgreSQL (or SQLite) persistence, JWT auth, WebSockets for live tables, and a small static web UI.

---

## Table of contents

1. [Overview](#overview)
2. [Features](#features)
3. [Technology stack](#technology-stack)
4. [Repository layout](#repository-layout)
5. [Core concepts](#core-concepts)
6. [Prerequisites](#prerequisites)
7. [Installation](#installation)
8. [Configuration](#configuration)
9. [Running locally](#running-locally)
10. [Docker](#docker)
11. [Testing & quality](#testing--quality)
12. [REST API](#rest-api-summary)
13. [WebSocket protocol](#websocket-protocol)
14. [Web UI (`web/`)](#web-ui-web)
15. [CLI tools](#cli-tools)
16. [Determinism & replay](#determinism--replay)
17. [Security](#security)
18. [Continuous integration](#continuous-integration)
19. [Troubleshooting](#troubleshooting)
20. [Documentation](#documentation)
21. [License](#license)

---

## Overview

DEAL-R implements a **play-money** poker table where:

- All meaningful state changes flow through a **pure reducer**: `next_state(state, command) → (new_state, events[])`.
- Events are **append-only** in the persistence layer with **optimistic concurrency** (`expected_version`).
- Clients send **commands** (sit, stand, act, start hand); the server validates, persists events, and broadcasts **derived public state**.
- **Hole cards** are never leaked to non-owners in the intended production posture (see threat model docs).

---

## Features

| Area | Capability |
|------|-------------|
| **Engine** | NLHE rules: legality, side pots, auto-advance, showdown evaluation, hand strength ranking |
| **Event sourcing** | Command idempotency, versioned streams, deterministic replay via `apply_event` |
| **Server** | FastAPI REST + JWT auth + WebSockets + Prometheus-friendly metrics hooks |
| **Persistence** | SQLAlchemy models, event store abstraction (PostgreSQL in CI/production path; SQLite default for dev) |
| **Quality** | Unit tests, integration tests with Postgres, property-based invariant tests (Hypothesis), **mypy** on `engine` + `server` |
| **UX** | Static `web/` assets: login, home, poker table, daily roulette |

---

## Technology stack

- **Python** 3.11+ (CI tests **3.11** and **3.12**)
- **FastAPI**, **Pydantic v2**, **Uvicorn**
- **SQLAlchemy** 2.x, **PostgreSQL** (recommended) / **SQLite** (default URL)
- **python-jose** + **bcrypt** for JWT and password hashing (see `server/services/auth.py`)
- **Hypothesis** for property testing
- **Ruff**, **Black**, **mypy** (with `sqlalchemy.ext.mypy.plugin`), **pre-commit**

---

## Repository layout

```
DEAL-R/
├── engine/                 # Pure game logic — no IO, no networking
│   ├── domain/             # GameState, commands, events, Card, Deck, types
│   ├── rules/              # Legality, side pots, invariants
│   ├── reducer/            # next_state, apply_event, auto-advance
│   └── eval/               # Hand evaluation / pot splitting helpers
├── server/                 # FastAPI application
│   ├── api/                # REST routers, WebSocket router, schemas
│   ├── persistence/        # Event store, ORM models
│   ├── services/           # Table service, auth, analytics, etc.
│   ├── middleware/         # Logging, rate limiting
│   ├── config.py           # Pydantic settings / env
│   └── main.py             # App factory, static mounts, health
├── web/                    # Static HTML/JS/CSS client (session.js, table.js, …)
├── tools/                  # replay_cli, hand history export
├── tests/
│   ├── unit/               # Engine + server units
│   ├── integration/        # DB + API + websocket tests
│   └── property/           # Hypothesis invariant tests
├── docs/                   # Architecture, threat model, ADRs
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md               # (this file)
```

---

## Core concepts

### Commands vs events

- **Commands** (`engine/domain/commands.py`) express *intent*: `SitDown`, `StandUp`, `StartHand`, `Act`, `RevealSeed`.
- **Events** (`engine/domain/events.py`) capture *facts* that happened: `PlayerSatDown`, `ActionApplied`, `StreetDealt`, `ShowdownResolved`, `HandEnded`, etc.
- The **reducer** validates commands against `GameState` and emits zero or more events; `apply_event` folds events into state for replay.

### Why event sourcing?

- **Auditability**: the event log *is* the authoritative history.
- **Deterministic replay**: same initial state + same events ⇒ same final state (modulo deliberate non-determinism boundaries, which this project avoids in the engine).
- **Concurrency story**: optimistic locking on `(hand_id/stream_id, version)` detects conflicting writers.

### Table streams vs hand streams

Runtime code uses identifiers such as:

- `table-{table_id}` for table-level lifecycle (sit/stand outside a specific hand persistence path in some flows)
- Individual `hand_id` values once a hand is started (`StartHand`)

The exact composition is implemented in `TableService`; when extending persistence, preserve version monotonicity per stream.

---

## Prerequisites

- **Python** 3.11 or newer
- **PostgreSQL** 15+ (optional locally; Docker Compose supplies one)
- **Docker** / **Docker Compose** (recommended for Postgres and image builds)

---

## Installation

```bash
git clone <your-fork-url> DEAL-R
cd DEAL-R
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -e ".[dev]"
pre-commit install                    # optional but recommended
```

Development dependencies (`[dev]`) include: `pytest`, `hypothesis`, `ruff`, `black`, `mypy`, `types-python-jose`, `pre-commit`.

---

## Configuration

Environment variables are read via `pydantic-settings` (`server/config.py`). Typical `.env`:

| Variable | Default | Meaning |
|---------|---------|---------|
| `DATABASE_URL` | `sqlite:///./poker.db` | SQLAlchemy URL (PostgreSQL DSN for real deployments) |
| `JWT_SECRET_KEY` | (dev placeholder) | **Must** be rotated in production |
| `JWT_ALGORITHM` | `HS256` | JWT alg |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Session lifetime |
| `RATE_LIMIT_ENABLED` | `true` | Toggle simple rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests/min per IP/key |
| `LOG_LEVEL` | `INFO` | Structlog threshold |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `SNAPSHOT_INTERVAL` | `100` | Snapshot cadence hook (see event store) |

---

## Running locally

### PostgreSQL via Compose

```bash
docker compose up -d
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname   # match your compose file
```

### API server

```bash
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

Useful URLs:

- OpenAPI UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`
- Static UI entry: `http://localhost:8000/web/home.html` (if static mount is enabled; see `main.py`)

---

## Docker

The `Dockerfile` installs **runtime dependencies only** (`pip install -e .`, no `[dev]`). Health checks use **`urllib`** against `/health` (no extra `requests` dependency).

Build:

```bash
docker build -t deal-r:latest .
```

Run (example):

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql://… \
  -e JWT_SECRET_KEY=… \
  deal-r:latest
```

---

## Testing & quality

```bash
# Full suite (includes integration tests; some require DATABASE_URL pointing at Postgres)
pytest

pytest --cov=engine --cov=server --cov-report=term-missing

# Focused subsets
pytest tests/unit/
pytest tests/integration/
pytest tests/property/

# Static checks
ruff check .
black --check .
mypy engine server
```

**Pre-commit** mirrors CI style checks locally:

```bash
pre-commit run --all-files
```

---

## REST API summary

All JSON routes live under prefixes defined in routers (auth: `/api/v1/auth`, game REST: `/api/v1`). OpenAPI (`/docs`) is the authoritative list. Common capabilities include:

| Concern | Notes |
|---------|-------|
| **Auth** | Register/login returns JWT `access_token`; use `Authorization: Bearer <token>` |
| **Player profile** | `/api/v1/players/me` style endpoints (see router definitions) |
| **Table snapshots** | Read models for spectators/refresh paths |
| **Roulette (demo)** | Daily spin endpoint persists chips into `users.json` (dev-oriented) |

Consult `server/api/rest.py` and `server/api/auth.py` for exact paths and payloads.

---

## WebSocket protocol

Connect to `/ws/tables/{table_id}` (see `server/api/ws.py`). Pass JWT as **`?token=<jwt>`** query parameter (browser WebSockets cannot set custom headers easily).

Outbound messages commonly include:

- `type: "state"` — table snapshot wrapper with seats, pots, street, version
- `type: "command_accepted"` — echo of successful command application with `new_version`
- `type: "error"` — human-readable failures (validation, capacity, etc.)

Inbound commands mirror domain commands roughly as:

```json
{ "type": "sit_down", "data": { "seat_id": 0, "stack": 1000, "player_id": "player_alice" }, "idempotency_key": "…", "expected_version": 0 }
```

Similar shapes exist for `act`, `start_hand`, and `stand_up`. Always send **fresh idempotency keys** per logical user action.

---

## Web UI (`web/`)

Static assets demonstrate end-to-end flows:

- **`session.js`** — shared auth/session helpers (`fetchWithAuth`, login redirect).
- **`table.js`** — WebSocket-driven poker UI.
- **`home.js`**, **`roulette.js`** — profile and daily bonus demo.

See `web/DESIGN.md` for UX notes.

---

## CLI tools

```bash
python -m tools.replay_cli <hand-id> [--hash-only]
python -m tools.hh_export <hand-id> --output hand.txt
```

These assume database connectivity consistent with `DATABASE_URL`.

---

## Determinism & replay

1. **Deck**: `Deck.create_shuffled(seed)` derives order deterministically from an integer seed.
2. **Hand start**: Clients supply a **`seed_commit`** string; replay paths derive integer seeds compatibly with runtime dealing (see `TableService._replay_events` and reducer start-hand flows).
3. **Replay**: `apply_event` in a loop reconstructs table state machine positions from persisted events alone.

Extended discussion: [`docs/architecture.md`](docs/architecture.md).

---

## Security

DEAL-R is designed as **server authoritative** poker with JWT auth and optimistic concurrency. Threat assumptions and residual risks are documented in [`docs/threat-model.md`](docs/threat-model.md). **Rotate secrets**, tighten CORS, and harden persistence before any real-money adjacent deployment.

---

## Continuous integration

GitHub Actions (`.github/workflows/ci.yml`):

1. **Lint** — Python 3.12, `pip install -e ".[dev]"`, `pre-commit run --all-files`, **`mypy engine server`**.
2. **Test** — Matrix **3.11 / 3.12** against **PostgreSQL 15**, `pytest` + coverage XML.
3. **Build** — Docker image build with GH Actions cache backends.

Codecov upload runs once (Python 3.12 job) to avoid duplicate reports.

---

## Troubleshooting

| Symptom | Things to check |
|---------|----------------|
| **Version mismatch errors** | Client `expected_version` stale; reload snapshot or websocket `state.version`. |
| **401 on REST** | Expired JWT; re-login. Ensure `Authorization: Bearer …` header present. |
| **WebSocket instant disconnect** | Missing/invalid `token` query param; server logs in `server/api/ws.py` print decode failures during dev. |
| **Integration tests fail** | Export `DATABASE_URL` to a reachable Postgres with created DB/user (CI uses `poker_test`). |
| **SQLite locked** | Multiple writers; prefer Postgres for concurrent local dev. |
| **mypy plugin errors** | Ensure `sqlalchemy` 2.x installed; `pyproject.toml` enables `sqlalchemy.ext.mypy.plugin`. |

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/architecture.md`](docs/architecture.md) | System design, boundaries between engine and server |
| [`docs/state-machine.md`](docs/state-machine.md) | Streets, transitions, table lifecycle |
| [`docs/invariants.md`](docs/invariants.md) | Chip conservation, pot correctness, etc. |
| [`docs/threat-model.md`](docs/threat-model.md) | Security assumptions |
| [`docs/adr/0001-event-sourcing.md`](docs/adr/0001-event-sourcing.md) | ADR: why event sourcing |
| [`web/DESIGN.md`](web/DESIGN.md) | Static client design notes |

---

## License

MIT

---

## Quick reference card

```bash
# Dev install
pip install -e ".[dev]"

# Database
docker compose up -d

# Run API
uvicorn server.main:app --reload

# Tests + types
pytest && mypy engine server

# Hooks
pre-commit run --all-files
```

For questions about extending the engine (new streets, tournament mode, different game variants), start from `engine/domain` and `engine/reducer/reducer.py`, then thread changes through `server/services/table_service.py` and API schemas.
