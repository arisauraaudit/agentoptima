#!/usr/bin/env python3
"""
AgentOptima Proxy Gateway — Phase 1
====================================
OpenAI-compatible endpoint: POST /v1/chat/completions
Drop-in replacement: change base_url to https://agentoptima.ai/v1

Key behaviours:
- model="auto"  → AO classifies task, routes to cheapest capable model
- model="gpt-4o" → passthrough to that specific model via OpenRouter
- Hard budget guardrails per API key
- Logs every call to savings_log for dashboard
- Exact-match cache check (Phase 3 — slot reserved, cache_enabled flag)
"""

import os, hashlib, json, time, uuid, logging
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("agentoptima.proxy")

router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────────
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
AO_INTERNAL_URL    = os.environ.get("AO_INTERNAL_URL", "http://localhost:8000")

# Default budget for new keys (cents) — $5.00
DEFAULT_BUDGET_CENTS = 500

# Models that are always safe to use as fallback
FALLBACK_MODEL = "openai/gpt-4o-mini"
QUALITY_FALLBACK = "anthropic/claude-haiku-4.5"

# ── Pydantic Models ────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[Message]
    max_tokens: Optional[int] = 1000
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False

# ── DB Helpers (imported from main context via get_db) ────────────────────────

def _get_db():
    """Import get_db from main module at call time to avoid circular imports."""
    from api.main import get_db
    return get_db()

# ── API Key Validation ─────────────────────────────────────────────────────────

def validate_api_key(raw_key: str) -> dict:
    """
    Validate an ao-xxxx key. Returns key record or raises HTTPException.
    Creates demo key on first use if DB table not yet migrated (Phase 0 safety).
    """
    if not raw_key or not raw_key.startswith("ao-"):
        raise HTTPException(status_code=401, detail="Invalid API key format. Use: Bearer ao-yourkey")

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_label, budget_limit_cents, spent_cents, enabled FROM api_keys WHERE key_hash = %s",
                (key_hash,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="API key not found. Generate one at agentoptima.ai/onboarding")
            key_id, label, budget, spent, enabled = row
            if not enabled:
                raise HTTPException(status_code=403, detail="API key disabled. Check your dashboard.")
            return {"id": key_id, "label": label, "budget": budget, "spent": spent}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"DB key validation failed: {e} — allowing request in degraded mode")
        # Degraded mode: allow request if DB is temporarily unreachable
        return {"id": None, "label": "degraded", "budget": DEFAULT_BUDGET_CENTS, "spent": 0}

# ── Budget Enforcement ─────────────────────────────────────────────────────────

def check_budget(key_record: dict) -> None:
    """Hard stop if key is at or over budget."""
    remaining = key_record["budget"] - key_record["spent"]
    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Budget limit reached (${key_record['budget']/100:.2f}). "
                   f"Update your limit at agentoptima.ai/dashboard"
        )

# ── Cache Check (Phase 3 slot — exact match) ──────────────────────────────────

def check_cache(messages: list[Message]) -> Optional[dict]:
    """
    Check exact-match cache. Returns cached response dict or None.
    Phase 3 will populate this — slot reserved here for zero-change integration.
    """
    try:
        normalized = [{"role": m.role, "content": m.content.strip()} for m in messages]
        payload    = json.dumps(normalized, sort_keys=True)
        cache_key  = hashlib.sha256(payload.encode()).hexdigest()

        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT response_json, model_used, cost_cents, id
                   FROM response_cache
                   WHERE cache_key = %s
                     AND (expires_at IS NULL OR expires_at > NOW())
                   LIMIT 1""",
                (cache_key,)
            )
            row = cur.fetchone()
            if row:
                response_json, model_used, cost_cents, cache_id = row
                # Increment hit count
                cur.execute("UPDATE response_cache SET hit_count = hit_count + 1 WHERE id = %s", (cache_id,))
                conn.commit()
                logger.info(f"Cache HIT — key={cache_key[:12]}… model={model_used} saved={cost_cents:.4f}¢")
                return {"response": response_json, "model": model_used, "cost_cents": 0, "cache_hit": True, "saved_cents": cost_cents}
    except Exception as e:
        logger.debug(f"Cache check skipped: {e}")
    return None

def store_cache(messages: list[Message], response_json: dict, model: str, cost_cents: float) -> None:
    """Store response in exact-match cache."""
    try:
        normalized = [{"role": m.role, "content": m.content.strip()} for m in messages]
        payload    = json.dumps(normalized, sort_keys=True)
        cache_key  = hashlib.sha256(payload.encode()).hexdigest()

        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO response_cache (cache_key, request_hash, response_json, model_used, cost_cents, cache_type)
                   VALUES (%s, %s, %s, %s, %s, 'exact')
                   ON CONFLICT (cache_key) DO NOTHING""",
                (cache_key, cache_key, json.dumps(response_json), model, cost_cents)
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"Cache store skipped: {e}")

# ── Model Selection ────────────────────────────────────────────────────────────

def select_model(messages: list[Message], requested_model: str) -> tuple[str, str]:
    """
    Returns (model_id, task_type).
    - model="auto" → classify + route via AO recommend engine
    - model=anything_else → passthrough
    """
    if requested_model != "auto":
        return requested_model, "passthrough"

    # Build task text from last user message
    user_msgs = [m.content for m in messages if m.role == "user"]
    task_text = user_msgs[-1] if user_msgs else ""

    try:
        # Use AO classify + recommend (internal call — same process)
        from api.main import classify_task_internal, get_recommendation_internal
        task_type  = classify_task_internal(task_text)
        model      = get_recommendation_internal(task_type)
        logger.info(f"Auto-route: '{task_text[:40]}…' → {task_type} → {model}")
        return model, task_type
    except Exception as e:
        logger.warning(f"Auto-route failed ({e}), using fallback: {FALLBACK_MODEL}")
        return FALLBACK_MODEL, "general"

# ── OpenRouter Call ────────────────────────────────────────────────────────────

async def call_openrouter(model: str, messages: list[Message], max_tokens: int, temperature: float) -> dict:
    """Forward request to OpenRouter. Returns (response_dict, cost_cents)."""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="Gateway not configured — missing OpenRouter key")

    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agentoptima.ai",
        "X-Title": "AgentOptima",  # OpenRouter affiliate tracking
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(OPENROUTER_API_URL, json=payload, headers=headers)

    duration_s = time.time() - start

    if resp.status_code != 200:
        logger.error(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
        raise HTTPException(status_code=502, detail=f"Model provider error: {resp.status_code}")

    data = resp.json()

    # Extract cost from OpenRouter response
    cost_cents = 0.0
    if "usage" in data:
        usage = data["usage"]
        # OpenRouter returns cost in dollars in x-total-cost header or usage.total_cost
        total_cost_usd = usage.get("total_cost", 0) or 0
        cost_cents = float(total_cost_usd) * 100

    return data, cost_cents, duration_s

# ── Savings Logger ─────────────────────────────────────────────────────────────

def log_savings(key_id, cost_cents: float, saved_cents: float, cache_hit: bool, model: str, task_type: str) -> None:
    """Log to savings_log and update key spent amount."""
    try:
        conn = _get_db()
        today = datetime.now(timezone.utc).date()
        with conn.cursor() as cur:
            if key_id:
                # Upsert daily savings row
                cur.execute(
                    """INSERT INTO savings_log (api_key_id, date, cache_hits, cost_saved_cents, actual_cost_cents)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (api_key_id, date) DO UPDATE SET
                           cache_hits        = savings_log.cache_hits + EXCLUDED.cache_hits,
                           cost_saved_cents  = savings_log.cost_saved_cents + EXCLUDED.cost_saved_cents,
                           actual_cost_cents = savings_log.actual_cost_cents + EXCLUDED.actual_cost_cents""",
                    (key_id, today, 1 if cache_hit else 0, saved_cents, cost_cents)
                )
                # Update key spent amount
                if cost_cents > 0:
                    cur.execute(
                        "UPDATE api_keys SET spent_cents = spent_cents + %s, last_used_at = NOW() WHERE id = %s",
                        (cost_cents, key_id)
                    )
            conn.commit()
    except Exception as e:
        logger.warning(f"Savings log failed (non-critical): {e}")

# ── Main Endpoint ──────────────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None),
    x_ao_cache: Optional[str] = Header(None),   # "off" to bypass cache
):
    """
    OpenAI-compatible chat completions endpoint.
    Drop-in: change base_url = "https://agentoptima.ai/v1"
    """
    # 1. Extract + validate API key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Bearer ao-yourkey")
    raw_key    = authorization.replace("Bearer ", "").strip()
    key_record = validate_api_key(raw_key)

    # 2. Budget check
    check_budget(key_record)

    # 3. Cache check (skip if x-ao-cache: off)
    cache_hit     = False
    saved_cents   = 0.0
    if x_ao_cache != "off":
        cached = check_cache(request.messages)
        if cached:
            log_savings(key_record["id"], 0, cached["saved_cents"], True, cached["model"], "cached")
            return JSONResponse(content=cached["response"])

    # 4. Model selection
    model, task_type = select_model(request.messages, request.model)

    # 5. Forward to OpenRouter
    response_data, cost_cents, duration_s = await call_openrouter(
        model, request.messages, request.max_tokens, request.temperature
    )

    # 6. Store in cache (if cacheable)
    if x_ao_cache != "off" and cost_cents > 0:
        store_cache(request.messages, response_data, model, cost_cents)

    # 7. Log savings (vs always using GPT-4o at ~0.5¢/call baseline)
    gpt4o_baseline_cents = 0.5
    routing_saved = max(0, gpt4o_baseline_cents - cost_cents)
    log_savings(key_record["id"], cost_cents, routing_saved, False, model, task_type)

    # 8. Add AO metadata to response (non-breaking — extra field)
    response_data["_ao"] = {
        "model_used":     model,
        "task_type":      task_type,
        "cost_cents":     round(cost_cents, 6),
        "saved_cents":    round(routing_saved, 6),
        "cache_hit":      False,
        "duration_s":     round(duration_s, 3),
    }

    logger.info(f"Proxy: {task_type} → {model} | {cost_cents:.4f}¢ | {duration_s:.2f}s")
    return JSONResponse(content=response_data)
