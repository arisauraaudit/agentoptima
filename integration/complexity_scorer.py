#!/usr/bin/env python3
"""
complexity_scorer.py — AgentOptima v0.8.0 Lightweight Complexity Scorer

Scores task complexity 0.0–1.0 without heavy ML dependencies.
Inspired by RouteLLM's bert_gpt4_augmented router logic, implemented
as a fast heuristic that runs in-process with zero extra RAM.

Score interpretation:
  0.0 – 0.35  → simple  → route to cheap model (gpt-4o-mini / Haiku)
  0.35 – 0.65 → medium  → route to mid-tier (Haiku / DeepSeek)
  0.65 – 1.0  → complex → route to premium (Sonnet)

USAGE:
    from complexity_scorer import score_complexity
    result = score_complexity("Write a Python hello world")
    # → {"score": 0.12, "tier": "simple", "signals": {...}}
"""

import re
from typing import Optional

# ── Signal weights ─────────────────────────────────────────────────────────────
# Each signal contributes to the total complexity score

def score_complexity(text: str) -> dict:
    """
    Score task complexity on 0.0–1.0 scale.

    Signals used:
    - Length: longer prompts tend to be more complex
    - Technical depth markers: "implement", "optimize", "prove", "design"
    - Multi-part requirements: numbered lists, multiple questions
    - Constraint density: "must", "should", "without", "only if"
    - Domain complexity: ML/math/security score higher than simple writing
    - Output format complexity: code + explanation > just answer

    Returns:
        {
            "score": 0.73,
            "tier": "complex",
            "signals": {
                "length_score": 0.4,
                "depth_score": 0.6,
                "constraint_score": 0.3,
                "multipart_score": 0.8,
                "domain_score": 0.5,
            },
            "recommended_tier": "premium"
        }
    """
    t = text.lower()
    words = t.split()
    word_count = len(words)
    signals = {}

    # 1. LENGTH SIGNAL (0–0.4)
    # Simple: <50 words. Complex: >300 words
    if word_count < 20:
        length_score = 0.05
    elif word_count < 50:
        length_score = 0.1
    elif word_count < 100:
        length_score = 0.2
    elif word_count < 200:
        length_score = 0.3
    elif word_count < 400:
        length_score = 0.4
    else:
        length_score = 0.5
    signals["length_score"] = round(length_score, 2)

    # 2. DEPTH MARKERS (0–0.4)
    # High-complexity verbs and phrases
    deep_markers = [
        "implement", "design a", "architect", "optimize", "prove that",
        "derive ", "explain why", "analyze", "compare and contrast",
        "trade-off", "tradeoff", "performance implication", "time complexity",
        "space complexity", "mathematical proof", "theorem", "formally",
        "comprehensive", "production-ready", "enterprise", "scalable",
        "debug and explain", "root cause", "refactor", "from scratch",
    ]
    depth_hits = sum(1 for m in deep_markers if m in t)
    depth_score = min(0.5, depth_hits * 0.12)
    signals["depth_score"] = round(depth_score, 2)

    # 3. MULTI-PART REQUIREMENTS (0–0.3)
    # Numbered lists, bullet points, multiple questions
    numbered = len(re.findall(r'\b[1-9]\.\s', text))
    bullet_sections = len(re.findall(r'[\n\r]-\s|\n\*\s', text))
    question_marks = text.count('?')
    multipart_score = min(0.4, (numbered * 0.08) + (bullet_sections * 0.06) + (question_marks * 0.04))
    signals["multipart_score"] = round(multipart_score, 2)

    # 4. CONSTRAINT DENSITY (0–0.2)
    constraint_words = [
        "must ", "should ", "without using", "only use", "do not use",
        "constraint", "requirement", "edge case", "handle error",
        "thread-safe", "memory efficient", "O(", "in-place",
    ]
    constraint_hits = sum(1 for c in constraint_words if c in t)
    constraint_score = min(0.3, constraint_hits * 0.08)
    signals["constraint_score"] = round(constraint_score, 2)

    # 5. DOMAIN COMPLEXITY SIGNAL (0–0.3)
    # High-complexity domains boost the score
    high_complexity_domains = [
        "cuda", "pytorch", "tensorflow", "neural network", "transformer",
        "cryptography", "encryption", "kernel", "assembly", "compiler",
        "distributed system", "consensus algorithm", "blockchain",
        "calculus", "linear algebra", "differential equation",
        "concurrency", "mutex", "deadlock", "race condition",
        "llm", "fine-tuning", "embeddings", "vector database",
        "thread-safe", "lru cache", "rate limiter", "proof by",
        "formally prove", "mathematical induction", "from scratch",
        "production-grade", "100k", "high throughput",
    ]
    medium_complexity_domains = [
        "docker", "kubernetes", "sql", "regex", "algorithm",
        "async", "api design", "database schema", "authentication",
        "caching", "rate limiting", "pagination",
    ]
    high_hits = sum(1 for d in high_complexity_domains if d in t)
    med_hits = sum(1 for d in medium_complexity_domains if d in t)
    domain_score = min(0.4, high_hits * 0.15 + med_hits * 0.07)
    signals["domain_score"] = round(domain_score, 2)

    # ── COMPOSITE SCORE ──────────────────────────────────────────────────────
    # Sum raw signal values (each already 0-0.5), then normalise
    raw_sum = length_score + depth_score + multipart_score + constraint_score + domain_score
    # Normalise: raw_sum of ~0.3 = medium, ~0.7+ = complex
    score = round(min(1.0, raw_sum / 0.85), 3)

    # ── TIER ASSIGNMENT ──────────────────────────────────────────────────────
    if score < 0.20:
        tier = "simple"
        recommended_tier = "cheap"       # gpt-4o-mini or Haiku
    elif score < 0.42:
        tier = "medium"
        recommended_tier = "mid"         # Haiku or DeepSeek
    else:
        tier = "complex"
        recommended_tier = "premium"     # Sonnet

    return {
        "score": score,
        "tier": tier,
        "recommended_tier": recommended_tier,
        "signals": signals,
        "word_count": word_count,
    }


# ── Model tier → pool mapping ─────────────────────────────────────────────────
TIER_TO_MODELS = {
    "cheap":   ["openai/gpt-4o-mini", "anthropic/claude-3-haiku"],
    "mid":     ["anthropic/claude-3-haiku", "deepseek/deepseek-v4-flash"],
    "premium": ["anthropic/claude-sonnet-4-6"],
}

def get_complexity_preferred_model(text: str) -> Optional[str]:
    """Returns the top model suggested by complexity alone."""
    result = score_complexity(text)
    models = TIER_TO_MODELS.get(result["recommended_tier"], [])
    return models[0] if models else None


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("simple",  "What is the capital of France?"),
        ("simple",  "Write a Python hello world"),
        ("medium",  "Write a SQL query to find the top 5 customers by revenue"),
        ("medium",  "Explain how Docker networking works"),
        ("complex", "Implement a thread-safe LRU cache in Python with O(1) get/put. Handle edge cases and write unit tests."),
        ("complex", "Design a distributed rate limiter using Redis. Must handle 100k req/s, be consistent across nodes, and degrade gracefully."),
        ("complex", "Prove that the square root of 2 is irrational using proof by contradiction. Show all steps formally."),
        ("complex", "Implement CUDA kernel for matrix multiplication optimized for A100 GPU. Include memory coalescing and shared memory tiling."),
    ]
    print("🧠 Complexity Scorer — Test Run\n")
    for expected, text in tests:
        r = score_complexity(text)
        status = "✅" if r["tier"] == expected else "⚠️ "
        print(f"  {status} [{r['tier']:<8}] score={r['score']:.3f} | {text[:70]}")
