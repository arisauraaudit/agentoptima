# AgentOptima API - Main Application
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 AgentOptima starting...")
    yield
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

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}

@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "AgentOptima API v0.1.0 - The self-improving intelligence network for AI agents",
        "docs": "/docs"
    }

# API routes (placeholder)
# Add your routes here
