from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.alerts import run_all_checks
from app.database import init_db
from app.routers import syllabus, assignments, courses, rag, chat, exams, alerts, documents, calendar_export

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await run_all_checks()  # run once immediately so alerts are populated right away
    scheduler.add_job(run_all_checks, "interval", hours=1, id="alert_checks")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Academic OS", version="0.1.0", lifespan=lifespan)

app.include_router(syllabus.router)
app.include_router(assignments.router)
app.include_router(courses.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(exams.router)
app.include_router(alerts.router)
app.include_router(documents.router)
app.include_router(calendar_export.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/static/react/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
