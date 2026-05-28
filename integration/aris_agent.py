#!/usr/bin/env python3
"""
AgentOptima tracker — logs every Aris orchestrator task to the live API.
Designed for fire-and-forget use: failures are logged but never raise.
"""

import requests
import uuid
import time
from datetime import datetime

API_BASE_URL  = "https://agentoptima.ai/api/v1"
ARIS_API_KEY  = "ao-41727e957d734ef638903180293af0d6171efda7373902e6"

# ── Task type classifier ───────────────────────────────────────────────────────
_TASK_KEYWORDS = {
    "coding":       ["code", "fix", "bug", "implement", "refactor", "deploy", "build",
                     "script", "function", "class", "debug", "error", "test"],
    "research":     ["research", "analyze", "compare", "benchmark", "find", "search",
                     "investigate", "audit", "review", "check"],
    "strategy":     ["strategy", "plan", "decide", "prioritize", "vision", "roadmap",
                     "design", "architect", "should we", "what next", "options"],
    "writing":      ["write", "draft", "copy", "summarize", "explain", "document",
                     "email", "post", "message", "tweet"],
    "data":         ["data", "database", "sql", "query", "schema", "migrate",
                     "postgres", "sqlite", "ranking", "metrics"],
}

def classify_task(text: str) -> str:
    text_lower = text.lower()
    scores = {t: sum(1 for kw in kws if kw in text_lower)
              for t, kws in _TASK_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


class ArisTracker:
    """Logs Aris tasks to AgentOptima with real model, cost, and token data."""

    def __init__(self, model_name="anthropic/claude-sonnet-4-6",
                 base_url=API_BASE_URL, api_key=ARIS_API_KEY):
        self.api_url  = base_url
        self.model_name = model_name
        self.api_key  = api_key
        self.headers  = {"X-API-Key": api_key} if api_key else {}

    def log(self, *, description: str, model: str = None,
            duration_s: int = 0, cost_usd: float = 0.0,
            input_tokens: int = 0, output_tokens: int = 0,
            success: bool = True, notes: str = None,
            task_type: str = None):
        """
        Primary logging method — call this directly after each task.

        Args:
            description:   Short task description (truncated to 200 chars)
            model:         Actual model used (defaults to tracker default)
            duration_s:    Wall-clock seconds
            cost_usd:      Estimated USD cost from tiers.py estimate_cost_usd()
            input_tokens:  Prompt tokens
            output_tokens: Completion tokens
            success:       Whether the task completed successfully
            notes:         Optional free-text notes or error trace
            task_type:     Override auto-classification
        """
        task_id   = str(uuid.uuid4())[:8]
        task_type = task_type or classify_task(description)
        model     = model or self.model_name
        cost_cents = round(cost_usd * 100, 6)

        full_notes = notes or ""
        if input_tokens or output_tokens:
            full_notes = f"in={input_tokens} out={output_tokens} tokens | " + full_notes

        payload = {
            "task_id":          task_id,
            "task_type":        task_type,
            "task_description": description[:200],
            "model":            model,
            "duration_seconds": duration_s,
            "cost_cents":       cost_cents,
            "success":          success,
            "notes":            full_notes.strip()
        }

        try:
            r = requests.post(f"{self.api_url}/track", json=payload,
                              headers=self.headers, timeout=8)
            if r.status_code == 200:
                print(f"⚡ AgentOptima logged [{task_type}] {task_id} "
                      f"({model}, {duration_s}s, ${cost_usd:.4f})")
            else:
                print(f"⚠️  AgentOptima log failed {r.status_code}: {r.text[:100]}")
        except Exception as e:
            # Never block the orchestrator — just warn
            print(f"⚠️  AgentOptima unreachable: {e}")

        return task_id

    # ── Legacy compatibility ───────────────────────────────────────────────────
    def before_task(self, task_type, description):
        return {"start_time": time.time(), "task_type": task_type,
                "description": description}

    def after_task(self, context, success=True, notes=None, **kwargs):
        """Legacy wrapper — kept for backward compatibility."""
        duration = int(time.time() - context.get("start_time", time.time()))
        desc = (kwargs.get("task_description")
                or context.get("description", "unknown task"))
        self.log(
            description=desc,
            duration_s=duration,
            success=success,
            notes=notes,
            task_type=context.get("task_type"),
        )

    def track_task(self, task_type, task_description, duration_seconds=0,
                   cost_cents=0.0, success=True, notes=None, model=None):
        """Legacy wrapper — kept for backward compatibility."""
        self.log(
            description=task_description,
            model=model,
            duration_s=duration_seconds or 0,
            cost_usd=(cost_cents or 0) / 100,
            success=success,
            notes=notes,
            task_type=task_type,
        )
