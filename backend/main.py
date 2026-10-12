"""
Main FastAPI application entry point for the T2-RAG Personal AI Digital Twin platform.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.session import engine, Base
from backend.api.health import router as health_router
from backend.api.twins import router as twins_router
from backend.api.documents import router as documents_router
from backend.api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables are registered
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="T2-RAG: Personal AI Digital Twin Platform",
    description="Multi-tenant, grounded, access-controlled Digital Twin platform powered by LangGraph, ChromaDB, and Groq.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(health_router)
app.include_router(twins_router)
app.include_router(documents_router)
app.include_router(chat_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

