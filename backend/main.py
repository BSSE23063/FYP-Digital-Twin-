"""
Main FastAPI application entry point for the T2-RAG Personal AI Digital Twin platform.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.conversations import router as conversations_router
from backend.api.debug import router as debug_router
from backend.api.grants import router as grants_router
from backend.api.health import router as health_router
from backend.api.knowledge_gaps import router as knowledge_gaps_router
from backend.api.sources import router as sources_router
from backend.api.twins import router as twins_router
from backend.api.voice import router as voice_router
from backend.config import settings
from backend.db.session import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only creates tables that don't exist yet -- never alters existing ones.
    # See CLAUDE.md for when a destructive --reset is actually needed.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="T2-RAG: Personal AI Digital Twin Platform",
    description="Multi-tenant, grounded, access-controlled digital twin platform "
    "powered by LangGraph, Qdrant, and Groq.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Avatars are static files on disk (TwinResponse.avatar_url points here) —
# created on first upload, so the directory may not exist yet at startup.
Path(settings.AVATAR_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/media/avatars", StaticFiles(directory=settings.AVATAR_DIR), name="avatars")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(twins_router)
app.include_router(sources_router)
app.include_router(grants_router)
app.include_router(knowledge_gaps_router)
app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(debug_router)
app.include_router(conversations_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
