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

from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import json
import os

# In-memory storage for MVP (will be replaced with DB later)
agent_data_store = []
recommendations_cache = []

# Pydantic models
class TrackRequest(BaseModel):
    task_id: str
    task_type: str
    task_description: str
    model: str
    duration_seconds: Optional[int]
    cost_cents: Optional[float]
    success: Optional[bool]
    notes: Optional[str] = None

class TrackResponse(BaseModel):
    status: str
    message: str
    task_id: str

class RecommendationsResponse(BaseModel):
    recommendations: List[Dict]
    last_updated: str
    summary: str

# POST /api/v1/track - Log agent task data
@app.post("/api/v1/track", response_model=TrackResponse)
async def track_task(request: TrackRequest):
    """Log an agent task for analytics and self-improvement"""
    try:
        data = {
            "task_id": request.task_id,
            "task_type": request.task_type,
            "task_description": request.task_description,
            "model": request.model,
            "duration_seconds": request.duration_seconds,
            "cost_cents": request.cost_cents,
            "success": request.success,
            "notes": request.notes,
            "timestamp": datetime.utcnow().isoformat()
        }
        agent_data_store.append(data)
        
        print(f"💾 Logged task: {request.task_id} ({request.task_type})")
        
        return TrackResponse(
            status="success",
            message=f"Task {request.task_id} logged successfully",
            task_id=request.task_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GET /api/v1/recommendations - Get analytics insights
@app.get("/api/v1/recommendations", response_model=RecommendationsResponse)
async def get_recommendations():
    """Generate performance recommendations based on logged data"""
    try:
        # Basic analytics based on available data
        recommendations = []
        summary = ""
        
        if agent_data_store:
            total_tasks = len(agent_data_store)
            successful = sum(1 for t in agent_data_store if t.get("success"))
            avg_duration = sum(t.get("duration_seconds", 0) for t in agent_data_store) / total_tasks
            total_cost = sum(t.get("cost_cents", 0) for t in agent_data_store)
            
            # Generate actionable insights
            if successful / total_tasks < 0.8:
                recommendations.append({
                    "priority": "high",
                    "category": "reliability",
                    "message": f"Task success rate ({successful}/{total_tasks}) is below target. Review failed tasks and add retry logic.",
                    "action": "Check notes field for error patterns"
                })
            else:
                recommendations.append({
                    "priority": "low",
                    "category": "optimization",
                    "message": f"Task success rate ({successful}/{total_tasks}) is healthy.",
                    "action": None
                })
            
            # Cost optimization recommendation
            if avg_duration > 300:  # 5+ minutes
                recommendations.append({
                    "priority": "medium",
                    "category": "performance",
                    "message": f"Average task duration ({avg_duration:.1f}s) is high. Consider batching or parallelization.",
                    "action": "Review task decomposition patterns"
                })
            
            summary = f"Analyzed {total_tasks} tasks | Success rate: {successful}/{total_tasks} | Avg duration: {avg_duration:.1f}s | Total cost: ${total_cost:.2f}"
        else:
            summary = "No data logged yet. Start tracking tasks to receive recommendations."
            recommendations.append({
                "priority": "high",
                "category": "onboarding",
                "message": "No agent task data logged yet",
                "action": "Start calling /api/v1/track after each task"
            })
        
        return RecommendationsResponse(
            recommendations=recommendations,
            last_updated=datetime.utcnow().isoformat(),
            summary=summary
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GET /api/v1/status - Get system status
@app.get("/api/v1/status")
async def get_status():
    """Get system status and usage metrics"""
    return {
        "status": "running",
        "version": "0.1.0",
        "tasks_logged": len(agent_data_store),
        "storage": "memory (MVP mode)",
        "endpoints": ["/health", "/api/v1/track", "/api/v1/recommendations", "/docs"]
    }
