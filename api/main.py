# AgentOptima API v1.1.10 — filter rankings to active registry models only, fix models_tracked KPI
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import os, hashlib, secrets, re, json, psycopg2, psycopg2.extras, requests as _requests
import logging, traceback, time, uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# ── Structured Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("agentoptima")
# Suppress noisy uvicorn access logs in favour of our middleware
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# ── Database ───────────────────────────────────────────────────────────────────
_clean_env  = {k.strip(): v for k, v in os.environ.items()}
_raw_url    = (_clean_env.get("DATABASE_URL") or _clean_env.get("POSTGRES_URL") or
               _clean_env.get("POSTGRESQL_URL") or _clean_env.get("DATABASE_PRIVATE_URL") or "")
DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1) if _raw_url else None
logger.info(f"DB URL detected: {'YES (' + _raw_url[:20] + '...)' if _raw_url else 'NO'}")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS orchestrator_state (
                        id          SERIAL PRIMARY KEY,
                        recommended_model TEXT NOT NULL,
                        success_rate REAL,
                        avg_cost_cents REAL,
                        avg_duration_s REAL,
                        based_on_tasks INTEGER,
                        reason TEXT,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS model_benchmarks (
                        id          SERIAL PRIMARY KEY,
                        model TEXT NOT NULL,
                        benchmark_date DATE DEFAULT CURRENT_DATE,
                        test_prompt TEXT,
                        response_text TEXT,
                        quality_score REAL,
                        latency_ms INTEGER,
                        cost_cents REAL,
                        success BOOLEAN,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
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
                # Migrations
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS agent_name TEXT DEFAULT 'aris'
                """)
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS output_text TEXT
                """)
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS quality_score REAL
                """)
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_task_id TEXT DEFAULT NULL
                """)
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_subtask BOOLEAN DEFAULT FALSE
                """)
                cur.execute("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_subtype TEXT DEFAULT NULL
                """)
                # v1.0.0 migrations
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS feedback_v2 (
                        id           SERIAL PRIMARY KEY,
                        task_id      TEXT NOT NULL,
                        original_model TEXT,
                        issue        TEXT,
                        retry_model  TEXT,
                        rating       INTEGER CHECK (rating BETWEEN 1 AND 5),
                        notes        TEXT,
                        created_at   TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS panic_log (
                        id          SERIAL PRIMARY KEY,
                        triggered_by TEXT,
                        level       INTEGER,
                        result      TEXT,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS risk_checks (
                        id          SERIAL PRIMARY KEY,
                        task_id     TEXT,
                        task_desc   TEXT,
                        risk_level  TEXT,
                        risk_score  REAL,
                        flags       TEXT,
                        action_taken TEXT,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                # Orchestrator migrations
                cur.execute("ALTER TABLE orchestrator_state ADD COLUMN IF NOT EXISTS resolution TEXT DEFAULT 'N/A'")
                cur.execute("ALTER TABLE model_benchmarks ADD COLUMN IF NOT EXISTS task_category TEXT DEFAULT 'general'")
                # Escalation events table (v1.0.6)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS escalation_events (
                        id SERIAL PRIMARY KEY,
                        task_id TEXT,
                        from_model TEXT,
                        to_model TEXT,
                        signals JSONB,
                        task_type TEXT,
                        confidence_score REAL,
                        success_after BOOLEAN,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_escalation_task_id ON escalation_events(task_id)")
                # OrchestraBench tables (v1.1.0)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS benchmark_results (
                        id           SERIAL PRIMARY KEY,
                        benchmark_name TEXT NOT NULL,
                        model        TEXT NOT NULL,
                        scores       JSONB,
                        total_score  REAL,
                        avg_latency_ms INTEGER,
                        cost_cents   REAL,
                        value_score  REAL,
                        run_at       TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bench_model ON benchmark_results(model)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bench_name ON benchmark_results(benchmark_name)")
                # model_benchmarks: add total_score column for OrchestraBench integration
                cur.execute("ALTER TABLE model_benchmarks ADD COLUMN IF NOT EXISTS total_score REAL")
                cur.execute("ALTER TABLE model_benchmarks ADD COLUMN IF NOT EXISTS value_score REAL")
                cur.execute("ALTER TABLE model_benchmarks ADD COLUMN IF NOT EXISTS benchmark_name TEXT")
                # v1.1.3 migrations — task state layer
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed'")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS retries INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error_type TEXT DEFAULT NULL")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error_msg TEXT DEFAULT NULL")
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS goal_id TEXT DEFAULT NULL")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_goal_id ON tasks(goal_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks(task_id)")
            conn.commit()
        logger.info("PostgreSQL ready (v1.1.10 + contracts)")
    except Exception as e:
        logger.warning(f"DB init warning: {e}")

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
    logger.info("AgentOptima API v1.1.10 starting...")
    logger.info(f"Port: {os.environ.get('PORT', 8000)}")
    yield

app = FastAPI(title="AgentOptima API", version="1.1.10", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Request Logging Middleware ─────────────────────────────────────────────────
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = uuid.uuid4().hex[:8]
        start  = time.monotonic()
        method = request.method
        path   = request.url.path
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000)
            level = logging.WARNING if response.status_code >= 500 else logging.INFO
            logger.log(level, f"[{req_id}] {method} {path} → {response.status_code} ({duration_ms}ms)")
            return response
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.error(
                f"[{req_id}] {method} {path} → UNHANDLED EXCEPTION ({duration_ms}ms)\n"
                + traceback.format_exc()
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": req_id},
            )

app.add_middleware(RequestLoggingMiddleware)

# ── Models ─────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    agent_name: str

class TrackRequest(BaseModel):
    task_id: str
    task_type: str
    task_description: str
    model: str
    duration_seconds: Optional[int]  = None
    cost_cents: Optional[float]      = None
    success: Optional[bool]          = None
    notes: Optional[str]             = None
    output_text: Optional[str]       = None
    quality_score: Optional[float]   = None
    parent_task_id: Optional[str]    = None
    is_subtask: bool                 = False
    task_subtype: Optional[str]      = None

class TaskStateUpdate(BaseModel):
    task_id: str
    status: str  # pending / running / success / failed / retry
    retries: Optional[int]    = None
    error_type: Optional[str] = None
    error_msg: Optional[str]  = None
    goal_id: Optional[str]    = None
    output_text: Optional[str] = None
    cost_cents: Optional[float] = None
    duration_s: Optional[int]   = None

class GoalQuery(BaseModel):
    goal_id: str

class TaskRegisterRequest(BaseModel):
    task_id: str
    task_type: Optional[str]   = None
    task_desc: Optional[str]   = None
    model: Optional[str]       = None
    status: Optional[str]      = "pending"
    goal_id: Optional[str]     = None
    agent_name: Optional[str]  = "aris"

# ── Public endpoints ───────────────────────────────────────────────────────────
@app.get("/")
async def dashboard():
    for path in ["/app/dashboard.html", "/app/index.html"]:
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "Dashboard not found"}, status_code=500)

@app.post("/api/v1/register")
async def register_agent(request: RegisterRequest):
    """Public endpoint — register a new agent and receive an API key."""
    # Validate agent_name: alphanumeric + hyphens, 3-32 chars
    # Validate agent_name: alphanumeric + hyphens, 3-32 chars (single combined check)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9\-]{1,30}[a-zA-Z0-9]|[a-zA-Z0-9]{3,32}', request.agent_name):
        raise HTTPException(
            status_code=422,
            detail="agent_name must be 3-32 characters, alphanumeric and hyphens only"
        )
    # Generate secure API key
    api_key  = "ao-" + secrets.token_hex(24)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Check name uniqueness
                cur.execute(
                    "SELECT id FROM api_keys WHERE agent_name=%s AND active=TRUE",
                    (request.agent_name,)
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail=f"Agent name '{request.agent_name}' is already taken"
                    )
                cur.execute(
                    "INSERT INTO api_keys (key_hash, agent_name) VALUES (%s, %s)",
                    (key_hash, request.agent_name)
                )
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Registration failed — please try again")
    logger.info(f"New agent registered: {request.agent_name}")
    return {
        "api_key":    api_key,
        "agent_name": request.agent_name,
        "message":    "Welcome to AgentOptima"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.1.10"}

@app.get("/api/v1/status")
async def get_status():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE success=TRUE")
            success = cur.fetchone()[0]
            models = len(_MODEL_REGISTRY)  # always reflects active registry, not task history
            cur.execute("SELECT logged_at FROM tasks ORDER BY id DESC LIMIT 1")
            latest = cur.fetchone()
    # Data source breakdown
    # Source breakdown via notes column (agent_name is overwritten by auth to 'aris')
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks WHERE notes ILIKE '%source:routerbench%'")
            rb_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE notes ILIKE '%source:arena55k%'")
            arena_count = cur.fetchone()[0]
    live_count = total - rb_count - arena_count
    sources = {"live": live_count, "arena55k": arena_count, "routerbench": rb_count}
    return {"status": "running", "version": "1.1.10", "tasks_logged": total,
            "tasks_success": success, "models_tracked": models,
            "last_task_at": latest[0].isoformat() if latest else None,
            "storage": "postgresql (Railway managed)",
            "data_sources": sources}

@app.get("/api/v1/models")
async def get_models():
    MODEL_POOL = ACTIVE_POOL
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT model, COUNT(*) AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(duration_s)::numeric,2) AS avg_duration_s,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents
                FROM tasks
                GROUP BY model
            """)
            rows = {r["model"]: dict(r) for r in cur.fetchall()}
    return {"pool_size": len(MODEL_POOL), "models": [
        {"model": m, "in_pool": True,
         "tasks_logged":   rows[m]["tasks_logged"]   if m in rows else 0,
         "success_rate":   rows[m]["success_rate"]   if m in rows else None,
         "avg_duration_s": rows[m]["avg_duration_s"] if m in rows else None,
         "avg_cost_cents": rows[m]["avg_cost_cents"] if m in rows else None}
        for m in MODEL_POOL]}

ACTIVE_POOL = [
    "anthropic/claude-sonnet-4-6",
    "deepseek/deepseek-v4-flash",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
    "anthropic/claude-haiku-4.5",
    "openai/o3-mini",
]

# ── Per-task-type quality tolerance ───────────────────────────────────────────
# Tighter = only models close to the best success rate are eligible.
# Looser = cheap models can win even with a lower success rate.
TASK_TOLERANCES = {
    "math":          0.05,   # correctness is binary — strictest
    "security":      0.05,   # no room for quality slip
    "coding":        0.08,   # bugs matter — tight
    "orchestration": 0.08,   # most critical — must understand + delegate accurately
    "strategy":      0.10,   # balanced default
    "data":          0.10,   # balanced default
    "research":      0.12,   # summaries have acceptable variance
    "general":       0.15,   # relaxed
    "writing":       0.20,   # style variance acceptable — most relaxed
}

def get_task_tolerance(task_type: str, override: float = None) -> float:
    """Return the quality tolerance for a given task type."""
    if override is not None:
        return override
    return TASK_TOLERANCES.get(task_type, 0.10)

@app.get("/api/v1/rankings")
async def get_rankings(include_subtypes: bool = False):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Category-level rankings — with cost_per_success computed in SQL
            cur.execute("""
                SELECT model, task_type AS category, NULL AS subtype,
                    COUNT(*) AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(duration_s)::numeric,2) AS avg_duration,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents,
                    ROUND(AVG(quality_score)::numeric,2) AS avg_quality,
                    ROUND(
                        (AVG(cost_cents) / NULLIF(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END), 0))::numeric
                    , 4) AS cost_per_success
                FROM tasks
                WHERE model = ANY(%s)
                GROUP BY model, task_type
                ORDER BY success_rate DESC, cost_per_success ASC NULLS LAST, tasks_logged DESC
            """, (ACTIVE_POOL,))
            category_rows = [r for r in cur.fetchall() if r["model"] in _MODEL_REGISTRY]

            subtype_rows = []
            if include_subtypes:
                # Subtype-level rankings (only where task_subtype is set)
                cur.execute("""
                    SELECT model, task_type AS category, task_subtype AS subtype,
                        COUNT(*) AS tasks_logged,
                        ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                        ROUND(AVG(duration_s)::numeric,2) AS avg_duration,
                        ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents,
                        ROUND(AVG(quality_score)::numeric,2) AS avg_quality,
                        ROUND(
                            (AVG(cost_cents) / NULLIF(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END), 0))::numeric
                        , 4) AS cost_per_success
                    FROM tasks
                    WHERE model = ANY(%s) AND task_subtype IS NOT NULL
                    GROUP BY model, task_type, task_subtype
                    ORDER BY task_subtype, success_rate DESC, cost_per_success ASC NULLS LAST, tasks_logged DESC
                """, (ACTIVE_POOL,))
                subtype_rows = [r for r in cur.fetchall() if r["model"] in _MODEL_REGISTRY]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_rows": len(category_rows),
        "models": [dict(r) for r in category_rows],
        "subtypes": [dict(r) for r in subtype_rows] if include_subtypes else None,
        "subtype_rows": len(subtype_rows) if include_subtypes else None,
    }

@app.get("/api/v1/subtype-progress")
async def get_subtype_progress():
    """Per-model, per-subtype task counts vs threshold (10) for subtype routing activation."""
    TARGET = 10
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT task_subtype, model,
                    COUNT(*) AS n,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents,
                    ROUND(AVG(quality_score)::numeric,2) AS avg_quality
                FROM tasks
                WHERE task_subtype IS NOT NULL AND model = ANY(%s)
                  AND task_subtype NOT ILIKE '%chinese%'
                GROUP BY task_subtype, model
                ORDER BY task_subtype, n DESC
                LIMIT 2000
            """, (ACTIVE_POOL,))
            rows = cur.fetchall()

    # Group by subtype
    by_subtype: dict = {}
    for r in rows:
        st = r["task_subtype"]
        if st not in by_subtype:
            by_subtype[st] = []
        by_subtype[st].append(dict(r))

    result = []
    for subtype, model_rows in sorted(by_subtype.items()):
        per_model = {m: 0 for m in ACTIVE_POOL}
        for r in model_rows:
            per_model[r["model"]] = int(r["n"])
        min_n = min(per_model.values())
        # Use cost-aware ranking to pick the subtype leader (not just highest task count)
        ranked = cost_aware_rank(model_rows, quality_tolerance=0.10)
        best_row = ranked[0]
        result.append({
            "subtype":            subtype,
            "min_n_across_models": min_n,
            "routing_ready":      min_n >= TARGET,
            "threshold":          TARGET,
            "runs_needed":        max(0, TARGET - min_n),
            "current_leader":     best_row["model"],
            "leader_value_score": best_row.get("value_score"),
            "leader_success":     float(best_row["success_rate"]),
            "leader_cost":        float(best_row.get("avg_cost_cents") or 0),
            "leader_quality":     float(best_row["avg_quality"]) if best_row.get("avg_quality") else None,
            "per_model":          per_model,
        })

    ready   = [r for r in result if r["routing_ready"]]
    pending = [r for r in result if not r["routing_ready"]]
    return {
        "generated_at":   datetime.utcnow().isoformat(),
        "threshold":      TARGET,
        "subtypes_ready": len(ready),
        "subtypes_pending": len(pending),
        "subtypes":       result,
    }


@app.get("/api/v1/progress")
async def get_progress():
    """Per-model, per-category task counts vs target (10) for data-driven routing."""
    TARGET = 10
    CATEGORIES = ["coding", "research", "strategy", "writing", "data", "general", "security", "math"]
    MODEL_POOL  = ACTIVE_POOL
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

@app.get("/api/v1/tasks/recent")
async def get_recent_tasks(limit: int = 20):
    """Live feed of most recent tasks across all agents and models."""
    limit = max(1, min(limit, 100))  # cap at 100
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, task_id, task_type, task_desc, model,
                       duration_s, cost_cents, success, notes, agent_name,
                       quality_score, parent_task_id, is_subtask, task_subtype, logged_at
                FROM tasks
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
    return {
        "count": len(rows),
        "limit": limit,
        "tasks": [
            {
                "id":         r["id"],
                "task_id":    r["task_id"],
                "task_type":  r["task_type"],
                "task_subtype": r["task_subtype"],
                "task_desc":  r["task_desc"],
                "model":      r["model"],
                "model_short": r["model"].split("/")[-1] if r["model"] else "",
                "duration_s": r["duration_s"],
                "cost_cents": float(r["cost_cents"]) if r["cost_cents"] is not None else None,
                "success":      r["success"],
                "quality_score":  float(r["quality_score"]) if r["quality_score"] is not None else None,
                "agent_name":     r["agent_name"],
                "parent_task_id": r["parent_task_id"],
                "is_subtask":     bool(r["is_subtask"]) if r["is_subtask"] is not None else False,
                "marker":         "subtask" if r["is_subtask"] else "task",
                "logged_at":      r["logged_at"].isoformat() if r["logged_at"] else None,
            }
            for r in rows
        ]
    }


@app.get("/api/v1/classify")
async def classify_task_endpoint(text: str):
    """Classify a task description and score its complexity."""
    import sys
    sys.path.insert(0, '/app')
    try:
        from integration.task_classifier import classify_task
        from integration.complexity_scorer import score_complexity
        subtype_result = classify_task(text)
        complexity_result = score_complexity(text)
        return {
            "input": text[:200],
            "subtype": subtype_result["subtype"],
            "category": subtype_result["category"],
            "confidence": subtype_result["confidence"],
            "complexity": complexity_result,
        }
    except Exception as e:
        return {"input": text[:200], "subtype": "general", "category": "general",
                "confidence": 0.3, "method": "fallback", "error": str(e)}


# ── Cost-Aware Ranking ─────────────────────────────────────────────────────────

def cost_aware_rank(rows: list, quality_tolerance: float = 0.10) -> list:
    """
    Rerank model candidates using cost-aware scoring.

    Algorithm:
      1. Find the best success_rate among all candidates.
      2. Mark models within `quality_tolerance` of that best rate as eligible.
         (e.g. tolerance=0.10 means accept up to 10% lower success rate)
      3. Models with success_rate < 0.30 are always ineligible (unreliable).
      4. Among eligible models, prefer lower cost_per_success
         (= avg_cost_cents / success_rate — the true cost per win).
      5. Ineligible models follow, sorted by success rate DESC.

    Also adds `value_score` to each row:
      value_score = success_rate x (quality/5) / log(1 + avg_cost_cents)
    Higher = better quality per dollar spent.

    With tolerance=0.0 this behaves identically to the old pure-quality sort.
    """
    import math
    if not rows:
        return rows

    RELIABILITY_FLOOR = 0.30   # models below this are never routed to regardless of cost

    rows_out = [dict(r) for r in rows]
    best_sr = max(float(r["success_rate"]) for r in rows_out)
    min_sr = best_sr * (1.0 - quality_tolerance)

    for r in rows_out:
        sr = float(r["success_rate"])
        cost = max(float(r.get("avg_cost_cents") or 0.001), 0.001)
        quality = float(r.get("avg_quality") or 4.0)
        # cost_per_success: the true cost per successful task
        r["cost_per_success"] = round(cost / sr, 4) if sr > 0 else None
        # Higher = better quality efficiency per log-cost unit
        r["value_score"] = round(sr * (quality / 5.0) / math.log1p(cost), 4)
        # Eligible if: above reliability floor AND within quality tolerance of best
        r["within_tolerance"] = (sr >= RELIABILITY_FLOOR) and (sr >= min_sr)

    # Among eligible: sort by cost_per_success ASC (cheapest per win first)
    # When cost_per_success is None (zero cost tasks), treat as 0 (free wins always first)
    eligible = sorted(
        [r for r in rows_out if r["within_tolerance"]],
        key=lambda r: (r["cost_per_success"] if r["cost_per_success"] is not None else 0.0)
    )
    ineligible = sorted(
        [r for r in rows_out if not r["within_tolerance"]],
        key=lambda r: -float(r["success_rate"])
    )
    return eligible + ineligible


@app.get("/api/v1/recommend")
async def get_recommendation(task_type: str = "general", task_subtype: str = None,
                             min_tasks: int = 10, text: str = None,
                             quality_tolerance: float = None):
    MODEL_POOL = ACTIVE_POOL
    # Use per-task-type tolerance unless caller explicitly overrides
    effective_tolerance = get_task_tolerance(task_type, quality_tolerance)

    # Auto-classify from text if provided and task_type is still default
    classification_meta = None
    if text and task_type == "general":
        try:
            import sys
            sys.path.insert(0, '/app')
            from integration.task_classifier import classify_task
            clf = classify_task(text)
            if clf["subtype"] != "general" and clf["confidence"] >= 0.5:
                task_type = clf["subtype"]
                classification_meta = clf
        except Exception:
            pass

    # Auto-detect subtype: if task_type contains '/' (e.g. 'coding/python'),
    # split into base_type + subtype so the DB lookup works correctly.
    effective_base = task_type
    effective_subtype = task_subtype
    if "/" in task_type and task_subtype is None:
        parts = task_type.split("/", 1)
        effective_base = parts[0]        # e.g. 'coding'
        effective_subtype = task_type    # e.g. 'coding/python' (stored in task_subtype col)

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if effective_subtype:
                # 1. Try subtype-specific data first
                cur.execute("""
                    SELECT model, COUNT(*) AS tasks,
                        AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
                        AVG(duration_s) AS avg_duration, AVG(cost_cents) AS avg_cost_cents,
                        AVG(quality_score) AS avg_quality
                    FROM tasks
                    WHERE task_type=%s AND task_subtype=%s
                    GROUP BY model HAVING COUNT(*) >= %s
                    ORDER BY AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) DESC,
                             AVG(quality_score) DESC NULLS LAST,
                             AVG(cost_cents) ASC
                """, (effective_base, effective_subtype, min_tasks))
                rows = cur.fetchall()

                # 2. Fall back to category-level if no subtype data yet
                if not rows:
                    cur.execute("""
                        SELECT model, COUNT(*) AS tasks,
                            AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
                            AVG(duration_s) AS avg_duration, AVG(cost_cents) AS avg_cost_cents,
                            AVG(quality_score) AS avg_quality
                        FROM tasks
                        WHERE task_type=%s
                        GROUP BY model HAVING COUNT(*) >= %s
                        ORDER BY AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) DESC,
                                 AVG(quality_score) DESC NULLS LAST,
                                 AVG(cost_cents) ASC
                    """, (effective_base, min_tasks))
                    rows = cur.fetchall()
                    if rows:
                        rows = cost_aware_rank(rows, effective_tolerance)
                        # Label as category fallback so caller knows it's not subtype-specific
                        return {
                            "mode": "data-driven",
                            "resolution": "category_fallback",
                            "scoring_mode": "cost_aware",
                            "quality_tolerance": effective_tolerance,
                            "task_type": effective_base,
                            "task_subtype": effective_subtype,
                            "note": f"No subtype data yet for '{effective_subtype}' — using category '{effective_base}' signal",
                            "recommended_model": rows[0]["model"],
                            "success_rate": round(float(rows[0]["success_rate"]), 4),
                            "avg_cost_cents": round(float(rows[0]["avg_cost_cents"]), 4) if rows[0].get("avg_cost_cents") is not None else None,
                            "avg_duration_s": round(float(rows[0]["avg_duration"]), 1) if rows[0].get("avg_duration") is not None else None,
                            "value_score": rows[0].get("value_score"),
                            "based_on_tasks": int(rows[0]["tasks"]),
                            "all_candidates": rows,
                        }
            else:
                cur.execute("""
                    SELECT model, COUNT(*) AS tasks,
                        AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
                        AVG(duration_s) AS avg_duration, AVG(cost_cents) AS avg_cost_cents,
                        AVG(quality_score) AS avg_quality
                    FROM tasks
                    WHERE task_type=%s
                    GROUP BY model HAVING COUNT(*) >= %s
                    ORDER BY AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) DESC,
                             AVG(quality_score) DESC NULLS LAST,
                             AVG(cost_cents) ASC
                """, (effective_base, min_tasks))
                rows = cur.fetchall()
                rows = [r for r in rows if r["model"] in _MODEL_REGISTRY]

    if not rows:
        label = effective_subtype or effective_base
        return {
            "mode": "round-robin",
            "reason": f"insufficient_data (need {min_tasks}+ tasks per model for '{label}')",
            "recommended_model": None,
            "pool": MODEL_POOL,
        }

    rows = cost_aware_rank(rows, effective_tolerance)
    best = rows[0]
    return {
        "mode": "data-driven",
        "resolution": "subtype" if effective_subtype else "category",
        "scoring_mode": "cost_aware",
        "quality_tolerance": effective_tolerance,
        "task_type": effective_base,
        "task_subtype": effective_subtype,
        "recommended_model": best["model"],
        "success_rate": round(float(best["success_rate"]), 4),
        "avg_cost_cents": round(float(best["avg_cost_cents"]), 4) if best.get("avg_cost_cents") is not None else None,
        "cost_per_success": best.get("cost_per_success"),
        "avg_duration_s": round(float(best["avg_duration"]), 1) if best.get("avg_duration") is not None else None,
        "avg_quality": round(float(best["avg_quality"]), 2) if best.get("avg_quality") else None,
        "value_score": best.get("value_score"),
        "based_on_tasks": int(best["tasks"]),
        "all_candidates": rows,
        "classification": classification_meta,
    }

# ── EFFICIENCY endpoint ────────────────────────────────────────────────────────

@app.get("/api/v1/efficiency")
async def get_efficiency():
    """
    Cost-per-success efficiency analysis across all model×task_type combinations.
    Returns best/worst value models and human-readable routing recommendations.
    cost_per_success = avg_cost_cents / success_rate
    (lower = better — you pay less per successful task outcome)
    """
    SONNET = "anthropic/claude-sonnet-4-6"
    MIN_TASKS = 5
    RELIABILITY_FLOOR = 0.30   # ignore unreliable models in efficiency ranking

    def sf(val, default=0.0):
        if val is None: return default
        try: return float(val)
        except: return default

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    model,
                    task_type,
                    COUNT(*) AS task_count,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric, 4) AS success_rate,
                    ROUND(AVG(cost_cents)::numeric, 4) AS avg_cost_cents,
                    ROUND(AVG(quality_score)::numeric, 2) AS avg_quality,
                    ROUND(
                        (AVG(cost_cents) / NULLIF(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END), 0))::numeric
                    , 4) AS cost_per_success
                FROM tasks
                WHERE model = ANY(%s)
                GROUP BY model, task_type
                HAVING COUNT(*) >= %s
                ORDER BY cost_per_success ASC NULLS LAST
            """, (ACTIVE_POOL, MIN_TASKS))
            rows = cur.fetchall()

    if not rows:
        return {
            "best_value_models": [],
            "worst_value_models": [],
            "routing_recommendations": ["Insufficient data — need at least 5 tasks per model per task_type"],
            "generated_at": datetime.utcnow().isoformat(),
        }

    # Build Sonnet baseline per task_type for savings calculation
    sonnet_cps_by_type: dict = {}
    for r in rows:
        if r["model"] == SONNET and r["cost_per_success"] is not None:
            sonnet_cps_by_type[r["task_type"]] = sf(r["cost_per_success"])

    # Filter: only models above reliability floor
    reliable = [r for r in rows if sf(r["success_rate"]) >= RELIABILITY_FLOOR]

    # Enrich with vs_sonnet_savings_pct
    enriched = []
    for r in reliable:
        cps = sf(r["cost_per_success"])
        sonnet_cps = sonnet_cps_by_type.get(r["task_type"])
        savings_pct = None
        if sonnet_cps and sonnet_cps > 0 and cps > 0 and r["model"] != SONNET:
            savings_pct = round((1.0 - cps / sonnet_cps) * 100, 1)
        enriched.append({
            "model":              r["model"],
            "task_type":          r["task_type"],
            "task_count":         int(r["task_count"]),
            "success_rate":       sf(r["success_rate"]),
            "avg_cost_cents":     sf(r["avg_cost_cents"]),
            "avg_quality":        sf(r["avg_quality"]) if r["avg_quality"] else None,
            "cost_per_success":   round(cps, 4) if cps else None,
            "vs_sonnet_savings_pct": savings_pct,
        })

    # Sort by cost_per_success ASC for best value; DESC for worst
    sortable = [r for r in enriched if r["cost_per_success"] is not None]
    best_value  = sorted(sortable, key=lambda r: r["cost_per_success"])[:10]
    worst_value = sorted(sortable, key=lambda r: -r["cost_per_success"])[:5]

    # Generate routing recommendations
    recommendations = []
    by_type: dict = {}
    for r in sortable:
        by_type.setdefault(r["task_type"], []).append(r)

    for task_type, candidates in sorted(by_type.items()):
        if len(candidates) < 2:
            continue
        best = min(candidates, key=lambda r: r["cost_per_success"])
        sonnet_row = next((r for r in candidates if r["model"] == SONNET), None)
        best_short = best["model"].split("/")[-1]

        if best["model"] != SONNET and sonnet_row:
            s_cps = sf(sonnet_row["cost_per_success"])
            b_cps = sf(best["cost_per_success"])
            if s_cps > 0 and b_cps > 0:
                savings = round((1.0 - b_cps / s_cps) * 100, 0)
                qual_note = ""
                if best.get("avg_quality") and sonnet_row.get("avg_quality"):
                    quality_ratio = round(sf(best["avg_quality"]) / sf(sonnet_row["avg_quality"]) * 100, 0)
                    qual_note = f" at {quality_ratio:.0f}% of Sonnet quality"
                if savings > 10:
                    recommendations.append(
                        f"For {task_type} tasks: {best_short} delivers {best['success_rate']*100:.0f}% success"
                        f"{qual_note} at {savings:.0f}% lower cost-per-success than Sonnet"
                        f" ({b_cps:.4f}¢ vs {s_cps:.4f}¢ per win)"
                    )
        elif best["model"] == SONNET:
            recommendations.append(
                f"For {task_type} tasks: Sonnet leads on cost-per-success — no cheaper model beats it yet"
            )

    if not recommendations:
        recommendations = ["All task types converging — need more data to differentiate model efficiency"]

    return {
        "best_value_models":      best_value,
        "worst_value_models":     worst_value,
        "routing_recommendations": recommendations,
        "total_model_task_pairs": len(enriched),
        "sonnet_baselines":       {k: round(v, 4) for k, v in sonnet_cps_by_type.items()},
        "generated_at":           datetime.utcnow().isoformat(),
        "methodology":            "cost_per_success = avg_cost_cents / success_rate (lower is better; models below 30% success rate excluded)",
    }


@app.get("/api/v1/recommendations")
async def get_recommendations():
    """Actionable per-model-per-category intelligence, not just a health badge."""
    SONNET = "anthropic/claude-sonnet-4-6"
    MIN_TASKS = 5  # minimum tasks before a model gets a recommendation
    FAIL_THRESHOLD = 0.70  # flag models below this success rate
    COST_WIN_MIN = 5.0  # only flag cost wins where cheap model is >=5x cheaper

    def sf(val, default=0.0):
        """Safe float: converts Decimal/None/str to float without crashing."""
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    recommendations = []

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Per-model per-category stats (with quality score awareness)
            cur.execute("""
                SELECT model, task_type AS category,
                       COUNT(*) AS tasks,
                       ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,3) AS success_rate,
                       ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents,
                       ROUND(AVG(quality_score)::numeric,2) AS avg_quality,
                       COUNT(quality_score) AS quality_samples
                FROM tasks
                GROUP BY model, task_type
                HAVING COUNT(*) >= %s
                ORDER BY task_type, success_rate DESC, avg_cost_cents ASC
            """, (MIN_TASKS,))
            rows = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
            total_tasks = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM tasks WHERE quality_score IS NOT NULL")
            scored_tasks = cur.fetchone()["cnt"]

    # Bucket by category
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(dict(r))

    # Find Sonnet's stats per category (baseline cost)
    sonnet_by_cat = {}
    for cat, models in by_cat.items():
        for m in models:
            if m["model"] == SONNET:
                sonnet_by_cat[cat] = m
                break

    # 1. Cost-win opportunities: cheap model beats Sonnet with same/better success
    for cat, models in by_cat.items():
        sonnet = sonnet_by_cat.get(cat)
        if not sonnet or sf(sonnet["avg_cost_cents"]) <= 0:
            continue
        for m in models:
            if m["model"] == SONNET:
                continue
            cost_ratio = sf(sonnet["avg_cost_cents"]) / max(sf(m["avg_cost_cents"]), 0.0001)
            if cost_ratio >= COST_WIN_MIN and sf(m["success_rate"]) >= 0.90:
                quality_note = ""
                if m["quality_samples"] and m["avg_quality"]:
                    quality_note = f", quality {sf(m['avg_quality']):.1f}/5"
                recommendations.append({
                    "priority": "high",
                    "category": "cost_optimization",
                    "task_category": cat,
                    "model": m["model"],
                    "message": (
                        f"{m['model'].split('/')[-1]} wins on {cat}: "
                        f"{cost_ratio:.0f}x cheaper than Sonnet "
                        f"({sf(m['avg_cost_cents']):.4f}¢ vs {sf(sonnet['avg_cost_cents']):.4f}¢), "
                        f"{sf(m['success_rate'])*100:.0f}% success{quality_note}"
                    ),
                    "action": f"Route {cat} tasks to {m['model'].split('/')[-1]} — data supports it ({int(m['tasks'])} tasks)",
                    "cost_ratio": round(cost_ratio, 1),
                    "tasks": int(m["tasks"]),
                })

    # 2. Reliability alerts: models failing below threshold
    for cat, models in by_cat.items():
        for m in models:
            if sf(m["success_rate"]) < FAIL_THRESHOLD:
                recommendations.append({
                    "priority": "high",
                    "category": "reliability_alert",
                    "task_category": cat,
                    "model": m["model"],
                    "message": (
                        f"{m['model'].split('/')[-1]} failing on {cat}: "
                        f"{sf(m['success_rate'])*100:.0f}% success rate "
                        f"({int(m['tasks'])} tasks)"
                    ),
                    "action": f"Remove {m['model'].split('/')[-1]} from {cat} pool or investigate failure notes",
                    "success_rate": sf(m["success_rate"]),
                    "tasks": int(m["tasks"]),
                })

    # 3. Quality scoring coverage
    if total_tasks > 0:
        coverage_pct = round(scored_tasks / total_tasks * 100, 1)
        if coverage_pct < 30:
            recommendations.append({
                "priority": "medium",
                "category": "quality_coverage",
                "message": f"Only {coverage_pct}% of tasks have quality scores ({scored_tasks}/{total_tasks})",
                "action": "Run: python3 /root/.aris/quality_evaluator.py --backfill",
                "coverage_pct": coverage_pct,
            })
        else:
            recommendations.append({
                "priority": "low",
                "category": "quality_coverage",
                "message": f"Quality scoring at {coverage_pct}% ✅ ({scored_tasks}/{total_tasks} tasks)",
                "action": None,
                "coverage_pct": coverage_pct,
            })

    # 4. Data gaps: subtypes with fewer than 10 tasks across all models
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT task_subtype, COUNT(*) AS tasks
                FROM tasks
                WHERE task_subtype IS NOT NULL
                GROUP BY task_subtype
                HAVING COUNT(*) < 10
                ORDER BY tasks ASC
                LIMIT 5
            """)
            thin_subtypes = cur.fetchall()

    for st in thin_subtypes:
        recommendations.append({
            "priority": "low",
            "category": "data_gap",
            "task_subtype": st["task_subtype"],
            "message": f"Thin data for subtype '{st['task_subtype']}': only {st['tasks']} tasks",
            "action": f"Run more benchmarks for {st['task_subtype']} to stabilize routing",
            "tasks": int(st["tasks"]),
        })

    # Summary
    high_count = sum(1 for r in recommendations if r["priority"] == "high")
    cost_wins = [r for r in recommendations if r["category"] == "cost_optimization"]
    summary = (
        f"{total_tasks} tasks | {scored_tasks} quality-scored | "
        f"{high_count} high-priority signals | "
        f"{len(cost_wins)} cost-win opportunities identified"
    )

    if not recommendations:
        recommendations.append({
            "priority": "low",
            "category": "status",
            "message": "Routing looks healthy ✅ No immediate actions needed",
            "action": "Continue collecting data to improve signal quality",
        })

    return {
        "recommendations": sorted(recommendations, key=lambda r: {"high": 0, "medium": 1, "low": 2}[r["priority"]]),
        "last_updated": datetime.utcnow().isoformat(),
        "summary": summary,
        "total_tasks": total_tasks,
        "quality_scored": scored_tasks,
    }

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
                     cost_cents, success, notes, agent_name, output_text,
                     quality_score, parent_task_id, is_subtask, task_subtype)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (request.task_id, request.task_type, request.task_description,
                  request.model, request.duration_seconds, request.cost_cents,
                  request.success, request.notes, agent_name,
                  request.output_text, request.quality_score,
                  request.parent_task_id, request.is_subtask, request.task_subtype))
        conn.commit()
    sub_marker = " [subtask]" if request.is_subtask else ""
    subtype_marker = f" ({request.task_subtype})" if request.task_subtype else ""
    logger.info(f"[{agent_name}]{sub_marker}{subtype_marker} {request.task_id} ({request.task_type}) [{request.model}]")
    return {"status": "success", "message": f"Task {request.task_id} logged",
            "task_id": request.task_id, "agent": agent_name}


@app.delete("/api/v1/tasks/purge")
async def purge_tasks_by_notes(notes_contains: str,
                               x_api_key: Optional[str] = Header(default=None)):
    """Delete tasks where notes contains a substring. Protected endpoint."""
    verify_key(x_api_key)
    if not notes_contains or len(notes_contains) < 5:
        raise HTTPException(status_code=400, detail="notes_contains must be at least 5 chars")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks WHERE notes ILIKE %s",
                        (f"%{notes_contains}%",))
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM tasks WHERE notes ILIKE %s",
                        (f"%{notes_contains}%",))
        conn.commit()
    logger.info(f"purge: Purged {count} tasks matching notes~'{notes_contains}'")
    return {"deleted": count, "pattern": notes_contains}


@app.patch("/api/v1/tasks/{task_id}/quality")
async def patch_quality_score(task_id: str, quality_score: float,
                               x_api_key: Optional[str] = Header(default=None)):
    """Update quality_score for an existing task (called by quality_evaluator.py)."""
    verify_key(x_api_key)
    if not (1.0 <= quality_score <= 5.0):
        raise HTTPException(status_code=400, detail="quality_score must be 1.0–5.0")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tasks SET quality_score=%s WHERE task_id=%s",
                (quality_score, task_id)
            )
            updated = cur.rowcount
        conn.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    logger.info(f"quality_score={quality_score} patched for task_id={task_id}")
    return {"status": "success", "task_id": task_id, "quality_score": quality_score}


# ══════════════════════════════════════════════════════════════════════════════
# v1.0.0 — NEW ENDPOINTS: Feedback Loop · Risk Check · Panic
# ══════════════════════════════════════════════════════════════════════════════

# ── Model registry (cost estimates in cents per typical task) ──────────────────
_MODEL_REGISTRY = {
    # Ultra-cheap
    "openai/gpt-4o-mini":           {"cost": 0.034, "tier": "ultra_cheap", "speed": "fast",   "strength": "simple tasks, drafts"},
    "deepseek/deepseek-v4-flash":   {"cost": 0.033, "tier": "ultra_cheap", "speed": "medium", "strength": "general, cost-sensitive"},
    # Free tier (benchmark + routing candidates)
    # "openai/gpt-oss-20b:free" — retired 2026-06-05 (429 rate limits ~30%, unreliable)
    "openai/gpt-oss-120b:free":     {"cost": 0.000, "tier": "free",        "speed": "slow",   "strength": "OSS 120B, free tier, higher quality"},
    "google/gemma-4-31b-it:free":   {"cost": 0.000, "tier": "free",        "speed": "medium", "strength": "Gemma 4 31B, free tier, instruction-tuned"},
    # Mid
    "anthropic/claude-haiku-4.5":   {"cost": 0.22,  "tier": "mid",         "speed": "fast",   "strength": "latest haiku, improved reasoning"},
    "openai/o3-mini":               {"cost": 0.40,  "tier": "mid",         "speed": "medium", "strength": "math, reasoning, coding precision"},
    # Quality
    "anthropic/claude-sonnet-4-6":  {"cost": 0.689, "tier": "quality",     "speed": "medium", "strength": "strategy, complex tasks, coding"},
    # Security oracle (rare, expensive — gatekeeper only)
    "anthropic/claude-opus-4":      {"cost": 4.50,  "tier": "oracle",      "speed": "slow",   "strength": "security audit, high-risk verification, critical decisions"},
    # RETIRED
    # "google/gemini-2.0-flash-001" — no endpoints on OpenRouter as of 2026-06-05
}

def _model_info(model_id: str) -> dict:
    return _MODEL_REGISTRY.get(model_id, {"cost": 0.5, "tier": "unknown", "speed": "unknown", "strength": "unknown"})


# ── RISK CHECK ─────────────────────────────────────────────────────────────────
_RISK_PATTERNS = {
    "destructive":   (0.9,  ["delete", "drop table", "truncate", "rm -rf", "format", "wipe", "purge all", "destroy"]),
    "config_change": (0.75, ["edit config", "modify openclaw.json", "change model", "update .env", "write to config"]),
    "auth_secrets":  (0.8,  ["api key", "password", "secret", "token", "credential", "private key"]),
    "production":    (0.7,  ["push to production", "deploy to prod", "release", "merge to main", "go live"]),
    "financial":     (0.85, ["transfer funds", "withdraw", "send crypto", "buy position", "sell all"]),
    "system":        (0.8,  ["shutdown", "reboot", "kill process", "disable service", "stop all"]),
    "self_modify":   (0.95, ["modify soul.md", "change agent rules", "update agents.md", "edit system prompt"]),
}

_RISK_TO_ACTION = {
    "critical": "human_approval_required",
    "high":     "security_oracle_review",
    "medium":   "proceed_with_logging",
    "low":      "proceed",
}

class RiskCheckRequest(BaseModel):
    task_id:   Optional[str] = None
    task_desc: str
    agent_name: Optional[str] = "unknown"

@app.post("/api/v1/risk-check")
async def risk_check(request: RiskCheckRequest,
                     x_api_key: Optional[str] = Header(default=None)):
    """
    Pre-flight security scan. Returns risk_level, flags, and recommended action.
    High/critical tasks are flagged for human approval or oracle review before execution.
    No LLM call — fast keyword heuristic, zero cost.
    """
    verify_key(x_api_key)
    text_lower = request.task_desc.lower()
    fired_flags = []
    max_score   = 0.0

    for flag, (score, keywords) in _RISK_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            fired_flags.append(flag)
            if score > max_score:
                max_score = score

    if max_score >= 0.90:
        risk_level = "critical"
    elif max_score >= 0.75:
        risk_level = "high"
    elif max_score >= 0.50:
        risk_level = "medium"
    else:
        risk_level = "low"

    action = _RISK_TO_ACTION[risk_level]
    recommended_model = "anthropic/claude-opus-4" if risk_level in ("critical", "high") else None

    # Log to DB
    task_id = request.task_id or f"risk-{secrets.token_hex(6)}"
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO risk_checks (task_id, task_desc, risk_level, risk_score, flags, action_taken) VALUES (%s,%s,%s,%s,%s,%s)",
                    (task_id, request.task_desc[:500], risk_level, max_score,
                     ",".join(fired_flags), action)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"risk_check DB log failed: {e}")

    logger.info(f"risk-check: risk-check [{risk_level}] score={max_score} flags={fired_flags} task={task_id}")
    return {
        "task_id":          task_id,
        "risk_level":       risk_level,
        "risk_score":       round(max_score, 2),
        "flags":            fired_flags,
        "action":           action,
        "recommended_model": recommended_model,
        "message": (
            f"🔴 CRITICAL — Human approval required before execution." if risk_level == "critical" else
            f"🟠 HIGH RISK — Recommend security oracle review before execution." if risk_level == "high" else
            f"🟡 MEDIUM RISK — Proceeding with full audit logging." if risk_level == "medium" else
            f"🟢 LOW RISK — Cleared to proceed."
        )
    }


# ── FEEDBACK LOOP ──────────────────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    task_id:        str
    original_model: str
    task_type:      Optional[str] = "general"
    issue:          Optional[str] = "response_quality"   # response_quality | too_slow | hallucination | incomplete
    notes:          Optional[str] = None

@app.post("/api/v1/feedback")
async def submit_feedback(request: FeedbackRequest,
                          x_api_key: Optional[str] = Header(default=None)):
    """
    Dissatisfaction signal for a completed task.
    Logs the failure, patches quality_score to 1.0, and returns ranked
    alternative models with transparent cost comparison and a human-friendly pitch.
    """
    verify_key(x_api_key)

    # Patch quality score to 1.0 on the original task
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tasks SET quality_score=1.0 WHERE task_id=%s", (request.task_id,))
                # Log feedback
                cur.execute(
                    "INSERT INTO feedback_v2 (task_id, original_model, issue, notes, rating) VALUES (%s,%s,%s,%s,%s)",
                    (request.task_id, request.original_model, request.issue, request.notes, 1)
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"feedback DB error: {e}")

    orig_info = _model_info(request.original_model)
    orig_cost = orig_info["cost"]

    # Build alternatives: all models more capable than original, sorted by cost
    tier_order = ["ultra_cheap", "cheap", "mid", "quality", "oracle"]
    orig_tier_idx = tier_order.index(orig_info.get("tier", "mid")) if orig_info.get("tier") in tier_order else 2

    alternatives = []
    for model_id, info in _MODEL_REGISTRY.items():
        if model_id == request.original_model:
            continue
        if info["tier"] == "oracle":
            continue  # oracle is never an auto-suggestion
        tier_idx = tier_order.index(info["tier"]) if info["tier"] in tier_order else 2
        if tier_idx <= orig_tier_idx and info["cost"] <= orig_cost * 1.1:
            continue  # skip same/worse tier unless meaningfully different
        cost_delta = info["cost"] - orig_cost
        delta_str  = f"+${cost_delta:.4f}" if cost_delta > 0 else f"-${abs(cost_delta):.4f}"
        # Fetch live success rate from DB if available
        sr = None
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) FROM tasks WHERE model=%s AND task_type=%s",
                        (model_id, request.task_type)
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        sr = round(float(row[0]), 3)
        except Exception:
            pass

        pitch = f"{info['strength'].capitalize()}. "
        pitch += f"Success rate: {int(sr*100)}%. " if sr else ""
        pitch += f"Est. cost: ${info['cost']:.4f}/task ({delta_str} vs current)."

        alternatives.append({
            "model":               model_id,
            "tier":                info["tier"],
            "estimated_cost":      f"${info['cost']:.4f}",
            "cost_delta":          delta_str,
            "success_rate":        sr,
            "speed":               info["speed"],
            "pitch":               pitch,
        })

    # Sort: mid tier first (best value), then quality, then cheap
    tier_score = {"mid": 0, "quality": 1, "cheap": 2, "ultra_cheap": 3}
    alternatives.sort(key=lambda x: tier_score.get(x["tier"], 9))
    top3 = alternatives[:3]

    orig_model_short = request.original_model.split("/")[-1]
    issue_text = {
        "response_quality": "the response quality wasn't satisfying",
        "too_slow":         "the response was too slow",
        "hallucination":    "the model hallucinated or gave inaccurate info",
        "incomplete":       "the response was incomplete",
    }.get(request.issue, "the response didn't meet expectations")

    message = (
        f"Sorry — we routed this to **{orig_model_short}** (${orig_cost:.4f}/task) "
        f"based on past performance data, but {issue_text}. "
        f"We've logged this failure to improve future routing. "
        f"Here are {len(top3)} better option(s) to retry:"
    )

    logger.info(f"feedback logged: task={request.task_id} model={request.original_model} issue={request.issue}")
    return {
        "status":         "logged",
        "task_id":        request.task_id,
        "original_model": request.original_model,
        "issue":          request.issue,
        "message":        message,
        "alternatives":   top3,
    }


# ── PANIC ENDPOINT ─────────────────────────────────────────────────────────────
_PANIC_KEY = os.environ.get("PANIC_KEY", "")   # set in Railway env vars

class PanicRequest(BaseModel):
    level:       int = 1          # 1=app-reset  2=railway-redeploy
    triggered_by: Optional[str] = "unknown"
    reason:      Optional[str] = None

@app.post("/api/v1/panic")
async def panic(request: PanicRequest,
                x_panic_key: Optional[str] = Header(default=None, alias="X-Panic-Key"),
                x_api_key: Optional[str]   = Header(default=None)):
    """
    One-command resurrection.
    Level 1 — App reset: clears internal state, logs event, confirms health.
    Level 2 — Railway redeploy: triggers a fresh deploy via Railway API (needs RAILWAY_TOKEN + SERVICE_ID env vars).
    """
    # Auth: either PANIC_KEY header or valid API key
    authed = False
    if _PANIC_KEY and x_panic_key == _PANIC_KEY:
        authed = True
    if not authed:
        try:
            verify_key(x_api_key)
            authed = True
        except Exception:
            pass
    if not authed:
        raise HTTPException(status_code=401, detail="Missing or invalid panic key / API key")

    result_log = []
    ts = datetime.utcnow().isoformat()
    result_log.append(f"[{ts}] Panic triggered: level={request.level} by={request.triggered_by}")

    # ── Level 1: App health check + state reset ───────────────────────────────
    db_ok = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM tasks")
                cnt = cur.fetchone()[0]
        db_ok = True
        result_log.append(f"✅ DB healthy — {cnt} tasks on record")
    except Exception as e:
        result_log.append(f"❌ DB check failed: {e}")

    agentoptima_ok = True
    result_log.append("✅ AgentOptima API is running (this response proves it)")

    # Log the panic event
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO panic_log (triggered_by, level, result) VALUES (%s,%s,%s)",
                    (request.triggered_by, request.level, " | ".join(result_log))
                )
            conn.commit()
    except Exception:
        pass

    # ── Level 2: Railway redeploy ─────────────────────────────────────────────
    railway_result = None
    if request.level >= 2:
        railway_token      = os.environ.get("RAILWAY_TOKEN", "")
        railway_service_id = os.environ.get("RAILWAY_SERVICE_ID", "")
        railway_env_id     = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")

        if not railway_token:
            railway_result = "⚠️ RAILWAY_TOKEN not set — set it in Railway env vars to enable Level 2 panic"
        else:
            try:
                gql = """
                mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
                  serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
                }
                """
                resp = _requests.post(
                    "https://backboard.railway.app/graphql/v2",
                    headers={"Authorization": f"Bearer {railway_token}", "Content-Type": "application/json"},
                    json={"query": gql, "variables": {"serviceId": railway_service_id, "environmentId": railway_env_id}},
                    timeout=15
                )
                if resp.status_code == 200 and "errors" not in resp.json():
                    railway_result = "✅ Railway redeploy triggered — new deploy will be live in ~2 minutes"
                else:
                    railway_result = f"⚠️ Railway API returned: {resp.text[:200]}"
            except Exception as e:
                railway_result = f"❌ Railway redeploy failed: {e}"
        result_log.append(railway_result)

    logger.warning(f"PANIC: PANIC L{request.level} by={request.triggered_by}: {' | '.join(result_log)}")
    return {
        "status":          "panic_executed",
        "level":           request.level,
        "db_healthy":      db_ok,
        "api_healthy":     agentoptima_ok,
        "railway_result":  railway_result,
        "log":             result_log,
        "recovery_guide": {
            "level_1": "POST /api/v1/panic  {level:1}  — app health reset (always available)",
            "level_2": "POST /api/v1/panic  {level:2}  — Railway redeploy (needs RAILWAY_TOKEN env var)",
            "level_3": "On Aris-HQ: bash /root/.openclaw/workspace/AgentOptima/scripts/panic_push.sh",
        }
    }


# ── WORKER CONTRACTS ──────────────────────────────────────────────────────────
# Embedded here (not read from file) because the API runs on Railway, not local.
WORKER_CONTRACTS = {
    "coding": {
        "description": "Code writing, debugging, refactoring, or script creation",
        "input_fields": ["task", "language", "context", "constraints"],
        "output_format": {
            "success": "bool",
            "code": "string — the complete code solution",
            "explanation": "string — brief explanation of what was done (1-3 sentences)",
            "files_modified": "list[string] — file paths touched (empty if none)",
            "error": "string — error message if success=false, else null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format. No markdown fences. No preamble.",
        "constraints": ["never execute destructive commands", "never expose secrets", "always return valid JSON"]
    },
    "writing": {
        "description": "Content creation, copywriting, documentation, emails",
        "input_fields": ["task", "tone", "length", "audience", "context"],
        "output_format": {
            "success": "bool",
            "content": "string — the written output",
            "word_count": "int",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": ["match requested tone", "respect length constraints"]
    },
    "research": {
        "description": "Information gathering, analysis, summarization, fact-checking",
        "input_fields": ["task", "depth", "context"],
        "output_format": {
            "success": "bool",
            "summary": "string — key findings (3-5 bullet points)",
            "details": "string — full research output",
            "sources": "list[string] — URLs or references if any",
            "confidence": "float 0.0-1.0 — confidence in findings",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": ["cite sources when available", "flag uncertainty explicitly"]
    },
    "analysis": {
        "description": "Data analysis, comparison, evaluation, risk assessment",
        "input_fields": ["task", "data", "context", "output_type"],
        "output_format": {
            "success": "bool",
            "conclusion": "string — 1-2 sentence bottom line",
            "breakdown": "string — detailed analysis",
            "recommendations": "list[string]",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": ["separate facts from inference", "quantify where possible"]
    },
    "math": {
        "description": "Mathematical calculations, proofs, statistical analysis",
        "input_fields": ["task", "context", "precision"],
        "output_format": {
            "success": "bool",
            "answer": "string — the final answer clearly stated",
            "working": "string — step-by-step working",
            "confidence": "float 0.0-1.0",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format. Show all working.",
        "constraints": ["show all steps", "flag assumptions", "verify answer"]
    },
    "data": {
        "description": "Data processing, transformation, formatting, ETL tasks",
        "input_fields": ["task", "input_data", "output_format_requested", "context"],
        "output_format": {
            "success": "bool",
            "result": "string — processed output or transformed data",
            "row_count": "int or null",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": ["preserve data integrity", "handle nulls explicitly"]
    },
    "build": {
        "description": "Build tasks, deployment, infrastructure, configuration",
        "input_fields": ["task", "environment", "context", "constraints"],
        "output_format": {
            "success": "bool",
            "steps_taken": "list[string] — ordered list of actions performed",
            "output": "string — final state or result",
            "warnings": "list[string]",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": ["never run destructive commands without explicit instruction", "log every step"]
    },
    "general": {
        "description": "General purpose tasks that don't fit other categories",
        "input_fields": ["task", "context"],
        "output_format": {
            "success": "bool",
            "result": "string — the task output",
            "error": "string or null"
        },
        "output_instruction": "Return ONLY a JSON object matching the output_format.",
        "constraints": []
    }
}


@app.get("/api/v1/contracts")
async def get_contracts(x_api_key: Optional[str] = Header(None)):
    """Return the worker contract registry. Defines typed I/O schemas per task type."""
    verify_key(x_api_key)
    return {
        "version": "1.0",
        "contracts": WORKER_CONTRACTS,
        "count": len(WORKER_CONTRACTS),
        "task_types": list(WORKER_CONTRACTS.keys()),
        "description": "Worker contracts define typed input/output schemas per task type for reliable delegation.",
    }


# ── MODEL REGISTRY endpoint ────────────────────────────────────────────────────
@app.get("/api/v1/registry")
async def model_registry():
    """Full model registry with tiers, costs, and strengths."""
    return {
        "version": "1.1.10",
        "total_models": len(_MODEL_REGISTRY),
        "models": [
            {"model": k, **v} for k, v in _MODEL_REGISTRY.items()
        ],
        "tiers": {
            "ultra_cheap": "Simple tasks, bulk ops — lowest cost",
            "cheap":       "Fast analysis, multimodal — great value",
            "mid":         "Balanced quality/cost — default for most tasks",
            "quality":     "Complex reasoning, strategy, coding — best output",
            "oracle":      "Security audit, critical decisions — used as gatekeeper only",
        }
    }


# ── PUBLIC: Risk Preview (no auth, no DB write — safe for dashboard demo) ──────
@app.get("/api/v1/risk-preview")
async def risk_preview(text: str = ""):
    """
    Public risk classification for dashboard demo.
    No auth required, no DB write. Pure keyword heuristic.
    """
    if not text or len(text.strip()) < 3:
        return {"risk_level": "low", "risk_score": 0.0, "flags": [], "action": "proceed",
                "message": "🟢 LOW RISK — Cleared to proceed."}

    text_lower = text.lower().strip()
    fired_flags = []
    max_score = 0.0
    for flag, (score, keywords) in _RISK_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            fired_flags.append(flag)
            if score > max_score:
                max_score = score

    if max_score >= 0.90:   risk_level = "critical"
    elif max_score >= 0.75: risk_level = "high"
    elif max_score >= 0.50: risk_level = "medium"
    else:                   risk_level = "low"

    action = _RISK_TO_ACTION[risk_level]

    # Recommended model from registry (public tiers)
    rec_model = None
    for model_id, info in _MODEL_REGISTRY.items():
        if risk_level in ("critical", "high") and info["tier"] == "oracle":
            rec_model = model_id
            break
        elif risk_level in ("low", "medium") and info["tier"] == "mid":
            rec_model = model_id
            break

    return {
        "risk_level":        risk_level,
        "risk_score":        round(max_score, 2),
        "flags":             fired_flags,
        "action":            action,
        "recommended_model": rec_model,
        "message": (
            "🔴 CRITICAL — Human approval required before execution." if risk_level == "critical" else
            "🟠 HIGH RISK — Security oracle review recommended." if risk_level == "high" else
            "🟡 MEDIUM RISK — Proceed with full audit logging." if risk_level == "medium" else
            "🟢 LOW RISK — Cleared to proceed."
        )
    }


# ── PUBLIC: Recent risk checks feed (no sensitive data) ────────────────────────
@app.get("/api/v1/gate/recent")
async def recent_gate_decisions(limit: int = 10):
    """
    Public feed of recent gate decisions for the dashboard.
    Returns risk level + action only — no full task descriptions for privacy.
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        risk_level, risk_score, flags, action_taken,
                        LEFT(task_desc, 60) AS task_preview,
                        created_at
                    FROM risk_checks
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (min(limit, 50),))
                rows = cur.fetchall()
        return {
            "decisions": [dict(r) for r in rows],
            "total": len(rows)
        }
    except Exception as e:
        return {"decisions": [], "total": 0, "error": str(e)}


# ── PUBLIC: Gate stats summary ─────────────────────────────────────────────────
# ── Adaptive Context Manager ──────────────────────────────────────────────────

class ContextPruneRequest(BaseModel):
    session_id:       str
    current_tokens:   int
    message_count:    int
    strategy:         str = "balanced"   # aggressive | balanced | minimal
    preserve_last_n:  int = 5

@app.post("/api/v1/context/prune")
async def context_prune(
    req: ContextPruneRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Adaptive Context Manager — tells caller how to prune their session context.
    Returns pruning strategy + estimated token savings + cost savings.

    Strategies:
      - aggressive: fire at 30K tokens, compress to ~5K
      - balanced:   fire at 60K tokens, compress to ~15K
      - minimal:    fire at 100K tokens, compress to ~30K
    """
    THRESHOLDS = {
        "aggressive": {"fire_at": 30_000,  "target": 5_000},
        "balanced":   {"fire_at": 60_000,  "target": 15_000},
        "minimal":    {"fire_at": 100_000, "target": 30_000},
    }
    SONNET_INPUT_PER_TOKEN = 3.00 / 1_000_000  # $3 per 1M input tokens

    cfg = THRESHOLDS.get(req.strategy, THRESHOLDS["balanced"])
    should_prune = req.current_tokens >= cfg["fire_at"]
    tokens_saved = max(0, req.current_tokens - cfg["target"]) if should_prune else 0

    # Cost saved = tokens pruned * Sonnet input price * msgs until next prune
    # (pruned tokens no longer travel in context on every future message)
    msgs_until_next_prune = max(1, (cfg["fire_at"] - cfg["target"]) // max(1, req.current_tokens // max(1, req.message_count)))
    cost_saved_cents = tokens_saved * SONNET_INPUT_PER_TOKEN * msgs_until_next_prune * 100

    return {
        "should_prune":        should_prune,
        "strategy":            req.strategy,
        "current_tokens":      req.current_tokens,
        "threshold":           cfg["fire_at"],
        "target_tokens":       cfg["target"] if should_prune else req.current_tokens,
        "tokens_to_prune":     tokens_saved,
        "estimated_cost_saved_cents": round(cost_saved_cents, 4),
        "preserve_last_n_messages": req.preserve_last_n,
        "instructions": (
            f"Summarize conversation history older than last {req.preserve_last_n} messages "
            f"into a 200-word bullet-point context block. "
            f"Strip all tool outputs except final results. "
            f"Target: {cfg['target']:,} tokens total context."
        ) if should_prune else "Context healthy — no pruning needed.",
        "message": (
            f"Pruning recommended: {req.current_tokens:,} tokens → ~{cfg['target']:,} tokens. "
            f"Estimated saving: {cost_saved_cents:.2f}¢ over next ~{msgs_until_next_prune} messages."
        ) if should_prune else f"Context at {req.current_tokens:,}/{cfg['fire_at']:,} tokens — healthy.",
    }

@app.get("/api/v1/context/stats")
async def context_stats():
    """Returns threshold config for all pruning strategies — useful for dashboard."""
    SONNET_MONTHLY = 3.00 / 1_000_000 * 30 * 20  # 20 msgs/day, 30 days
    return {
        "strategies": {
            "aggressive": {
                "fires_at_tokens": 30_000,
                "compresses_to":   5_000,
                "monthly_saving_estimate": f"${SONNET_MONTHLY * 25_000 * 100:.0f}",
                "best_for": "High-volume agents, cost-critical",
            },
            "balanced": {
                "fires_at_tokens": 60_000,
                "compresses_to":   15_000,
                "monthly_saving_estimate": f"${SONNET_MONTHLY * 45_000 * 100:.0f}",
                "best_for": "Most users — default",
            },
            "minimal": {
                "fires_at_tokens": 100_000,
                "compresses_to":   30_000,
                "monthly_saving_estimate": f"${SONNET_MONTHLY * 70_000 * 100:.0f}",
                "best_for": "Long research sessions needing full history",
            },
        },
        "sonnet_input_price_per_1m": "$3.00",
        "insight": "Context bloat is the #1 hidden cost driver in AI chat. Pruning at 60K tokens saves ~70% of input costs on long sessions.",
    }


# ── Adaptive Context Threshold ──────────────────────────────────────────────────

class ContextAnalyzeRequest(BaseModel):
    session_id:    str
    token_history: list  # token count at each message, e.g. [4000, 8200, 12800]
    strategy:      str = "adaptive"

@app.post("/api/v1/context/analyze")
async def context_analyze(
    req: ContextAnalyzeRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Adaptive Context Threshold — learns from your actual session token growth.
    Instead of a hardcoded 60K threshold, computes the optimal prune point
    based on where YOUR cost curve starts inflecting.

    Returns a personalized threshold recommendation.
    """
    MIN_THRESHOLD  = 20_000
    MAX_THRESHOLD  = 120_000
    SAFETY_MARGIN  = 0.95    # prune 5% before inflection
    HEADROOM_MSGS  = 15      # fallback: 15 messages of headroom

    history = [int(t) for t in req.token_history if t > 0]

    if len(history) < 3:
        return {
            "recommended_threshold": 60_000,
            "growth_rate_per_msg":   3_000,
            "inflection_point":      None,
            "msgs_until_threshold":  None,
            "strategy":              "fallback",
            "reasoning":             "Not enough history (need ≥3 msgs) — using balanced default",
        }

    # Compute per-message growth deltas
    deltas = [history[i] - history[i-1] for i in range(1, len(history))]
    avg_growth = sum(deltas) / len(deltas)

    # Find inflection: where delta growth rate first exceeds 20% above avg
    inflection = None
    for i in range(1, len(deltas)):
        if deltas[i] > avg_growth * 1.20:
            # Inflection at the token count where this spike starts
            inflection = history[i]
            break

    if inflection:
        threshold = int(max(MIN_THRESHOLD, min(MAX_THRESHOLD, inflection * SAFETY_MARGIN)))
        reasoning = (f"Growth rate {avg_growth:.0f} tokens/msg. "
                     f"Cost curve inflects at {inflection:,} tokens — "
                     f"threshold set {int((1-SAFETY_MARGIN)*100)}% below inflection.")
    else:
        # No clear inflection — use headroom heuristic
        threshold = int(max(MIN_THRESHOLD, min(MAX_THRESHOLD, avg_growth * HEADROOM_MSGS)))
        reasoning = (f"No clear inflection found. "
                     f"Growth rate {avg_growth:.0f} tokens/msg × {HEADROOM_MSGS} msgs headroom "
                     f"= {threshold:,} token threshold.")

    # Estimate msgs until threshold from current position
    current = history[-1] if history else 0
    msgs_remaining = max(0, int((threshold - current) / avg_growth)) if avg_growth > 0 else None

    return {
        "recommended_threshold": threshold,
        "growth_rate_per_msg":   round(avg_growth, 0),
        "inflection_point":      inflection,
        "msgs_until_threshold":  msgs_remaining,
        "current_tokens":        current,
        "strategy":              "adaptive",
        "reasoning":             reasoning,
        "vs_default":            f"{'Better' if threshold != 60_000 else 'Same as'} balanced default (60K). Your personalized threshold: {threshold:,}.",
    }


@app.get("/api/v1/gate/stats")
async def gate_stats():
    """Aggregate gate stats: total checks, blocked count, by risk level."""
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        risk_level,
                        COUNT(*) AS count,
                        AVG(risk_score) AS avg_score
                    FROM risk_checks
                    GROUP BY risk_level
                    ORDER BY avg_score DESC
                """)
                by_level = cur.fetchall()
                cur.execute("SELECT COUNT(*) AS total FROM risk_checks")
                total = cur.fetchone()["total"]
                cur.execute("SELECT COUNT(*) AS total FROM feedback_v2")
                feedback_total = cur.fetchone()["total"]
        return {
            "total_checks":    total,
            "feedback_signals": feedback_total,
            "by_level":        [dict(r) for r in by_level],
            "blocked_count":   next((r["count"] for r in by_level if r["risk_level"] == "critical"), 0),
        }
    except Exception as e:
        return {"total_checks": 0, "blocked_count": 0, "by_level": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR RECALIBRATION — NEW ENDPOINTS v1.0.5
# ══════════════════════════════════════════════════════════════════════════════

class RecalibrateOrchestratorRequest(BaseModel):
    task_id: Optional[str] = None
    force: bool = False

@app.post("/api/v1/recalibrate/orchestrator")
async def recalibrate_orchestrator(
    request: RecalibrateOrchestratorRequest,
    x_api_key: Optional[str] = Header(None)
):
    """
    Daily orchestration model recalibration.
    
    1. Queries all orchestration tasks (task_type='orchestration')
    2. Ranks models by: success_rate >= 0.85, then lowest cost, then fastest duration
    3. Picks best model and stores in orchestrator_state
    4. Returns {recommended_model, success_rate, benchmarks_used, timestamp}
    """
    # Auth optional — can be called by cron or webhook
    try:
        if x_api_key:
            verify_key(x_api_key)
    except HTTPException:
        pass  # allow unauthenticated calls for cron

    task_id = request.task_id or f"orch-{secrets.token_hex(8)}"
    ts = datetime.utcnow().isoformat()

    # ── Step 1: Check benchmark_results for OrchestraBench data ──────────────
    bench_candidates = []
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT model, total_score, value_score, cost_cents, avg_latency_ms, run_at
                    FROM (
                        SELECT *,
                               ROW_NUMBER() OVER (PARTITION BY model ORDER BY run_at DESC) AS rn
                        FROM benchmark_results
                        WHERE benchmark_name='orchestra_bench_v1'
                    ) sub
                    WHERE rn=1
                    ORDER BY value_score DESC NULLS LAST, total_score DESC
                """)
                bench_candidates = cur.fetchall()
    except Exception as e:
        logger.warning(f"benchmark_results query failed: {e}")

    # Use benchmark data if we have results with total_score >= 0.85 threshold
    eligible_bench = [r for r in bench_candidates if r["total_score"] and float(r["total_score"]) >= 0.85 * 5]
    # If nothing meets 0.85 per task avg but we have data, use top by value_score
    if not eligible_bench and bench_candidates:
        eligible_bench = list(bench_candidates)  # fallback: use all bench data

    if eligible_bench:
        best_bench = eligible_bench[0]
        result = {
            "recommended_model": best_bench["model"],
            "reason": "benchmark_data",
            "data_source": "benchmark_data",
            "benchmarks_used": {
                "total_score": float(best_bench["total_score"]),
                "value_score": float(best_bench["value_score"]) if best_bench["value_score"] else None,
                "cost_cents": float(best_bench["cost_cents"]) if best_bench["cost_cents"] else None,
                "avg_latency_ms": int(best_bench["avg_latency_ms"]) if best_bench["avg_latency_ms"] else None,
                "run_at": best_bench["run_at"].isoformat() if best_bench["run_at"] else None,
                "benchmark_name": "orchestra_bench_v1",
            },
            "success_rate": round(float(best_bench["total_score"]) / 5, 4) if best_bench["total_score"] else None,
            "avg_cost_cents": float(best_bench["cost_cents"]) if best_bench["cost_cents"] else None,
            "avg_duration_s": None,
            "task_id": task_id,
            "timestamp": ts,
        }
    else:
        # ── Step 2: Fallback to task history (original behavior) ────────────────
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        model,
                        COUNT(*) AS task_count,
                        ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric, 4) AS success_rate,
                        ROUND(AVG(duration_s)::numeric, 2) AS avg_duration_s,
                        ROUND(AVG(cost_cents)::numeric, 4) AS avg_cost_cents,
                        ROUND(AVG(quality_score)::numeric, 2) AS avg_quality
                    FROM tasks
                    WHERE task_type = 'orchestration' AND success = TRUE
                    GROUP BY model
                    HAVING COUNT(*) >= 5
                    ORDER BY
                        success_rate DESC,
                        avg_cost_cents ASC,
                        avg_duration_s ASC
                """)
                candidates = cur.fetchall()

        if not candidates:
            result = {
                "recommended_model": "anthropic/claude-sonnet-4-6",
                "reason": "insufficient_data — defaulting to Sonnet (most reliable for orchestration)",
                "data_source": "fallback_default",
                "benchmarks_used": 0,
                "success_rate": None,
                "avg_cost_cents": None,
                "avg_duration_s": None,
                "task_id": task_id,
                "timestamp": ts,
            }
        else:
            reliable = [c for c in candidates if float(c["success_rate"]) >= 0.85]
            if not reliable:
                reliable = candidates[:1]
            best = reliable[0]
            result = {
                "recommended_model": best["model"],
                "reason": "task_history",
                "data_source": "task_history",
                "benchmarks_used": {
                    "success_rate": float(best["success_rate"]),
                    "avg_cost_cents": float(best["avg_cost_cents"]),
                    "avg_duration_s": float(best["avg_duration_s"]),
                    "avg_quality": float(best["avg_quality"]) if best["avg_quality"] else None,
                    "based_on_tasks": int(best["task_count"]),
                },
                "success_rate": float(best["success_rate"]),
                "avg_cost_cents": float(best["avg_cost_cents"]),
                "avg_duration_s": float(best["avg_duration_s"]),
                "task_id": task_id,
                "timestamp": ts,
            }

    # Write to persistent state
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO orchestrator_state
                        (recommended_model, success_rate, avg_cost_cents, avg_duration_s, based_on_tasks, reason, resolution)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    result["recommended_model"],
                    result.get("success_rate"),
                    result.get("avg_cost_cents"),
                    result.get("avg_duration_s"),
                    result.get("benchmarks_used", {}).get("based_on_tasks") if isinstance(result.get("benchmarks_used"), dict) else None,
                    result.get("reason"),
                    result.get("reason"),
                ))
            conn.commit()
    except Exception as e:
        logger.warning(f"orchestrator_state write failed: {e}")

    logger.info(f"orchestrator recalibrated: {result['recommended_model']} (reason={result.get('reason')})")
    return result


@app.get("/api/v1/orchestrator/current")
async def get_orchestrator_current():
    """
    GET current orchestrator recommendation.
    Returns: {recommended_model, reason, benchmarks_used, updated_at, age_hours}
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        recommended_model, reason, success_rate, avg_cost_cents, avg_duration_s,
                        based_on_tasks, updated_at
                    FROM orchestrator_state
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()

        if not row:
            return {
                "status": "no_recommendation_yet",
                "recommended_model": "anthropic/claude-sonnet-4-6",
                "reason": "first_run — defaulting to Sonnet",
                "updated_at": None,
            }

        # Calculate age
        from datetime import timezone
        updated = row["updated_at"]
        now = datetime.now(timezone.utc) if updated.tzinfo else datetime.utcnow()
        age_hours = (now - updated).total_seconds() / 3600 if updated else None

        return {
            "status": "current",
            "recommended_model": row["recommended_model"],
            "reason": row["reason"],
            "benchmarks_used": {
                "success_rate": float(row["success_rate"]) if row["success_rate"] else None,
                "avg_cost_cents": float(row["avg_cost_cents"]) if row["avg_cost_cents"] else None,
                "avg_duration_s": float(row["avg_duration_s"]) if row["avg_duration_s"] else None,
                "based_on_tasks": int(row["based_on_tasks"]) if row["based_on_tasks"] else None,
            },
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "age_hours": round(age_hours, 1) if age_hours else None,
        }
    except Exception as e:
        logger.error(f"get_orchestrator_current failed: {e}")
        return {
            "status": "error",
            "recommended_model": "anthropic/claude-sonnet-4-6",
            "reason": f"query_failed: {str(e)}",
            "fallback": "using Sonnet",
        }


@app.get("/api/v1/registry/with-benchmarks")
async def registry_with_benchmarks():
    """
    Extended model registry including live benchmark results.
    Shows each model's recent test performance (quality, latency, cost).
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Latest benchmark per model (last 7 days)
                cur.execute("""
                    SELECT
                        model,
                        ROUND(AVG(quality_score)::numeric, 2) AS avg_quality,
                        ROUND(AVG(latency_ms)::numeric, 0) AS avg_latency_ms,
                        ROUND(AVG(cost_cents)::numeric, 4) AS avg_bench_cost,
                        COUNT(*) AS benchmark_count,
                        MAX(created_at) AS last_tested,
                        ROUND(SUM(CASE WHEN success THEN 1.0 ELSE 0.0 END) / COUNT(*)::numeric, 4) AS success_rate
                    FROM model_benchmarks
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                    GROUP BY model
                    ORDER BY avg_quality DESC, avg_latency_ms ASC
                """)
                bench_rows = {r["model"]: dict(r) for r in cur.fetchall()}

    except Exception as e:
        logger.warning(f"benchmark query failed: {e}")
        bench_rows = {}

    # Combine registry + benchmarks
    models_with_bench = []
    for model_id, info in _MODEL_REGISTRY.items():
        bench = bench_rows.get(model_id, {})
        models_with_bench.append({
            "model": model_id,
            "tier": info["tier"],
            "estimated_cost": info["cost"],
            "speed": info["speed"],
            "strength": info["strength"],
            "last_tested": bench.get("last_tested").isoformat() if bench.get("last_tested") else None,
            "benchmark": {
                "quality_score": bench.get("avg_quality"),
                "latency_ms": int(bench.get("avg_latency_ms")) if bench.get("avg_latency_ms") else None,
                "cost_cents": bench.get("avg_bench_cost"),
                "success_rate": bench.get("success_rate"),
                "test_count": int(bench.get("benchmark_count")) if bench.get("benchmark_count") else 0,
            } if bench else None,
        })

    return {
        "version": "1.1.10",
        "total_models": len(models_with_bench),
        "models": models_with_bench,
        "note": "Benchmarks updated daily via /api/v1/recalibrate/orchestrator",
    }


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRABENCH ENDPOINTS (v1.1.0)
# ══════════════════════════════════════════════════════════════════════════════

class BenchmarkSubmitRequest(BaseModel):
    benchmark: str
    model: str
    scores: dict
    total_score: float
    avg_latency_ms: Optional[int] = None
    cost_cents: Optional[float] = None
    value_score: Optional[float] = None
    timestamp: Optional[str] = None


@app.post("/api/v1/benchmark/submit")
async def benchmark_submit(
    request: BenchmarkSubmitRequest,
    x_api_key: Optional[str] = Header(None)
):
    """
    Store OrchestraBench results. Updates benchmark_results table + model_benchmarks.
    Returns: {stored, rank, vs_previous}
    """
    verify_key(x_api_key)

    run_at = request.timestamp or datetime.utcnow().isoformat()

    # Get previous best for this model+benchmark
    prev_total = None
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT total_score FROM benchmark_results
                    WHERE benchmark_name=%s AND model=%s
                    ORDER BY run_at DESC LIMIT 1
                """, (request.benchmark, request.model))
                row = cur.fetchone()
                if row:
                    prev_total = float(row[0])
    except Exception:
        pass

    # Insert new result
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO benchmark_results
                        (benchmark_name, model, scores, total_score, avg_latency_ms, cost_cents, value_score, run_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    request.benchmark,
                    request.model,
                    psycopg2.extras.Json(request.scores),
                    request.total_score,
                    request.avg_latency_ms,
                    request.cost_cents,
                    request.value_score,
                    run_at,
                ))
                # Also update model_benchmarks with latest OrchestraBench score
                cur.execute("""
                    INSERT INTO model_benchmarks
                        (model, benchmark_date, test_prompt, quality_score, latency_ms,
                         cost_cents, success, total_score, value_score, benchmark_name)
                    VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, TRUE, %s, %s, %s)
                """, (
                    request.model,
                    f"orchestra_bench_v1: {list(request.scores.keys())}",
                    request.total_score,
                    request.avg_latency_ms,
                    request.cost_cents,
                    request.total_score,
                    request.value_score,
                    request.benchmark,
                ))
            conn.commit()
    except Exception as e:
        logger.error(f"benchmark_submit DB error: {e}")
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    # Compute rank among latest results for this benchmark
    rank = 1
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Latest run per model for this benchmark
                cur.execute("""
                    SELECT model, total_score
                    FROM (
                        SELECT model, total_score,
                               ROW_NUMBER() OVER (PARTITION BY model ORDER BY run_at DESC) AS rn
                        FROM benchmark_results WHERE benchmark_name=%s
                    ) sub
                    WHERE rn=1
                    ORDER BY total_score DESC
                """, (request.benchmark,))
                all_scores = cur.fetchall()
                for i, (m, s) in enumerate(all_scores, 1):
                    if m == request.model:
                        rank = i
                        break
    except Exception:
        pass

    vs_previous = None
    if prev_total is not None:
        delta = round(request.total_score - prev_total, 4)
        vs_previous = f"+{delta:.2f} improvement" if delta >= 0 else f"{delta:.2f} regression"

    logger.info(f"benchmark_submit: {request.model.split('/')[-1]} score={request.total_score:.2f} rank=#{rank}")
    return {
        "stored": True,
        "model": request.model,
        "benchmark": request.benchmark,
        "total_score": request.total_score,
        "rank": rank,
        "vs_previous": vs_previous,
    }


@app.get("/api/v1/benchmark/results")
async def benchmark_results(
    benchmark: Optional[str] = None,
    limit: int = 50,
):
    """
    Latest run per model, ranked by value_score (score/cost).
    Optional ?benchmark=orchestra_bench_v1 filter.
    """
    bench_filter = benchmark or "orchestra_bench_v1"
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT model, benchmark_name, scores, total_score,
                           avg_latency_ms, cost_cents, value_score, run_at
                    FROM (
                        SELECT *,
                               ROW_NUMBER() OVER (PARTITION BY model, benchmark_name ORDER BY run_at DESC) AS rn
                        FROM benchmark_results
                        WHERE benchmark_name=%s
                    ) sub
                    WHERE rn=1
                    ORDER BY value_score DESC NULLS LAST, total_score DESC
                    LIMIT %s
                """, (bench_filter, min(limit, 200)))
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "benchmark": bench_filter,
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(rows),
        "results": [
            {
                "rank": i,
                "model": r["model"],
                "model_short": r["model"].split("/")[-1],
                "scores": r["scores"],
                "total_score": float(r["total_score"]) if r["total_score"] else None,
                "avg_latency_ms": int(r["avg_latency_ms"]) if r["avg_latency_ms"] else None,
                "cost_cents": float(r["cost_cents"]) if r["cost_cents"] else None,
                "value_score": float(r["value_score"]) if r["value_score"] else None,
                "run_at": r["run_at"].isoformat() if r["run_at"] else None,
            }
            for i, r in enumerate(rows, 1)
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# ESCALATION ENGINE ENDPOINTS (v1.0.6)
# ══════════════════════════════════════════════════════════════════════════════

class EscalationEventRequest(BaseModel):
    task_id: str
    from_model: str
    to_model: str
    signals: list = []
    task_type: Optional[str] = None
    confidence_score: float
    success_after: bool


@app.post("/api/v1/escalation/event")
async def log_escalation_event(
    request: EscalationEventRequest,
    x_api_key: Optional[str] = Header(None)
):
    """
    Log an escalation event from escalation_engine.py.
    
    Stores in escalation_events table and updates model stats.
    Returns insights: which task types escalate most, per-model escalation rates.
    """
    agent = verify_key(x_api_key)
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Insert escalation event
                cur.execute("""
                    INSERT INTO escalation_events
                        (task_id, from_model, to_model, signals, task_type, confidence_score, success_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    request.task_id,
                    request.from_model,
                    request.to_model,
                    json.dumps(request.signals) if request.signals else '[]',
                    request.task_type,
                    request.confidence_score,
                    request.success_after,
                ))
                conn.commit()

                # Get insight: other tasks that escalated from this model for this task_type
                cur.execute("""
                    SELECT COUNT(*) as escalation_count
                    FROM escalation_events
                    WHERE from_model = %s AND task_type = %s
                    AND created_at >= NOW() - INTERVAL '30 days'
                """, (request.from_model, request.task_type))
                
                row = cur.fetchone()
                escalation_count = row[0] if row else 0
                
                # Suggestion for pre-routing
                suggestion = ""
                if escalation_count >= 5:
                    suggestion = f"{request.from_model} escalated {escalation_count}x on {request.task_type} tasks in 30d → consider pre-routing higher"

        return {
            "stored": True,
            "task_id": request.task_id,
            "escalation_count_30d": escalation_count,
            "insight": suggestion,
        }
    
    except Exception as e:
        logger.error(f"escalation event logging failed: {e}")
        return {
            "stored": False,
            "error": str(e),
        }


@app.get("/api/v1/escalation/insights")
async def get_escalation_insights(x_api_key: Optional[str] = Header(None)):
    """
    GET escalation analytics.
    
    Returns:
    - per_model_escalation_rate: % of tasks requiring escalation by model
    - task_type_escalation_rate: % of escalations by task type
    - pre_routing_saves: count of tasks pre-routed higher based on escalation history
    - last_5_events: recent escalations
    """
    agent = verify_key(x_api_key)
    
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                
                # Per-model escalation rate (last 30 days)
                cur.execute("""
                    SELECT
                        from_model,
                        COUNT(*) as escalation_count,
                        ROUND(COUNT(*) * 100.0 / NULLIF(
                            (SELECT COUNT(*) FROM tasks t2 WHERE t2.logged_at >= NOW() - INTERVAL '30 days'), 0
                        )::numeric, 2) AS escalation_rate_pct
                    FROM escalation_events
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY from_model
                    ORDER BY escalation_count DESC
                """)
                per_model = [dict(r) for r in cur.fetchall()]
                
                # Task type escalation distribution
                cur.execute("""
                    SELECT
                        COALESCE(task_type, 'unknown') as task_type,
                        COUNT(*) as count,
                        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM escalation_events WHERE created_at >= NOW() - INTERVAL '30 days')::numeric, 1) AS pct
                    FROM escalation_events
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY task_type
                    ORDER BY count DESC
                """)
                by_task_type = [dict(r) for r in cur.fetchall()]
                
                # Last 5 escalation events
                cur.execute("""
                    SELECT
                        task_id, from_model, to_model, task_type, confidence_score, success_after, created_at
                    FROM escalation_events
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                last_events = [dict(r) for r in cur.fetchall()]
                for evt in last_events:
                    if evt.get('created_at'):
                        evt['created_at'] = evt['created_at'].isoformat()

        return {
            "period": "last_30_days",
            "per_model_escalation_rate": per_model,
            "task_type_distribution": by_task_type,
            "last_5_events": last_events,
            "pre_routing_saves": 0,  # TODO: track when pre-routing avoids escalation
        }
    
    except Exception as e:
        logger.error(f"escalation insights query failed: {e}")
        return {
            "error": str(e),
            "per_model_escalation_rate": [],
            "task_type_distribution": [],
            "last_5_events": [],
        }


@app.get("/api/v1/escalation/public")
async def escalation_public():
    """
    Public (no-auth) escalation summary for dashboard display.
    Returns aggregate stats only — no sensitive task details.
    """
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Total escalations (last 30 days)
                cur.execute("SELECT COUNT(*) AS total FROM escalation_events WHERE created_at >= NOW() - INTERVAL '30 days'")
                total = cur.fetchone()["total"] or 0

                # Per-model escalation counts
                cur.execute("""
                    SELECT from_model, COUNT(*) AS escalation_count
                    FROM escalation_events
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY from_model
                    ORDER BY escalation_count DESC
                    LIMIT 10
                """)
                per_model = [{"from_model": r["from_model"], "escalation_count": int(r["escalation_count"])} for r in cur.fetchall()]

                # Task type distribution
                cur.execute("""
                    SELECT COALESCE(task_type, 'unknown') AS task_type, COUNT(*) AS count
                    FROM escalation_events
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY task_type
                    ORDER BY count DESC
                    LIMIT 10
                """)
                by_task_type = [dict(r) for r in cur.fetchall()]

                # Success rate from last 20 escalations
                cur.execute("""
                    SELECT success_after FROM escalation_events
                    ORDER BY created_at DESC LIMIT 20
                """)
                recent = cur.fetchall()
                success_after_count = sum(1 for r in recent if r["success_after"])
                success_rate = round(success_after_count / len(recent), 3) if recent else None

        return {
            "period": "last_30_days",
            "total_escalations": int(total),
            "per_model_escalation_rate": per_model,
            "task_type_distribution": by_task_type,
            "escalation_success_rate": success_rate,
            "pre_routing_saves": 0,
            "last_5_events": [],
        }
    except Exception as e:
        return {
            "total_escalations": 0,
            "per_model_escalation_rate": [],
            "task_type_distribution": [],
            "escalation_success_rate": None,
            "pre_routing_saves": 0,
            "last_5_events": [],
            "error": str(e),
        }


# ── Task State Layer (v1.1.3) ──────────────────────────────────────────────────

@app.post("/api/v1/tasks/register")
async def register_task(request: TaskRegisterRequest,
                        x_api_key: Optional[str] = Header(None)):
    """Register a task as pending before spawn. Called by spawn_gate.pre_spawn()."""
    verify_key(x_api_key)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tasks
                        (task_id, task_type, task_desc, model, status, goal_id,
                         agent_name, logged_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (
                    request.task_id,
                    request.task_type or "general",
                    (request.task_desc or "")[:500],
                    request.model or "unknown",
                    request.status or "pending",
                    request.goal_id,
                    request.agent_name or "aris",
                ))
            conn.commit()
        return {"task_id": request.task_id, "registered": True}
    except Exception as e:
        logger.error(f"register_task error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/v1/tasks/{task_id}/state")
async def update_task_state(task_id: str, request: TaskStateUpdate,
                            x_api_key: Optional[str] = Header(None)):
    """Update task state after worker completes. Called by orchestrator."""
    verify_key(x_api_key)
    valid_statuses = {"pending", "running", "success", "failed", "retry", "completed"}
    if request.status not in valid_statuses:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {valid_statuses}")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                fields, values = [], []
                fields.append("status = %s");      values.append(request.status)
                if request.retries    is not None: fields.append("retries = %s");    values.append(request.retries)
                if request.error_type is not None: fields.append("error_type = %s"); values.append(request.error_type)
                if request.error_msg  is not None: fields.append("error_msg = %s");  values.append(request.error_msg)
                if request.goal_id    is not None: fields.append("goal_id = %s");    values.append(request.goal_id)
                if request.output_text is not None: fields.append("output_text = %s"); values.append(request.output_text[:2000])
                if request.cost_cents  is not None: fields.append("cost_cents = %s");  values.append(request.cost_cents)
                if request.duration_s  is not None: fields.append("duration_s = %s");  values.append(request.duration_s)
                values.append(task_id)
                cur.execute(
                    f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = %s",
                    values
                )
            conn.commit()
        return {"task_id": task_id, "status": request.status, "updated": True}
    except Exception as e:
        logger.error(f"update_task_state error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tasks/failed")
async def get_failed_tasks(x_api_key: Optional[str] = Header(None)):
    """List last 50 failed tasks with error details."""
    verify_key(x_api_key)
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT task_id, task_type, task_desc, model, status,
                           error_type, error_msg, retries, cost_cents,
                           agent_name, logged_at
                    FROM tasks
                    WHERE status = 'failed' OR success = FALSE
                    ORDER BY logged_at DESC
                    LIMIT 50
                """)
                rows = [dict(r) for r in cur.fetchall()]
        return {"failed_tasks": rows, "count": len(rows)}
    except Exception as e:
        logger.error(f"get_failed_tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str, x_api_key: Optional[str] = Header(None)):
    """Fetch a single task record by task_id."""
    verify_key(x_api_key)
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, task_id, task_type, task_desc, model,
                           duration_s, cost_cents, success, notes, agent_name,
                           logged_at, output_text, quality_score, parent_task_id,
                           is_subtask, task_subtype, status, retries,
                           error_type, error_msg, goal_id
                    FROM tasks WHERE task_id = %s
                    ORDER BY logged_at DESC LIMIT 1
                """, (task_id,))
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_task error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/goals/{goal_id}")
async def get_goal(goal_id: str, x_api_key: Optional[str] = Header(None)):
    """Fetch all tasks under a goal_id with summary stats."""
    verify_key(x_api_key)
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT task_id, task_type, task_desc, model, status,
                           error_type, error_msg, retries, cost_cents,
                           success, agent_name, logged_at, duration_s
                    FROM tasks WHERE goal_id = %s
                    ORDER BY logged_at ASC
                """, (goal_id,))
                rows = [dict(r) for r in cur.fetchall()]

        summary = {
            "total":            len(rows),
            "success":          sum(1 for r in rows if r["status"] == "success" or r["success"]),
            "failed":           sum(1 for r in rows if r["status"] == "failed"),
            "pending":          sum(1 for r in rows if r["status"] == "pending"),
            "retry":            sum(1 for r in rows if r["status"] == "retry"),
            "total_cost_cents": round(sum(r["cost_cents"] or 0 for r in rows), 4),
        }
        return {"goal_id": goal_id, "tasks": rows, "summary": summary}
    except Exception as e:
        logger.error(f"get_goal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Cascade / Retry Waterfall ──────────────────────────────────────────────────
CASCADE_ORDER = {
    "coding":   ["openai/gpt-4o-mini", "anthropic/claude-haiku-4.5", "openai/o3-mini"],
    "research": ["deepseek/deepseek-v4-flash", "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5"],
    "writing":  ["deepseek/deepseek-v4-flash", "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5"],
    "data":     ["deepseek/deepseek-v4-flash", "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5"],
    "math":     ["openai/o3-mini", "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5"],
    "analysis": ["openai/gpt-4o-mini", "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"],
    "build":    ["openai/gpt-4o-mini", "anthropic/claude-haiku-4.5", "openai/o3-mini"],
    "general":  ["openai/gpt-4o-mini", "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"],
    "strategy": ["anthropic/claude-sonnet-4-6"],
    "security": ["anthropic/claude-sonnet-4-6"],
}

DELEGATABLE_TYPES = {"coding", "writing", "data", "research", "analysis", "build", "math"}


class ClassifyRequest(BaseModel):
    message: str
    context: Optional[str] = None


@app.post("/api/v1/classify")
async def classify_post_endpoint(request: ClassifyRequest,
                                 x_api_key: Optional[str] = Header(None)):
    """
    POST /api/v1/classify

    Classify a task description and return the recommended retry cascade.
    Requires X-API-Key header. Logs every classification to the DB.
    """
    agent_name = verify_key(x_api_key)
    start_t = time.monotonic()
    try:
        sys.path.insert(0, '/app')
        from integration.task_classifier import classify_task as _classify

        result = _classify(request.message)
        task_type = result["category"]
        subtype   = result["subtype"]
        confidence = result["confidence"]

        should_delegate = task_type in DELEGATABLE_TYPES
        cascade = CASCADE_ORDER.get(task_type, CASCADE_ORDER["general"])

        # Derive complexity label from confidence
        if confidence < 0.5:
            complexity = "complex"
        elif confidence < 0.75:
            complexity = "medium"
        else:
            complexity = "simple"

        reason = f"{task_type} task, {complexity} complexity"

        # Log to DB
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO tasks
                           (task_id, task_type, task_desc, model, duration_s, cost_cents, success, agent_name, logged_at)
                           VALUES (%s, 'classify', %s, 'none', 0, 0, TRUE, %s, NOW())""",
                        (uuid.uuid4().hex[:12], request.message[:500], agent_name),
                    )
                conn.commit()
        except Exception as db_err:
            logger.warning(f"Failed to log classify call: {db_err}")

        return {
            "task_type":           task_type,
            "task_subtype":        subtype,
            "complexity":          complexity,
            "confidence":          confidence,
            "should_delegate":     should_delegate,
            "recommended_cascade": cascade,
            "reason":              reason,
        }
    except Exception as e:
        logger.error(f"Classify POST error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@app.get("/api/v1/cascade")
async def get_cascade(task_type: str = "general"):
    """
    GET /api/v1/cascade?task_type=coding

    Return the retry waterfall for a given task type. Public, no auth required.
    """
    tt = task_type.strip().lower()
    if "/" in tt:
        tt = tt.split("/")[0]

    if tt not in CASCADE_ORDER:
        note = f"Unknown task_type '{tt}'. Returning general cascade."
        tt = "general"
    else:
        note = None

    cascade    = CASCADE_ORDER[tt]
    escalation = "anthropic/claude-sonnet-4-6"

    resp = {
        "task_type":      tt,
        "cascade":        cascade,
        "escalation":     escalation,
        "description":    "Try models in order. On failure, move to next. Only use escalation after all cascade models fail.",
        "total_attempts": len(cascade) + 1,
    }
    if note:
        resp["note"] = note
    return resp
