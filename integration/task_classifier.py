#!/usr/bin/env python3
"""
task_classifier.py — AgentOptima v0.8.0 Task Classifier

Maps incoming task descriptions to AgentOptima subtypes using:
1. Keyword matching against ArenaHard cluster taxonomy (fast, zero-cost)
2. Falls back to existing broad categories

USAGE:
    from task_classifier import classify_task
    result = classify_task("Write a Python function to sort a list")
    # → {"subtype": "coding/python", "category": "coding", "confidence": 0.85}
"""

import re
from typing import Optional

# ── Taxonomy from ArenaHard 250 clusters → 26 subtypes ───────────────────────
SUBTYPE_KEYWORDS = {
    "coding/python": [
        "python", "django", "flask", "fastapi", "pandas", "numpy", "matplotlib",
        "pip", "venv", "pytest", "asyncio", "class", "def ", "lambda", ".py",
        "list comprehension", "decorator", "generator", "pickle",
    ],
    "coding/sql": [
        "sql", "postgresql", "mysql", "sqlite", "select ", "insert into",
        "join ", "where ", "group by", "database query", "schema", "orm",
    ],
    "coding/debugging": [
        "debug", "fix this", "why is this wrong", "error in", "bug in",
        "not working", "traceback", "exception", "TypeError", "ValueError",
        "refactor", "deobfuscat", "broken code",
    ],
    "coding/frontend": [
        "react", "vue", "angular", "css", "html", "javascript", "typescript",
        "tailwind", "bootstrap", "next.js", "svelte", "dom ", "frontend",
        "ui component", "responsive", "flexbox", "grid layout",
    ],
    "coding/architecture": [
        "architecture", "microservice", "api design", "rest api", "graphql",
        "docker", "kubernetes", "k8s", "deployment", "ci/cd", "devops",
        "node.js", "express", "fastify", "laravel", "symfony", "cqrs",
    ],
    "coding/algorithms": [
        "algorithm", "sort", "binary search", "dynamic programming", "recursion",
        "linked list", "tree ", "graph ", "heap", "queue", "stack",
        "time complexity", "big o", "leetcode", "competitive programming",
        "fibonacci", "factorial",
    ],
    "coding/ml": [
        "pytorch", "tensorflow", "keras", "neural network", "model training",
        "embedding", "transformer", "attention", "fine-tuning", "llm",
        "machine learning", "deep learning", "gradient", "backprop",
        "classification", "regression", "clustering", "huggingface",
    ],
    "coding/ops": [
        "linux", "bash", "shell script", "cron", "systemd", "nginx", "docker compose",
        "kubernetes", "aws", "gcp", "azure", "terraform", "ansible",
        "network", "firewall", "ssh", "vpn", "subnet",
    ],
    "coding/testing": [
        "unit test", "integration test", "pytest", "jest", "mocha", "mock",
        "test coverage", "tdd", "bdd", "selenium", "cypress",
    ],
    "coding/gpu": [
        "cuda", "gpu", "vram", "parallel computing", "shader", "opengl",
        "matrix multiplication", "tensor", "performance optimization gpu",
    ],
    "math/statistics": [
        "probability", "statistics", "standard deviation", "variance",
        "distribution", "p-value", "hypothesis", "regression", "correlation",
        "sample size", "confidence interval", "bayes",
    ],
    "math/algebra": [
        "algebra", "equation", "calculus", "derivative", "integral",
        "linear algebra", "matrix", "vector", "eigenvalue", "proof",
        "geometry", "triangle", "prime number", "modular arithmetic",
    ],
    "math/logic": [
        "logic puzzle", "sequence", "pattern", "riddle", "puzzle",
        "deduction", "inference", "set theory", "boolean",
    ],
    "research/technical": [
        "explain how", "how does", "what is", "overview of", "introduction to",
        "research on", "survey of", "literature review",
        "technical explanation", "compare technologies",
    ],
    "research/market": [
        "market research", "market size", "industry analysis", "competitor",
        "startup", "business model", "venture", "fundraising", "investor",
        "stock market", "trading strategy", "crypto",
    ],
    "research/competitive": [
        "competitive analysis", "swot", "positioning", "differentiation",
        "compare products", "benchmark comparison", "vs ", "versus",
    ],
    "strategy/product": [
        "product roadmap", "feature", "user story", "product strategy",
        "mvp", "product-market fit", "ux", "user experience", "persona",
    ],
    "strategy/gtm": [
        "go to market", "gtm", "launch strategy", "marketing plan",
        "customer acquisition", "growth strategy", "seo", "content marketing",
        "go-to-market", "saas strategy", "product launch", "user acquisition",
        "growth hacking", "distribution strategy", "channel strategy",
    ],
    "strategy/analysis": [
        "business analysis", "operations", "process improvement", "kpi",
        "metrics", "okr", "strategic plan", "executive", "board",
    ],
    "strategy/pricing": [
        "pricing strategy", "revenue model", "monetization", "saas pricing",
        "unit economics", "ltv", "cac", "margin", "tax", "accounting",
    ],
    "data/analysis": [
        "data analysis", "data pipeline", "etl", "data quality",
        "dashboard", "visualization", "report", "analytics", "bi tool",
    ],
    "data/performance": [
        "performance", "optimization", "latency", "throughput", "benchmark",
        "profiling", "bottleneck", "scale",
    ],
    "writing/marketing": [
        "write a blog", "marketing copy", "email campaign", "ad copy",
        "content strategy", "social media post", "copywriting", "headline",
    ],
    "security/hacking": [
        "security", "vulnerability", "exploit", "penetration test", "pentest",
        "xss", "sql injection", "cve", "cryptography", "encryption",
        "password", "hacking", "wifi security",
    ],
    "knowledge/general": [
        "explain", "describe", "what are", "history of", "philosophy",
        "medical", "healthcare", "science", "climate",
    ],
    "conversation/roleplay": [
        "roleplay", "act as", "pretend", "character", "story", "fiction",
        "dialogue", "scenario",
    ],
}

# Broader category fallbacks
CATEGORY_FROM_SUBTYPE = {s: s.split("/")[0] for s in SUBTYPE_KEYWORDS}

def classify_task(text: str, top_k: int = 1) -> dict:
    """
    Classify a task description into an AgentOptima subtype.

    Returns:
        {
            "subtype": "coding/python",
            "category": "coding",
            "confidence": 0.85,
            "method": "keyword",
            "scores": {"coding/python": 3, "coding/algorithms": 1, ...}
        }
    """
    text_lower = text.lower()

    # Score each subtype by keyword hits
    scores = {}
    for subtype, keywords in SUBTYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits > 0:
            scores[subtype] = hits

    if not scores:
        return {
            "subtype": "general",
            "category": "general",
            "confidence": 0.3,
            "method": "fallback",
            "scores": {}
        }

    # Best match
    best_subtype = max(scores, key=scores.get)
    max_score = scores[best_subtype]
    total_score = sum(scores.values())
    confidence = min(0.95, max_score / max(total_score, 1) + 0.3)

    return {
        "subtype": best_subtype,
        "category": best_subtype.split("/")[0],
        "confidence": round(confidence, 2),
        "method": "keyword",
        "scores": dict(sorted(scores.items(), key=lambda x: -x[1])[:5])
    }


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "Write a Python function to parse JSON and filter by date",
        "Optimize this SQL query for better performance",
        "Fix the bug in my React component - useState not updating",
        "Explain gradient descent and backpropagation",
        "What is the market size for AI routing APIs?",
        "Write a go-to-market strategy for a SaaS product",
        "Calculate the probability of rolling a 6 twice in a row",
        "How does encryption work in TLS?",
        "Debug this Docker compose file that keeps crashing",
    ]
    print("🧪 Task Classifier — Test Run\n")
    for t in tests:
        r = classify_task(t)
        print(f"  [{r['subtype']:<30}] conf={r['confidence']:.2f} | {t[:60]}")
