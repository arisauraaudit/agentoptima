#!/usr/bin/env python3
"""
AgentOptima API Key Management — Phase 1
==========================================
POST /api/v1/keys/create   → generate new ao-xxxx key
GET  /api/v1/keys/status   → check key usage + savings
PUT  /api/v1/keys/budget   → update budget limit
"""

import secrets, hashlib, logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("agentoptima.keys")
router = APIRouter()

class CreateKeyRequest(BaseModel):
    label: Optional[str] = "my-app"
    email: Optional[str] = None
    budget_limit_cents: Optional[int] = 500   # $5.00 default

class UpdateBudgetRequest(BaseModel):
    budget_limit_cents: int

def _get_db():
    from api.main import get_db
    return get_db()

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def _validate_key(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer ao-"):
        raise HTTPException(status_code=401, detail="Invalid key format")
    raw = authorization.replace("Bearer ", "").strip()
    key_hash = _hash_key(raw)
    conn = _get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, user_label, budget_limit_cents, spent_cents, enabled, plan FROM api_keys WHERE key_hash = %s",
            (key_hash,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Key not found")
        return {"id": row[0], "label": row[1], "budget": row[2], "spent": row[3], "enabled": row[4], "plan": row[5]}


@router.post("/api/v1/keys/create")
def create_key(req: CreateKeyRequest):
    """
    Generate a new ao-xxxx API key.
    Returns the raw key ONCE — we never store it, only the hash.
    """
    raw_key  = "ao-" + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)

    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO api_keys (key_hash, user_label, user_email, budget_limit_cents)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (key_hash, req.label, req.email, req.budget_limit_cents)
            )
            key_id = cur.fetchone()[0]
            conn.commit()

        logger.info(f"New key created: label={req.label} budget={req.budget_limit_cents}¢")
        return JSONResponse({
            "key":                  raw_key,
            "key_id":               str(key_id),
            "label":                req.label,
            "budget_limit_cents":   req.budget_limit_cents,
            "budget_limit_usd":     req.budget_limit_cents / 100,
            "message":              "Save this key — we can't show it again.",
            "quickstart": {
                "python": f'client = OpenAI(api_key="{raw_key}", base_url="https://agentoptima.ai/v1")',
                "curl":   f'curl https://agentoptima.ai/v1/chat/completions -H "Authorization: Bearer {raw_key}" -d \'{{\"model\":\"auto\",\"messages\":[{{\"role\":\"user\",\"content\":\"Hello\"}}]}}\''
            }
        })
    except Exception as e:
        logger.error(f"Key creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create key")


@router.get("/api/v1/keys/status")
def key_status(authorization: Optional[str] = Header(None)):
    """Return usage, spending, and savings for this key."""
    key = _validate_key(authorization or "")

    try:
        conn = _get_db()
        with conn.cursor() as cur:
            # Last 30 days savings
            cur.execute(
                """SELECT
                       COALESCE(SUM(actual_cost_cents), 0)    AS total_spent,
                       COALESCE(SUM(cost_saved_cents), 0)     AS cache_saved,
                       COALESCE(SUM(routing_saved_cents), 0)  AS routing_saved,
                       COALESCE(SUM(cache_hits), 0)           AS total_cache_hits
                   FROM savings_log
                   WHERE api_key_id = %s AND date >= NOW() - INTERVAL '30 days'""",
                (key["id"],)
            )
            row = cur.fetchone()
            spent_30d, cache_saved, routing_saved, cache_hits = row

            total_saved = cache_saved + routing_saved
            budget_remaining = key["budget"] - key["spent"]

        return JSONResponse({
            "label":                    key["label"],
            "plan":                     key["plan"],
            "budget_limit_cents":       key["budget"],
            "budget_limit_usd":         key["budget"] / 100,
            "spent_total_cents":        round(key["spent"], 4),
            "budget_remaining_cents":   round(budget_remaining, 4),
            "budget_remaining_usd":     round(budget_remaining / 100, 4),
            "last_30_days": {
                "spent_cents":          round(spent_30d, 4),
                "saved_cents":          round(total_saved, 4),
                "saved_usd":            round(total_saved / 100, 4),
                "cache_hit_count":      int(cache_hits),
                "cache_saved_cents":    round(cache_saved, 4),
                "routing_saved_cents":  round(routing_saved, 4),
            },
            "enabled": key["enabled"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/v1/keys/budget")
def update_budget(req: UpdateBudgetRequest, authorization: Optional[str] = Header(None)):
    """Update the hard budget limit for this key."""
    key = _validate_key(authorization or "")

    if req.budget_limit_cents < 50:
        raise HTTPException(status_code=400, detail="Minimum budget is $0.50 (50 cents)")

    conn = _get_db()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE api_keys SET budget_limit_cents = %s WHERE id = %s",
            (req.budget_limit_cents, key["id"])
        )
        conn.commit()

    return JSONResponse({
        "updated": True,
        "new_budget_cents": req.budget_limit_cents,
        "new_budget_usd":   req.budget_limit_cents / 100
    })
