# AgentOptima API - Main Application

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from api.routes import track, recommendations, research
from api.auth.middleware import verify_api_key

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 AgentOptima starting...")
    yield
    # Shutdown
    print("🛑 AgentOptima shutdown")

app = FastAPI(
    title="AgentOptima API",
    description="The self-improving intelligence network for AI agents",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(track.router, prefix="/api/v1", tags=["track"])
app.include_router(recommendations.router, prefix="/api/v1", tags=["recommendations"])
app.include_router(research.router, prefix="/api/v1", tags=["research"])

@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "AgentOptima API v0.1.0 - The self-improving intelligence network for AI agents",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}
