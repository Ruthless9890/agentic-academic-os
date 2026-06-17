# AcademicOS — Agentic AI Academic Assistant

An AI agent that reads your syllabus, tracks every assignment and exam, and tells you the truth about where you stand — powered by a LangGraph intent-routing pipeline and RAG over your own course documents.

**Live demo:** [agentic-academic-os-production.up.railway.app](https://agentic-academic-os-production.up.railway.app)

![Dashboard screenshot placeholder](docs/screenshot.png)

<!--
  Replace docs/screenshot.png with an actual screenshot of the dashboard
  or chat view before publishing.
-->

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-agent%20orchestration-1C3C3C">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white">
  <img alt="pgvector" src="https://img.shields.io/badge/pgvector-embeddings-336791">
  <img alt="OpenAI" src="https://img.shields.io/badge/OpenAI-gpt--4o--mini%20%7C%20embeddings-412991?logo=openai&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="Railway" src="https://img.shields.io/badge/Deployed%20on-Railway-0B0D0E?logo=railway&logoColor=white">
</p>

---

## What it does

Upload a syllabus PDF. AcademicOS extracts every assignment, exam, weight, and due date, then becomes a chat agent that already knows your grade situation — and routes every question to the right kind of reasoning instead of giving one generic LLM answer to everything.

Ask it "am I cooked?" and it does the grade math and tells you honestly. Ask "what's due this week?" and it gives you facts, not a pep talk. Ask "what should I do about it?" right after discussing a specific assignment, and it stays focused on *that* assignment instead of re-listing everything you own.

## Features

**Conversational agent**
- Intent-routed chat (`WHAT`, `HOW_BAD`, `PLAN`, `UPDATE`, `CRISIS`, `MULTI_COURSE`) — each intent gets its own reasoning path and tone, not a single shared prompt
- Multi-turn memory: follow-up questions ("when is it due?", "what should I do about it?") resolve to the specific assignment/exam under discussion instead of re-answering broadly
- Conversational assignment updates ("I finished the presentation") with fuzzy-match confirmation before writing to the database — no silent wrong updates
- Multi-course awareness: "which of my courses needs the most attention?" ranks urgency across everything you're taking

**Syllabus & document intelligence**
- Drop in a syllabus PDF → structured extraction of assignments, exams, weights, due dates, and late policy via GPT-4o-mini
- Automatic weight normalization so categories + exams always sum to 100%
- Duplicate-course detection on re-upload (case-insensitive name match) — re-uploads enrich the existing course's search index instead of creating a clone
- Upload lecture notes, problem sets, or any course PDF — chunked, embedded (`text-embedding-3-small`), and retrievable via RAG inside chat ("what did the lecture cover on binary trees?")
- Course Materials panel: see everything indexed per course, delete what you don't need

**Dashboard & planning**
- Live weighted grade calculation, color-coded by standing
- Inline assignment editing, score entry, status tracking (pending → in progress → completed)
- Pure-React calendar view (no library) with month navigation and a day-detail panel
- iCal export — single course, multiple selected courses (merged into one file), or everything at once — importable into Google Calendar/Apple Calendar
- Proactive alerts: due-tomorrow, due-soon, overdue, exam-proximity, heavy-week, and inactivity nudges, computed hourly by a background scheduler

## Architecture

```
                         ┌─────────────────────────┐
                         │   React SPA (no build)   │
                         │  app/static/react/app.js │
                         └────────────┬─────────────┘
                                       │ fetch / JSON
                                       ▼
                         ┌─────────────────────────┐
                         │        FastAPI app        │
                         │  (routers, async/await)   │
                         └────────────┬─────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
     ┌────────────────────┐  ┌──────────────────┐  ┌────────────────────┐
     │  Syllabus pipeline  │  │  LangGraph agent  │  │  APScheduler jobs   │
     │  PDF → GPT-4o-mini  │  │   (chat.py entry)  │  │  (alerts, hourly)   │
     │  → structured JSON  │  └─────────┬─────────┘  └──────────┬──────────┘
     └──────────┬──────────┘            │                       │
                │           ┌────────────┴────────────┐         │
                │           │      context_resolver     │         │
                │           │   (course + entity scope) │         │
                │           └────────────┬────────────┘         │
                │           ┌────────────┴────────────┐         │
                │           │       intent_router       │         │
                │           └────────────┬────────────┘         │
                │      ┌─────────┬────────┼────────┬─────────┐   │
                │      ▼         ▼        ▼        ▼         ▼   │
                │   WHAT     HOW_BAD    PLAN    UPDATE   CRISIS  │
                │      │         │        │        │         │   │
                │      └─────────┴───┬────┴────────┴─────────┘   │
                │                    ▼                            │
                │         MULTI_COURSE (cross-course ranking)      │
                ▼                    ▼                            ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │                  PostgreSQL + pgvector                            │
     │  courses · assignments · exams · alerts · conversation_sessions   │
     │  document_chunks (embeddings for syllabi + lecture notes)         │
     └─────────────────────────────────────────────────────────────────┘
```

**Request flow for chat:** every message rebuilds an `AgentState` from the DB (course context, recent conversation history, any pending confirmation) → `context_resolver` figures out which course and which specific assignment/exam is "currently being discussed" → `intent_router` classifies the message (with a deterministic override for yes/no replies to a pending update) → the matching node runs, pulling RAG chunks via pgvector cosine-distance search when relevant → the response and updated state are persisted back to `conversation_sessions`/`conversation_messages` for the next turn.

**RAG:** PDFs are parsed with PyMuPDF, chunked, embedded with `text-embedding-3-small`, and stored in `document_chunks` tagged by `doc_type` (`syllabus` or `document`) and `filename`. Retrieval is a single cosine-distance query scoped to the course — syllabi and lecture notes are searched together, so "what did the lecture say about X" and "what's the late policy" hit the same index.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI, fully async (SQLAlchemy 2.0 async ORM, asyncpg) |
| Agent orchestration | LangGraph (`StateGraph`) + LangChain's `ChatOpenAI` |
| LLM | OpenAI `gpt-4o-mini` (chat/extraction), `text-embedding-3-small` (embeddings) |
| Database | PostgreSQL 16 + `pgvector` for similarity search |
| PDF parsing | PyMuPDF (`fitz`) |
| Scheduling | APScheduler (hourly alert checks) |
| Calendar export | `icalendar` |
| Frontend | React 18 + Tailwind (CDN, Babel-standalone — zero build step) |
| Infra | Docker Compose locally, Railway in production |

## Running locally

**Prerequisites:** Docker and Docker Compose, and an OpenAI API key.

1. **Clone the repo**
   ```bash
   git clone https://github.com/Ruthless9890/agentic-academic-os.git
   cd agentic-academic-os
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and set your `OPENAI_API_KEY` (see [Environment variables](#environment-variables) below).

3. **Build and start the stack**
   ```bash
   docker compose up --build -d
   ```
   This starts a `pgvector/pgvector:pg16` Postgres container and the FastAPI app, with the `vector` extension created automatically and tables created on startup.

4. **Open the app**
   ```
   http://localhost:8000
   ```

5. **Verify it's healthy**
   ```bash
   curl http://localhost:8000/health
   # {"status": "ok"}
   ```

6. **Stop the stack**
   ```bash
   docker compose down       # stops containers, keeps your data
   docker compose down -v    # also wipes the database volume
   ```

The app container mounts `./app` as a live volume and runs `uvicorn --reload`, so backend code changes apply immediately without a rebuild. Frontend files under `app/static/` are plain static files served directly — edit and refresh (the script tag in `index.html` is version-querystringed to bust browser caches when you bump it).

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | yes | Used for syllabus extraction, chat, and embeddings |
| `DATABASE_URL` | yes | SQLAlchemy async connection string, e.g. `postgresql+asyncpg://postgres:postgres@db:5432/academicos`. If your platform (e.g. Railway) injects a plain `postgresql://` URL, it's automatically rewritten to the `+asyncpg` driver at startup |
| `POSTGRES_USER` | yes (local) | Used by the `db` service in `docker-compose.yml` |
| `POSTGRES_PASSWORD` | yes (local) | Used by the `db` service in `docker-compose.yml` |
| `POSTGRES_DB` | yes (local) | Used by the `db` service in `docker-compose.yml` |

See `.env.example` for a ready-to-copy template.

## Project structure

```
academic-os/
├── app/
│   ├── agent/
│   │   └── graph.py            # LangGraph StateGraph: intent routing + all reasoning nodes
│   ├── routers/
│   │   ├── syllabus.py         # PDF upload → structured extraction → course creation/dedup
│   │   ├── documents.py        # Lecture notes / any-PDF upload, list, delete (RAG corpus)
│   │   ├── courses.py          # Course detail + delete
│   │   ├── assignments.py      # CRUD, status/score updates, priority queue
│   │   ├── exams.py            # Exam creation
│   │   ├── chat.py             # /chat endpoint — wraps the LangGraph agent per session
│   │   ├── rag.py              # Manual embed/ask endpoints, chunking helpers
│   │   ├── alerts.py           # Alert feed: list, mark read, dismiss
│   │   └── calendar_export.py  # Single/all-course .ics export
│   ├── static/react/
│   │   ├── index.html          # Loads React/Babel/Tailwind via CDN, no build step
│   │   └── app.js              # Entire SPA: sidebar, chat, dashboard, calendar, modals
│   ├── alerts.py                # Background checks: due-soon, overdue, exam-proximity, etc.
│   ├── database.py              # Async engine/session setup, schema migrations on boot
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py                # Pydantic request/response schemas
│   └── main.py                   # FastAPI app, router wiring, scheduler lifespan
├── db/
│   └── init.sql                  # Creates the pgvector extension on first boot
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Future improvements

- [ ] Push notifications (email/SMS) for alerts instead of in-app only
- [ ] Google Calendar / Canvas LMS direct sync (beyond one-way `.ics` export)
- [ ] Multi-user auth — currently single-tenant by design
- [ ] Streaming chat responses instead of waiting for the full LangGraph run
- [ ] Replace the CDN/Babel-standalone frontend with a proper Vite build for production performance
- [ ] Alembic-managed migrations instead of idempotent `ALTER TABLE` statements in `database.py`
- [ ] Confidence-scored RAG citations so chat answers can point back to the exact source PDF/page

## Author

**Ruthless9890**
