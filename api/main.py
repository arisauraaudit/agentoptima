# AgentOptima API v0.3.0 — PostgreSQL persistence
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from pydantic import BaseModel

# ── Database connection ────────────────────────────────────────────────────────
_raw_url = os.environ.get("DATABASE_URL", "")

# Railway injects postgres:// but psycopg2 requires postgresql://
DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1) if _raw_url else None

def get_db():
    """Return a fresh psycopg2 connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set — add PostgreSQL service to Railway project")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Create tables if they don't exist."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id            SERIAL PRIMARY KEY,
                        task_id       TEXT NOT NULL,
                        task_type     TEXT,
                        task_desc     TEXT,
                        model         TEXT,
                        duration_s    INTEGER,
                        cost_cents    REAL,
                        success       BOOLEAN,
                        notes         TEXT,
                        logged_at     TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
            conn.commit()
        print("✅ PostgreSQL ready")
    except Exception as e:
        print(f"⚠️  DB init warning (will retry on first request): {e}")

# ── App lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("🚀 AgentOptima API v0.3.0 starting...")
    print(f"   Storage: PostgreSQL (Railway managed)")
    print(f"   Port: {os.environ.get('PORT', 8000)}")
    yield
    print("🛑 AgentOptima shutdown")

app = FastAPI(
    title="AgentOptima API",
    description="The self-improving intelligence network for AI agents",
    version="0.3.0",
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
    return {"status": "healthy", "version": "0.3.0"}

@app.post("/api/v1/track")
async def track_task(request: TrackRequest):
    """Log an agent task — persisted to PostgreSQL."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tasks
                        (task_id, task_type, task_desc, model, duration_s,
                         cost_cents, success, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    request.task_id,
                    request.task_type,
                    request.task_description,
                    request.model,
                    request.duration_seconds,
                    request.cost_cents,
                    request.success,
                    request.notes,
                ))
            conn.commit()
        print(f"💾 Logged: {request.task_id} ({request.task_type}) [{request.model}]")
        return TrackResponse(
            status="success",
            message=f"Task {request.task_id} logged",
            task_id=request.task_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/status")
async def get_status():
    """Real task counts from PostgreSQL."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE success = TRUE")
            success = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT model) FROM tasks")
            models = cur.fetchone()[0]
            cur.execute("SELECT logged_at FROM tasks ORDER BY id DESC LIMIT 1")
            latest = cur.fetchone()
    return {
        "status": "running",
        "version": "0.3.0",
        "tasks_logged": total,
        "tasks_success": success,
        "models_tracked": models,
        "last_task_at": latest[0].isoformat() if latest else None,
        "storage": "postgresql (Railway managed)"
    }

@app.get("/api/v1/rankings")
async def get_rankings():
    """Live model rankings aggregated from real task data."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    model,
                    task_type                                           AS category,
                    COUNT(*)                                            AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric, 4)
                                                                        AS success_rate,
                    ROUND(AVG(duration_s)::numeric, 2)                 AS avg_duration,
                    ROUND(AVG(cost_cents)::numeric, 4)                 AS avg_cost_cents
                FROM tasks
                GROUP BY model, task_type
                ORDER BY success_rate DESC, tasks_logged DESC
            """)
            rows = cur.fetchall()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_rows": len(rows),
        "models": [dict(r) for r in rows]
    }

@app.get("/api/v1/recommendations")
async def get_recommendations():
    """Generate insights from real PostgreSQL data."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE success = TRUE")
            success = cur.fetchone()[0]
            cur.execute("SELECT AVG(duration_s) FROM tasks")
            avg_dur = cur.fetchone()[0] or 0

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
                "action": "Review failure notes for recurring error patterns."
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
