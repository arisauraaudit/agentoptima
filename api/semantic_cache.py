"""
AgentOptima Semantic Cache — Phase 5
=====================================
Conservative semantic matching: threshold 0.97, 7-day TTL, no real-time topics.
A miss is always better than a wrong answer.
"""

import os, json, hashlib, logging, math
from typing import Optional

logger = logging.getLogger("agentoptima.semantic_cache")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SEMANTIC_THRESHOLD = 0.97   # extremely conservative — adjust down only with real data
EMBEDDING_MODEL = "openai/text-embedding-3-small"
MAX_PROMPT_CHARS = 2000     # cap embedding input for cost control

# Topics that MUST NOT be served from semantic cache (real-time sensitive)
REALTIME_SIGNALS = [
    "price", "cost", "rate", "today", "now", "current", "latest", "news",
    "weather", "stock", "crypto", "bitcoin", "eth", "market", "breaking",
    "live", "right now", "this week", "this month", "yesterday", "tomorrow",
]


def _is_realtime_query(text: str) -> bool:
    """Return True if the query likely needs fresh data — skip semantic cache."""
    lower = text.lower()
    return any(signal in lower for signal in REALTIME_SIGNALS)


def _cosine_similarity(a: list, b: list) -> float:
    """Pure Python cosine similarity — no numpy required."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def get_embedding(text: str) -> Optional[list]:
    """
    Get embedding via OpenRouter (uses OpenAI embedding model).
    Returns None on any failure — semantic cache degrades gracefully.
    """
    if not OPENROUTER_API_KEY:
        return None
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://agentoptima.ai",
            "X-Title": "AgentOptima",
        }
        payload = {
            "model": EMBEDDING_MODEL,
            "input": text[:MAX_PROMPT_CHARS],
        }
        # Use sync httpx for simplicity (called from sync context)
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/embeddings",
                json=payload,
                headers=headers
            )
        if resp.status_code == 200:
            data = resp.json()
            return data["data"][0]["embedding"]
        else:
            logger.warning(f"Embedding API error {resp.status_code}: {resp.text[:100]}")
            return None
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


def check_semantic_cache(messages: list, get_db_fn) -> Optional[dict]:
    """
    Check semantic cache for a near-match to the current messages.
    Returns cached response dict (with _ao metadata) or None.

    Safety rules:
    - Threshold: 0.97 (extremely conservative)
    - Skip real-time queries entirely
    - Skip if embedding generation fails
    - 7-day TTL enforced
    """
    try:
        # Extract last user message
        user_msgs = [
            m.content if hasattr(m, 'content') else m.get('content', '')
            for m in messages
            if (m.role if hasattr(m, 'role') else m.get('role')) == 'user'
        ]
        if not user_msgs:
            return None
        query_text = user_msgs[-1].strip()

        # Safety: skip real-time queries
        if _is_realtime_query(query_text):
            logger.debug(f"Semantic cache skip (real-time): {query_text[:50]}")
            return None

        # Get embedding for query
        query_embedding = get_embedding(query_text)
        if not query_embedding:
            return None

        # Fetch recent semantic cache entries (last 10K, ordered by recency)
        conn = get_db_fn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, embedding_json, response_json, model_used, cost_cents, prompt_text
                       FROM semantic_cache
                       WHERE expires_at > NOW()
                         AND embedding_json IS NOT NULL
                       ORDER BY created_at DESC
                       LIMIT 10000""",
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return None

        # Find best similarity match
        best_sim = 0.0
        best_row = None
        for row in rows:
            cache_id, emb_json, resp_json, model, cost, prompt = row
            if not emb_json:
                continue
            stored_embedding = emb_json if isinstance(emb_json, list) else json.loads(emb_json)
            sim = _cosine_similarity(query_embedding, stored_embedding)
            if sim > best_sim:
                best_sim = sim
                best_row = row

        if best_sim < SEMANTIC_THRESHOLD or best_row is None:
            logger.debug(
                f"Semantic cache miss (best={best_sim:.4f} < {SEMANTIC_THRESHOLD}): {query_text[:50]}"
            )
            return None

        # HIT — increment counter and return
        cache_id, emb_json, resp_json, model, cost, prompt = best_row
        conn = get_db_fn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = %s",
                    (cache_id,)
                )
                conn.commit()
        finally:
            conn.close()

        resp = resp_json if isinstance(resp_json, dict) else json.loads(resp_json)
        resp["_ao"] = {
            "model_used": model,
            "task_type": "semantic_cache",
            "cost_cents": 0,
            "saved_cents": round(cost, 6),
            "cache_hit": True,
            "semantic_hit": True,
            "similarity": round(best_sim, 4),
            "duration_s": 0.0,
        }
        logger.info(
            f"Semantic cache HIT (sim={best_sim:.4f}): '{query_text[:40]}' → matched '{prompt[:40]}'"
        )
        return {
            "response": resp,
            "model": model,
            "cost_cents": 0,
            "cache_hit": True,
            "saved_cents": cost,
        }

    except Exception as e:
        logger.warning(f"Semantic cache check failed (non-critical): {e}")
        return None


def store_semantic_cache(
    messages: list,
    response_json: dict,
    model: str,
    cost_cents: float,
    get_db_fn,
) -> None:
    """
    Store a new response in the semantic cache with its embedding.
    Fails silently — never blocks the response path.
    """
    try:
        user_msgs = [
            m.content if hasattr(m, 'content') else m.get('content', '')
            for m in messages
            if (m.role if hasattr(m, 'role') else m.get('role')) == 'user'
        ]
        if not user_msgs:
            return
        query_text = user_msgs[-1].strip()

        # Don't store real-time queries
        if _is_realtime_query(query_text):
            return

        cache_key = hashlib.sha256(query_text.lower().encode()).hexdigest()
        embedding = get_embedding(query_text)
        if not embedding:
            return

        clean_response = {k: v for k, v in response_json.items() if k != '_ao'}

        conn = get_db_fn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO semantic_cache
                       (cache_key, prompt_text, embedding_json, response_json, model_used, cost_cents)
                       VALUES (%s, %s, %s::jsonb, %s, %s, %s)
                       ON CONFLICT (cache_key) DO NOTHING""",
                    (
                        cache_key,
                        query_text[:500],
                        json.dumps(embedding),
                        json.dumps(clean_response),
                        model,
                        cost_cents,
                    )
                )
                conn.commit()
                logger.info(f"Semantic cache STORE: '{query_text[:40]}' model={model}")
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Semantic cache store failed (non-critical): {e}")
