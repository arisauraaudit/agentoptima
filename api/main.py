# AgentOptima API - Main Application
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os
import sqlite3
import json
from datetime import datetime
from pydantic import BaseModel

# ── Storage ────────────────────────────────────────────────────────────────────
# Uses SQLite at /data/agentoptima.db (Railway volume) with /app fallback.
# Data now survives restarts and deploys.

DB_PATH = "/data/agentoptima.db" if os.path.isdir("/data") else "/app/agentoptima.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     TEXT NOT NULL,
                task_type   TEXT,
                task_desc   TEXT,
                model       TEXT,
                duration_s  INTEGER,
                cost_cents  REAL,
                success     INTEGER,
                notes       TEXT,
                logged_at   TEXT
            )
        """)
        conn.commit()
    print(f"✅ DB ready at {DB_PATH}")

# ── App lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("🚀 AgentOptima API starting...")
    print(f"   DB path:        {DB_PATH}")
    print(f"   Dashboard file: {os.path.exists('/app/dashboard.html')}")
    print(f"   Rankings file:  {os.path.exists('/app/rankings.json')}")
    print(f"   Port:           {os.environ.get('PORT', 8000)}")
    yield
    print("🛑 AgentOptima shutdown")

app = FastAPI(
    title="AgentOptima API",
    description="The self-improving intelligence network for AI agents",
    version="0.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ────────────────────────────────────────────────────────────
class TrackRequest(BaseModel):
    task_id: str
    task_type: str
    task_description: str
    model: str
    duration_seconds: int = None
    cost_cents: float = None
    success: bool = None
    notes: str = None

class TrackResponse(BaseModel):
    status: str
    message: str
    task_id: str

# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/")
async def dashboard():
    for path in ["/app/dashboard.html", "/app/index.html"]:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "Dashboard not found"}, status_code=500)

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.2.0"}

@app.post("/api/v1/track")
async def track_task(request: TrackRequest):
    """Log an agent task — persisted to SQLite."""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO tasks
                    (task_id, task_type, task_desc, model, duration_s,
                     cost_cents, success, notes, logged_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                request.task_id,
                request.task_type,
                request.task_description,
                request.model,
                request.duration_seconds,
                request.cost_cents,
                1 if request.success else 0,
                request.notes,
                datetime.utcnow().isoformat()
            ))
            conn.commit()
        print(f"💾 Logged task: {request.task_id} ({request.task_type})")
        return TrackResponse(
            status="success",
            message=f"Task {request.task_id} logged",
            task_id=request.task_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/status")
async def get_status():
    """Real task counts from the DB."""
    with get_db() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        success   = conn.execute("SELECT COUNT(*) FROM tasks WHERE success=1").fetchone()[0]
        models    = conn.execute("SELECT COUNT(DISTINCT model) FROM tasks").fetchone()[0]
        latest    = conn.execute("SELECT logged_at FROM tasks ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "status": "running",
        "version": "0.2.0",
        "tasks_logged": total,
        "tasks_success": success,
        "models_tracked": models,
        "last_task_at": latest[0] if latest else None,
        "storage": f"sqlite ({DB_PATH})"
    }

@app.get("/api/v1/rankings")
async def get_rankings():
    """Live model rankings from real logged tasks."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                model,
                task_type                          AS category,
                COUNT(*)                           AS tasks_logged,
                ROUND(AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END), 4) AS success_rate,
                ROUND(AVG(duration_s), 2)          AS avg_duration,
                ROUND(AVG(cost_cents), 4)          AS avg_cost_cents
            FROM tasks
            GROUP BY model, task_type
            ORDER BY success_rate DESC, tasks_logged DESC
        """).fetchall()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_rows": len(rows),
        "models": [dict(r) for r in rows]
    }

@app.get("/api/v1/recommendations")
async def get_recommendations():
    """Generate insights based on real data."""
    with get_db() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM tasks WHERE success=1").fetchone()[0]
        avg_dur = conn.execute("SELECT AVG(duration_s) FROM tasks").fetchone()[0] or 0

    recommendations = []
    if total == 0:
        summary = "No data yet — start running tasks to unlock insights."
        recommendations.append({
            "priority": "high",
            "category": "onboarding",
            "message": "No tasks logged yet.",
            "action": "Run any task through the Aris orchestrator."
        })
    else:
        rate = success / total
        summary = (
            f"{total} tasks logged | "
            f"Success rate: {success}/{total} ({rate*100:.0f}%) | "
            f"Avg duration: {avg_dur:.1f}s"
        )
        if rate < 0.8:
            recommendations.append({
                "priority": "high", "category": "reliability",
                "message": f"Success rate {rate*100:.0f}% is below 80% target.",
                "action": "Review failure notes for recurring errors."
            })
        else:
            recommendations.append({
                "priority": "low", "category": "optimization",
                "message": f"Success rate {rate*100:.0f}% is healthy ✅",
                "action": None
            })
        if avg_dur > 300:
            recommendations.append({
                "priority": "medium", "category": "performance",
                "message": f"Avg task duration {avg_dur:.0f}s is high.",
                "action": "Consider breaking long tasks into smaller subtasks."
            })

    return {
        "recommendations": recommendations,
        "last_updated": datetime.utcnow().isoformat(),
        "summary": summary
    }
