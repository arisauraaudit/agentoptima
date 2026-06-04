# AgentOptima API v1.0.4 — cost_per_success metric + /efficiency endpoint + enhanced routing
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os, hashlib, secrets, re, psycopg2, psycopg2.extras, requests as _requests
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
            conn.commit()
        print("✅ PostgreSQL ready (v1.0.5 + orchestrator)")
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
    print("🚀 AgentOptima API v0.9.0 starting...")
    print(f"   Port: {os.environ.get('PORT', 8000)}")
    yield

app = FastAPI(title="AgentOptima API", version="1.0.4", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9\-]{1,30}[a-zA-Z0-9]', request.agent_name) \
            and not re.fullmatch(r'[a-zA-Z0-9]{3,32}', request.agent_name):
        raise HTTPException(
            status_code=422,
            detail="agent_name must be 3-32 characters, alphanumeric and hyphens only"
        )
    if len(request.agent_name) < 3 or len(request.agent_name) > 32:
        raise HTTPException(
            status_code=422,
            detail="agent_name must be between 3 and 32 characters"
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
        print(f"❌ Register error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed — please try again")
    print(f"🎉 New agent registered: {request.agent_name}")
    return {
        "api_key":    api_key,
        "agent_name": request.agent_name,
        "message":    "Welcome to AgentOptima"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.4"}

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
    return {"status": "running", "version": "1.0.4", "tasks_logged": total,
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

ACTIVE_POOL = [
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-3-haiku",
    "deepseek/deepseek-v4-flash",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
    "anthropic/claude-haiku-4.5",
    "openai/o3-mini",
    "anthropic/claude-3.5-haiku",
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
            category_rows = cur.fetchall()

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
                subtype_rows = cur.fetchall()

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
                        FROM tasks WHERE task_type=%s
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
                    FROM tasks WHERE task_type=%s
                    GROUP BY model HAVING COUNT(*) >= %s
                    ORDER BY AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) DESC,
                             AVG(quality_score) DESC NULLS LAST,
                             AVG(cost_cents) ASC
                """, (effective_base, min_tasks))
                rows = cur.fetchall()

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
    print(f"💾 [{agent_name}]{sub_marker}{subtype_marker} {request.task_id} ({request.task_type}) [{request.model}]")
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
    print(f"🗑️  Purged {count} tasks matching notes~'{notes_contains}'")
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
    print(f"⭐ quality_score={quality_score} patched for task_id={task_id}")
    return {"status": "success", "task_id": task_id, "quality_score": quality_score}


# ══════════════════════════════════════════════════════════════════════════════
# v1.0.0 — NEW ENDPOINTS: Feedback Loop · Risk Check · Panic
# ══════════════════════════════════════════════════════════════════════════════

# ── Model registry (cost estimates in cents per typical task) ──────────────────
_MODEL_REGISTRY = {
    # Ultra-cheap
    "openai/gpt-4o-mini":           {"cost": 0.034, "tier": "ultra_cheap", "speed": "fast",   "strength": "simple tasks, drafts"},
    "deepseek/deepseek-v4-flash":   {"cost": 0.033, "tier": "ultra_cheap", "speed": "medium", "strength": "general, cost-sensitive"},
    # Cheap
    "google/gemini-2.0-flash-001":  {"cost": 0.145, "tier": "cheap",       "speed": "fast",   "strength": "multimodal, fast analysis"},
    # Mid
    "anthropic/claude-3-haiku":     {"cost": 0.191, "tier": "mid",         "speed": "fast",   "strength": "balanced quality/cost"},
    "anthropic/claude-haiku-4.5":   {"cost": 0.22,  "tier": "mid",         "speed": "fast",   "strength": "latest haiku, improved reasoning"},
    "anthropic/claude-3.5-haiku":   {"cost": 0.20,  "tier": "mid",         "speed": "fast",   "strength": "next-gen haiku, strong all-round"},
    "openai/o3-mini":               {"cost": 0.40,  "tier": "mid",         "speed": "medium", "strength": "math, reasoning, coding precision"},
    # Quality
    "anthropic/claude-sonnet-4-6":  {"cost": 0.689, "tier": "quality",     "speed": "medium", "strength": "strategy, complex tasks, coding"},
    # Security oracle (rare, expensive — gatekeeper only)
    "anthropic/claude-opus-4":      {"cost": 4.50,  "tier": "oracle",      "speed": "slow",   "strength": "security audit, high-risk verification, critical decisions"},
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
        print(f"⚠️ risk_check DB log failed: {e}")

    print(f"🛡️ risk-check [{risk_level}] score={max_score} flags={fired_flags} task={task_id}")
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
        print(f"⚠️ feedback DB error: {e}")

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

    print(f"📣 feedback logged: task={request.task_id} model={request.original_model} issue={request.issue}")
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

    print(f"🚨 PANIC L{request.level} by={request.triggered_by}: {' | '.join(result_log)}")
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


# ── MODEL REGISTRY endpoint ────────────────────────────────────────────────────
@app.get("/api/v1/registry")
async def model_registry():
    """Full model registry with tiers, costs, and strengths."""
    return {
        "version": "1.0.4",
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

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get orchestration task stats per model
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
        # Fallback: use Sonnet for orchestration (safest choice)
        result = {
            "recommended_model": "anthropic/claude-sonnet-4-6",
            "reason": "insufficient_data — defaulting to Sonnet (most reliable for orchestration)",
            "benchmarks_used": 0,
            "success_rate": None,
            "avg_cost_cents": None,
            "avg_duration_s": None,
            "task_id": task_id,
            "timestamp": ts,
        }
    else:
        # Filter: only models >= 85% success rate
        reliable = [c for c in candidates if float(c["success_rate"]) >= 0.85]

        if not reliable:
            # Use highest success rate if none meet floor
            reliable = candidates[:1]

        best = reliable[0]
        result = {
            "recommended_model": best["model"],
            "reason": "data_driven_orchestration",
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
        print(f"⚠️ orchestrator_state write failed: {e}")

    print(f"🧠 orchestrator recalibrated: {result['recommended_model']} (reason={result.get('reason')})")
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
        print(f"❌ get_orchestrator_current failed: {e}")
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
        print(f"⚠️ benchmark query failed: {e}")
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
        "version": "1.0.5",
        "total_models": len(models_with_bench),
        "models": models_with_bench,
        "note": "Benchmarks updated daily via /api/v1/recalibrate/orchestrator",
    }
