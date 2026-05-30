# AgentOptima API v0.5.0 — quality scoring + actionable recommendations
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os, hashlib, secrets, re, psycopg2, psycopg2.extras
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
            conn.commit()
        print("✅ PostgreSQL ready (v0.6.0)")
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
    print("🚀 AgentOptima API v0.6.0 starting...")
    print(f"   Port: {os.environ.get('PORT', 8000)}")
    yield

app = FastAPI(title="AgentOptima API", version="0.6.0", lifespan=lifespan)
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
    return {"status": "healthy", "version": "0.6.0"}

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
    return {"status": "running", "version": "0.6.0", "tasks_logged": total,
            "tasks_success": success, "models_tracked": models,
            "last_task_at": latest[0].isoformat() if latest else None,
            "storage": "postgresql (Railway managed)"}

@app.get("/api/v1/models")
async def get_models():
    MODEL_POOL = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                  "deepseek/deepseek-v4-flash", "openai/gpt-4o-mini",
                  "google/gemini-2.0-flash-001"]
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
]

@app.get("/api/v1/rankings")
async def get_rankings(include_subtypes: bool = False):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Category-level rankings
            cur.execute("""
                SELECT model, task_type AS category, NULL AS subtype,
                    COUNT(*) AS tasks_logged,
                    ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)::numeric,4) AS success_rate,
                    ROUND(AVG(duration_s)::numeric,2) AS avg_duration,
                    ROUND(AVG(cost_cents)::numeric,4) AS avg_cost_cents,
                    ROUND(AVG(quality_score)::numeric,2) AS avg_quality
                FROM tasks
                WHERE model = ANY(%s)
                GROUP BY model, task_type
                ORDER BY success_rate DESC, tasks_logged DESC
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
                        ROUND(AVG(quality_score)::numeric,2) AS avg_quality
                    FROM tasks
                    WHERE model = ANY(%s) AND task_subtype IS NOT NULL
                    GROUP BY model, task_type, task_subtype
                    ORDER BY task_subtype, success_rate DESC, tasks_logged DESC
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
                GROUP BY task_subtype, model
                ORDER BY task_subtype, n DESC
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
        best_row = model_rows[0]  # already sorted by n DESC
        result.append({
            "subtype":          subtype,
            "min_n_across_models": min_n,
            "routing_ready":    min_n >= TARGET,
            "threshold":        TARGET,
            "runs_needed":      max(0, TARGET - min_n),
            "current_leader":   best_row["model"],
            "leader_success":   float(best_row["success_rate"]),
            "leader_cost":      float(best_row["avg_cost_cents"]),
            "leader_quality":   float(best_row["avg_quality"]) if best_row["avg_quality"] else None,
            "per_model":        per_model,
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
    MODEL_POOL  = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                   "deepseek/deepseek-v4-flash", "openai/gpt-4o-mini",
                   "google/gemini-2.0-flash-001"]
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
    """Classify a task description into an AgentOptima subtype."""
    import sys
    sys.path.insert(0, '/app')
    try:
        from integration.task_classifier import classify_task
        result = classify_task(text)
        return {"input": text[:200], **result}
    except Exception as e:
        return {"input": text[:200], "subtype": "general", "category": "general",
                "confidence": 0.3, "method": "fallback", "error": str(e)}


@app.get("/api/v1/recommend")
async def get_recommendation(task_type: str = "general", task_subtype: str = None,
                             min_tasks: int = 10, text: str = None):
    MODEL_POOL = ["anthropic/claude-sonnet-4-6", "anthropic/claude-3-haiku",
                  "deepseek/deepseek-v4-flash", "openai/gpt-4o-mini",
                  "google/gemini-2.0-flash-001"]

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
                        # Label as category fallback so caller knows it's not subtype-specific
                        return {
                            "mode": "data-driven",
                            "resolution": "category_fallback",
                            "task_type": effective_base,
                            "task_subtype": effective_subtype,
                            "note": f"No subtype data yet for '{effective_subtype}' — using category '{effective_base}' signal",
                            "recommended_model": dict(rows[0])["model"],
                            "success_rate": round(float(rows[0]["success_rate"]), 4),
                            "avg_cost_cents": round(float(rows[0]["avg_cost_cents"]), 4),
                            "avg_duration_s": round(float(rows[0]["avg_duration"]), 1),
                            "based_on_tasks": int(rows[0]["tasks"]),
                            "all_candidates": [dict(r) for r in rows],
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

    best = dict(rows[0])
    return {
        "mode": "data-driven",
        "resolution": "subtype" if effective_subtype else "category",
        "task_type": effective_base,
        "task_subtype": effective_subtype,
        "recommended_model": best["model"],
        "success_rate": round(float(best["success_rate"]), 4),
        "avg_cost_cents": round(float(best["avg_cost_cents"]), 4),
        "avg_duration_s": round(float(best["avg_duration"]), 1),
        "avg_quality": round(float(best["avg_quality"]), 2) if best["avg_quality"] else None,
        "based_on_tasks": int(best["tasks"]),
        "all_candidates": [dict(r) for r in rows],
        "classification": classification_meta,
    }

@app.get("/api/v1/recommendations")
async def get_recommendations():
    """Actionable per-model-per-category intelligence, not just a health badge."""
    SONNET = "anthropic/claude-sonnet-4-6"
    MIN_TASKS = 5  # minimum tasks before a model gets a recommendation
    FAIL_THRESHOLD = 0.70  # flag models below this success rate
    COST_WIN_MIN = 5.0  # only flag cost wins where cheap model is >=5x cheaper

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

            cur.execute("SELECT COUNT(*) FROM tasks")
            total_tasks = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM tasks WHERE quality_score IS NOT NULL")
            scored_tasks = cur.fetchone()[0]

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
        if not sonnet or float(sonnet["avg_cost_cents"]) <= 0:
            continue
        for m in models:
            if m["model"] == SONNET:
                continue
            cost_ratio = float(sonnet["avg_cost_cents"]) / max(float(m["avg_cost_cents"]), 0.0001)
            if cost_ratio >= COST_WIN_MIN and float(m["success_rate"]) >= 0.90:
                quality_note = ""
                if m["quality_samples"] and m["avg_quality"]:
                    quality_note = f", quality {float(m['avg_quality']):.1f}/5"
                recommendations.append({
                    "priority": "high",
                    "category": "cost_optimization",
                    "task_category": cat,
                    "model": m["model"],
                    "message": (
                        f"{m['model'].split('/')[-1]} wins on {cat}: "
                        f"{cost_ratio:.0f}x cheaper than Sonnet "
                        f"({float(m['avg_cost_cents']):.4f}¢ vs {float(sonnet['avg_cost_cents']):.4f}¢), "
                        f"{float(m['success_rate'])*100:.0f}% success{quality_note}"
                    ),
                    "action": f"Route {cat} tasks to {m['model'].split('/')[-1]} — data supports it ({int(m['tasks'])} tasks)",
                    "cost_ratio": round(cost_ratio, 1),
                    "tasks": int(m["tasks"]),
                })

    # 2. Reliability alerts: models failing below threshold
    for cat, models in by_cat.items():
        for m in models:
            if float(m["success_rate"]) < FAIL_THRESHOLD:
                recommendations.append({
                    "priority": "high",
                    "category": "reliability_alert",
                    "task_category": cat,
                    "model": m["model"],
                    "message": (
                        f"{m['model'].split('/')[-1]} failing on {cat}: "
                        f"{float(m['success_rate'])*100:.0f}% success rate "
                        f"({int(m['tasks'])} tasks)"
                    ),
                    "action": f"Remove {m['model'].split('/')[-1]} from {cat} pool or investigate failure notes",
                    "success_rate": float(m["success_rate"]),
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
