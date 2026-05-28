# AgentOptima API v0.4.0 — API key auth + progress tracking
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os, hashlib, psycopg2, psycopg2.extras
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# ── Database ───────────────────────────────────────────────────────────────────
_clean_env  = {k.strip(): v for k, v in os.environ.items()}
_raw_url    = (_clean_env.get("DATABASE_URL") or _clean_env.get("POSTGRES_URL") or
               _clean_env.get("POSTGRESQL_URL") or _clean_env.get("DATABASE_PRIVATE_URL") or "")
DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1) if _raw_url else None
print(f"🔍 DB URL detected: {'YES (' + _raw_url[:20] + '...)' if _raw_url else 'NO'}")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id          SERIAL PRIMARY KEY,
                        task_id     TEXT NOT NULL,
                        task_type   TEXT,
                        task_desc   TEXT,
                        model       TEXT,
                        duration_s  INTEGER,
                        cost_cents  REAL,
                        success     BOOLEAN,
                        notes       TEXT,
                        agent_name  TEXT DEFAULT 'aris',
                        logged_at   TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id          SERIAL PRIMARY KEY,
                        task_id     TEXT NOT NULL,
                        rating      INTEGER CHECK (rating BETWEEN 1 AND 5),
                        label       TEXT,
                        notes       TEXT,
                        rated_at    TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id          SERIAL PRIMARY KEY,
                        key_hash    TEXT NOT NULL UNIQUE,
                        agent_name  TEXT NOT NULL,
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        active      BOOLEAN DEFAULT TRUE
                    )
                """)
                # Seed Aris master key (idempotent)
                master_key  = os.environ.get("ARIS_API_KEY", "ao-41727e957d734ef638903180293af0d6171efda7373902e6")
                master_hash = hashlib.sha256(master_key.encode()).hexdigest()
                cur.execute("""
                    INSERT INTO api_keys (key_hash, agent_name)
                    VALUES (%s, 'aris')
                    ON CONFLICT (key_hash) DO NOTHING
                """, (master_hash,))
                # Migration: add agent_name column if missing
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS agent_name TEXT DEFAULT 'aris'
                """)
            conn.commit()
        print("✅ PostgreSQL ready (v0.4.0)")
    except Exception as e:
        print(f"⚠️  DB init warning: {e}")

# ── Auth helper ────────────────────────────────────────────────────────────────
def verify_key(x_api_key: Optional[str]) -> str:
    """Verify API key, return agent_name. Raises 401 if invalid."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent_name FROM api_keys WHERE key_hash=%s AND active=TRUE",
                (key_hash,)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return row[0]

# ── App ────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("🚀 AgentOptima API v0.4.0 starting...")
    print(f"   Port: {os.environ.get('PORT', 8000)}")
    yield

app = FastAPI(title="AgentOptima API", version="0.4.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Models ─────────────────────────────────────────────────────────────────────
class TrackRequest(BaseModel):
    task_id: str
    task_type: str
    task_description: str
    model: str
    duration_seconds: Optional[int]  = None
    cost_cents: Optional[float]      = None
    success: Optional[bool]          = None
    notes: Optional[str]             = None

# ── Public endpoints ───────────────────────────────────────────────────────────
@app.get("/")
async def dashboard():
    for path in ["/app/dashboard.html", "/app/index.html"]:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "Dashboard not found"}, status_code=500)

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.4.0"}

@app.get("/api/v1/status")
async def get_status():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE success=TRUE")
            success = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT model) FROM tasks")
            models = cur.fetchone()[0]
            cur.execute("SELECT logged_at FROM tasks ORDER BY id DESC LIMIT 1")
            latest = cur.fetchone()
    return {"status": "running", "version": "0.4.0", "tasks_logged": total,
            "tasks_success": success, "models_tracked": models,
            "last_task_at": latest[0].isoformat() if latest else None,
            "storage": "postgresql (Railway managed)"}

@app.get("/api/v1/models")
async def get_models():
    MODEL_POOL = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                  "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-flash:free",
                  "openai/gpt-4o-mini"]
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT model, COUNT(*) AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(duration_s)::numeric,2) AS avg_duration_s,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents
                FROM tasks GROUP BY model
            """)
            rows = {r["model"]: dict(r) for r in cur.fetchall()}
    return {"pool_size": len(MODEL_POOL), "models": [
        {"model": m, "in_pool": True,
         "tasks_logged":   rows[m]["tasks_logged"]   if m in rows else 0,
         "success_rate":   rows[m]["success_rate"]   if m in rows else None,
         "avg_duration_s": rows[m]["avg_duration_s"] if m in rows else None,
         "avg_cost_cents": rows[m]["avg_cost_cents"] if m in rows else None}
        for m in MODEL_POOL]}

@app.get("/api/v1/rankings")
async def get_rankings():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT model, task_type AS category, COUNT(*) AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(duration_s)::numeric,2) AS avg_duration,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents
                FROM tasks GROUP BY model, task_type
                ORDER BY success_rate DESC, tasks_logged DESC
            """)
            rows = cur.fetchall()
    return {"generated_at": datetime.utcnow().isoformat(),
            "total_rows": len(rows), "models": [dict(r) for r in rows]}

@app.get("/api/v1/progress")
async def get_progress():
    """Per-model, per-category task counts vs target (10) for data-driven routing."""
    TARGET = 10
    CATEGORIES = ["coding", "research", "strategy", "writing", "data", "general"]
    MODEL_POOL  = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                   "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-flash:free",
                   "openai/gpt-4o-mini"]
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT model, task_type, COUNT(*) AS count
                FROM tasks GROUP BY model, task_type
            """)
            rows = cur.fetchall()
    counts = {}
    for r in rows:
        counts.setdefault(r["model"], {})[r["task_type"]] = r["count"]
    result = []
    for model in MODEL_POOL:
        model_counts = counts.get(model, {})
        categories   = {cat: int(model_counts.get(cat, 0)) for cat in CATEGORIES}
        total        = sum(categories.values())
        data_driven  = sum(1 for v in categories.values() if v >= TARGET)
        result.append({"model": model, "categories": categories,
                        "total_tasks": total, "target_per_category": TARGET,
                        "data_driven_categories": data_driven,
                        "total_categories": len(CATEGORIES),
                        "pct_complete": round(
                            sum(min(v, TARGET) for v in categories.values()) /
                            (TARGET * len(CATEGORIES)) * 100, 1)})
    overall = round(
        sum(min(r["categories"].get(c, 0), TARGET)
            for r in result for c in CATEGORIES) /
        (TARGET * len(CATEGORIES) * len(MODEL_POOL)) * 100, 1)
    return {"target_per_category": TARGET, "categories": CATEGORIES,
            "models": result, "overall_pct": overall}

@app.get("/api/v1/recommend")
async def get_recommendation(task_type: str = "general", min_tasks: int = 10):
    MODEL_POOL = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                  "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-flash:free",
                  "openai/gpt-4o-mini"]
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT model, COUNT(*) AS tasks,
                    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
                    AVG(duration_s) AS avg_duration, AVG(cost_cents) AS avg_cost_cents
                FROM tasks WHERE task_type=%s
                GROUP BY model HAVING COUNT(*) >= %s
                ORDER BY AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) DESC, AVG(cost_cents) ASC
            """, (task_type, min_tasks))
            rows = cur.fetchall()
    if not rows:
        return {"mode": "round-robin",
                "reason": f"insufficient_data (need {min_tasks}+ tasks per model for '{task_type}')",
                "recommended_model": None, "pool": MODEL_POOL}
    best = dict(rows[0])
    return {"mode": "data-driven", "task_type": task_type,
            "recommended_model": best["model"],
            "success_rate": round(float(best["success_rate"]), 4),
            "avg_cost_cents": round(float(best["avg_cost_cents"]), 4),
            "avg_duration_s": round(float(best["avg_duration"]), 1),
            "based_on_tasks": int(best["tasks"]),
            "all_candidates": [dict(r) for r in rows]}

@app.get("/api/v1/recommendations")
async def get_recommendations():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE success=TRUE")
            success = cur.fetchone()[0]
            cur.execute("SELECT AVG(duration_s) FROM tasks")
            avg_dur = cur.fetchone()[0] or 0
    recommendations, summary = [], ""
    if total == 0:
        summary = "No data yet."
        recommendations.append({"priority": "high", "category": "onboarding",
                                 "message": "No tasks logged yet.",
                                 "action": "Run tasks through the Aris orchestrator."})
    else:
        rate    = success / total
        summary = (f"{total} tasks | Success: {success}/{total} ({rate*100:.0f}%) | "
                   f"Avg duration: {avg_dur:.1f}s")
        if rate < 0.8:
            recommendations.append({"priority": "high", "category": "reliability",
                                     "message": f"Success rate {rate*100:.0f}% below 80% target.",
                                     "action": "Review failure notes for error patterns."})
        else:
            recommendations.append({"priority": "low", "category": "optimization",
                                     "message": f"Success rate {rate*100:.0f}% is healthy \u2705",
                                     "action": None})
        if avg_dur > 300:
            recommendations.append({"priority": "medium", "category": "performance",
                                     "message": f"Avg duration {avg_dur:.0f}s is high.",
                                     "action": "Consider breaking long tasks into subtasks."})
    return {"recommendations": recommendations,
            "last_updated": datetime.utcnow().isoformat(), "summary": summary}

# ── Protected endpoints (require API key) ──────────────────────────────────────
@app.post("/api/v1/track")
async def track_task(request: TrackRequest,
                     x_api_key: Optional[str] = Header(default=None)):
    agent_name = verify_key(x_api_key)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tasks
                    (task_id, task_type, task_desc, model, duration_s,
                     cost_cents, success, notes, agent_name)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (request.task_id, request.task_type, request.task_description,
                  request.model, request.duration_seconds, request.cost_cents,
                  request.success, request.notes, agent_name))
        conn.commit()
    print(f"💾 [{agent_name}] {request.task_id} ({request.task_type}) [{request.model}]")
    return {"status": "success", "message": f"Task {request.task_id} logged",
            "task_id": request.task_id, "agent": agent_name}
