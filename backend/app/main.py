from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlmodel import Session

from .db import get_session
from .routers import cases, checkins, claims, coverage, devices, documents, state

app = FastAPI(title="MedSure API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (devices, cases, documents, coverage, claims, checkins, state):
    app.include_router(r.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.exec(text("SELECT 1"))
    return {"ok": True, "database": "ok"}
