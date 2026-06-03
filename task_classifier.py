#!/usr/bin/env python3
"""
task_classifier.py — Fast rule-based + keyword heuristic classifier for Telegram messages.

No LLM call. Pure heuristics. Returns classification in <1ms.

Output:
    {
        "complexity": "simple" | "complex",
        "task_type":  "coding" | "research" | "strategy" | "writing" |
                      "data" | "general" | "math" | "security",
        "confidence": 0.0–1.0,
        "reason":     "one-line explanation"
    }
"""

import re
import sys
import json

# ── Keyword tables ─────────────────────────────────────────────────────────────

# Task type → trigger keywords/phrases (lowercase, substring match)
TASK_TYPE_SIGNALS: dict[str, list[str]] = {
    "strategy": [
        "strategy", "strategic", "pivot", "roadmap",
        "business model", "go-to-market", "gtm", "market fit", "product-market",
        "trade-off", "tradeoff",
        "north star", "mission statement", "positioning",
        "competitive moat", "moat", "differentiation", "growth strategy",
        "launch strategy", "expansion plan", "fundraise", "investor pitch",
        "design the complete", "design the full", "design the entire",
        "product strategy", "feature roadmap", "go to market",
    ],
    "security": [
        "security", "vulnerability", "exploit", "injection", "xss", "csrf",
        "auth", "authentication", "authorization", "oauth", "jwt", "token leak",
        "rate limit", "brute force", "firewall", "pentest", "penetration",
        "malware", "phishing", "zero-day", "privilege escalation",
        "encryption", "hash", "bcrypt", "secret", "api key exposure",
    ],
    "coding": [
        # Bug fixing
        "fix the bug", "fix bug", "debug", "error on line", "traceback",
        "syntax error", "runtime error", "exception", "not working", "broken",
        # Building / creating
        "build", "create a", "implement", "develop", "make a", "make the",
        "write a function", "write a script", "write a class",
        "refactor", "update the code", "update our code", "modify the file",
        "add a feature", "new feature", "lets add", "let's add",
        "add this to the", "add to the website", "add to the dashboard",
        # Files / code artifacts (extension must appear in context of building)
        ".py", ".js", ".ts", ".html", ".css", ".sh", ".yaml", ".yml",
        "function(", "unit test", "test case", "def ", "class ",
        # Dev workflow
        "deploy", "git", "commit", "push", "pull request", "merge",
        "dockerfile", "bash script", "shell command", "regex", "api endpoint",
        # Website / frontend
        "website", "index.html", "add section", "add feature to",
        # Classifier / router specific (only when fixing/building it)
        "classifier", "task_classifier", "keyword",
        "misfiring", "misfire", "improve the classifier", "fix the classifier",
        "improve classifier", "tune the classifier", "improve the router",
        "fix the router", "update the router", "fix router",
    ],
    "math": [
        "calculate", "compute", "how much is",
        "percent of", "% of", "formula", "equation", "solve for", "integral",
        "derivative", "matrix", "algebra", "statistics",
        "standard deviation", "probability", "factorial",
        "what is 2", "what is the sum", "what is the average",
        "what is the total", "what is the difference between",
    ],
    "data": [
        "format the data", "parse the data", "json data", "csv file", "csv data",
        "table of", "sort the", "filter the",
        "count the", "summarize the data", "extract data", "transform data",
        "schema", "sql", "query", "dataframe", "spreadsheet",
        "clean the data", "normalize", "rankings", "ranking",
        "benchmark results", "cost breakdown table",
    ],
    "writing": [
        "write a blog", "blog post", "draft", "copywrite", "email template",
        "write a post", "linkedin post", "tweet", "announcement",
        "press release", "write an article", "newsletter", "changelog",
        "product description", "marketing copy", "tagline", "slogan",
        "write a README", "documentation", "brief", "write a report",
        "write a summary", "write up",
        "reddit post", "post for reddit", "post about", "write about",
        "social media", "caption",
    ],
    "research": [
        "research", "what is the latest", "compare", "explain", "overview",
        "how does", "what are the", "find information", "look up",
        "survey", "summarize", "literature", "state of the art", "review",
        "who is", "what company", "market size", "competitor analysis",
        "what happened", "analyze", "analysis", "investigate", "audit",
        # Status / evaluation queries
        "what is the current", "what is the status", "current status",
        "evaluate the cost", "evaluate saving", "evaluate the",
        "cost benefit", "cost-benefit", "is it worth", "should we",
        "how is", "how are", "tell me about", "give me an overview",
        "what does", "how can", "what can",
    ],
    "orchestration": [
        "break this into", "delegate", "coordinate", "manage", "orchestrate",
        "plan and execute", "end to end", "end-to-end", "full pipeline",
        "step by step plan", "assign", "sub-task", "subtask",
        "who should", "which model", "route this", "best agent for",
        "decompose", "multi-step", "multi step",
    ],
    "general": [
        "weather", "time", "date", "news", "hello", "hi", "status",
        "what's up", "ping", "check", "is the server", "show me",
        "list me", "tell me", "remind me",
    ],
}

# Complexity signals — strong indicators of complex tasks
COMPLEX_SIGNALS = [
    "design the", "design a", "design an",
    "architect", "architecture",
    "full system", "complete system",
    "end-to-end", "end to end",
    "strategy", "strategic",
    "multi-step", "multiple steps",
    "comprehensive", "holistic",
    "should we pivot", "should we", "is it worth",
    "make a decision", "help me decide",
    "business model", "roadmap",
    "trade-off", "tradeoff",
    "long-term", "north star",
    "analyze and recommend",
    "pros and cons of",
    # Multi-step composite tasks
    "analyze",            # never trivial — research + synthesis
    "and write",          # composite: do X then produce written output
    "and give me",        # composite: research + deliver
    "optimization brief", # analysis + deliverable
]

# Complexity signals — strong indicators of simple tasks
SIMPLE_SIGNALS = [
    "what is the weather", "what's the weather",
    "convert", "format this", "fix the bug on line", "fix line",
    "how many", "what time is it", "current time", "today's date",
    "list of", "show the", "ping", "status check",
    "single line", "quick question",
    "what does this error mean",
    "format this json", "format the json",
    "is the server up", "is it up",
]

# Subtype signals — categorize within task types
SUBTYPE_SIGNALS = {
    # coding subtypes
    "coding/python":       ["python", "async", "def ", "import", "class ", "django", "flask", "fastapi"],
    "coding/sql":          ["sql", "query", "select", "join", "table", "database", "postgresql", "mysql"],
    "coding/debugging":    ["bug", "debug", "fix", "error", "exception", "traceback", "broken", "issue"],
    "coding/architecture": ["design", "architecture", "system", "redis", "cache", "microservice", "pattern", "scalab"],
    "coding/frontend":     ["html", "css", "react", "javascript", "ui", "component", "frontend", "responsive"],
    "coding/testing":      ["test", "unittest", "pytest", "assert", "coverage", "mock"],
    # research subtypes
    "research/technical":  ["how does", "explain", "transformer", "algorithm", "mechanism", "internals"],
    "research/market":     ["market", "trend", "industry", "competitor", "landscape"],
    "research/competitive": ["compare", "vs", "versus", "better than", "alternative"],
    # strategy subtypes
    "strategy/product":    ["product", "roadmap", "feature", "user", "mvp", "launch"],
    "strategy/pricing":    ["pricing", "price", "monetiz", "revenue", "cost model", "subscription"],
    "strategy/gtm":        ["go-to-market", "gtm", "marketing", "distribution", "channel", "adoption"],
    # data subtypes
    "data/analysis":       ["analyze", "analysis", "insight", "pattern", "trend", "breakdown"],
    "data/etl":            ["etl", "pipeline", "transform", "ingest", "parse", "process"],
    # writing subtypes
    "writing/technical":   ["documentation", "readme", "api doc", "technical write"],
    "writing/marketing":   ["copy", "landing page", "headline", "tagline", "pitch"],
    "writing/brief":       ["brief", "summary", "report", "outline"],
}


# ── Classifier ─────────────────────────────────────────────────────────────────

def classify(message: str) -> dict:
    """
    Classify a Telegram message into complexity + task type.

    Returns:
        dict with keys: complexity, task_type, confidence, reason
    """
    msg = message.lower().strip()

    # ── Step 1: Task type detection (scores) ─────────────────────────────────
    type_scores: dict[str, int] = {t: 0 for t in TASK_TYPE_SIGNALS}
    for task_type, keywords in TASK_TYPE_SIGNALS.items():
        for kw in keywords:
            if kw in msg:
                type_scores[task_type] += 1

    # Pick best task type
    best_type = max(type_scores, key=lambda t: type_scores[t])
    best_score = type_scores[best_type]

    if best_score == 0:
        best_type = "general"
        type_confidence = 0.5
    elif best_score == 1:
        type_confidence = 0.7
    elif best_score == 2:
        type_confidence = 0.85
    else:
        type_confidence = 0.95

    # Tie-breaking: strategy only overrides if it scored at least as high as the winner
    # (prevents casual questions with one strategy keyword from hard-routing to Sonnet)
    if type_scores["strategy"] > 0 and best_type not in ("strategy", "security"):
        if type_scores["strategy"] >= best_score:
            best_type = "strategy"
            type_confidence = max(type_confidence, 0.8)

    # ── Step 2: Complexity detection ─────────────────────────────────────────
    complexity = "simple"
    complexity_reason = "no strong complexity signals found"
    complexity_confidence = 0.8

    # Check complex signals
    complex_hit = None
    for signal in COMPLEX_SIGNALS:
        if signal in msg:
            complex_hit = signal
            break

    # Check simple signals
    simple_hit = None
    for signal in SIMPLE_SIGNALS:
        if signal in msg:
            simple_hit = signal
            break

    if complex_hit and not simple_hit:
        complexity = "complex"
        complexity_reason = f"complex signal: '{complex_hit}'"
        complexity_confidence = 0.9
    elif simple_hit and not complex_hit:
        complexity = "simple"
        complexity_reason = f"simple signal: '{simple_hit}'"
        complexity_confidence = 0.92
    elif complex_hit and simple_hit:
        # Both signals — cautious: treat as complex
        complexity = "complex"
        complexity_reason = f"both signals present — defaulting complex; complex='{complex_hit}'"
        complexity_confidence = 0.75
    else:
        # No explicit signal — infer from task type
        if best_type in ("strategy", "security"):
            complexity = "complex"
            complexity_reason = f"task type '{best_type}' defaults to complex"
            complexity_confidence = 0.85
        elif best_type in ("coding",):
            # Short messages with simple action words → simple
            word_count = len(msg.split())
            if word_count <= 15:
                complexity = "simple"
                complexity_reason = f"short coding task ({word_count} words)"
                complexity_confidence = 0.72
            else:
                complexity = "complex"
                complexity_reason = f"longer coding task ({word_count} words)"
                complexity_confidence = 0.65
        elif best_type in ("math", "data", "general"):
            complexity = "simple"
            complexity_reason = f"task type '{best_type}' defaults to simple"
            complexity_confidence = 0.78
        elif best_type == "research":
            # Research tasks are assumed complex unless very short (≤6 words)
            word_count = len(msg.split())
            if word_count <= 6:
                complexity = "simple"
                complexity_reason = f"very short research query ({word_count} words)"
                complexity_confidence = 0.70
            else:
                complexity = "complex"
                complexity_reason = f"research task defaults to complex ({word_count} words)"
                complexity_confidence = 0.78
        elif best_type == "writing":
            # Writing tasks with any non-trivial scope → complex
            word_count = len(msg.split())
            # "draft" or "write a" with a subject → complex
            writing_complex_hints = ["blog", "article", "newsletter", "post", "email template",
                                     "press release", "documentation", "readme", "announcement"]
            if any(hint in msg for hint in writing_complex_hints):
                complexity = "complex"
                complexity_reason = "writing task with substantive scope"
                complexity_confidence = 0.80
            elif word_count > 8:
                complexity = "complex"
                complexity_reason = f"longer writing task ({word_count} words)"
                complexity_confidence = 0.72
            else:
                complexity = "simple"
                complexity_reason = f"short writing task ({word_count} words)"
                complexity_confidence = 0.68
        else:
            # fallback
            word_count = len(msg.split())
            if word_count <= 10:
                complexity = "simple"
                complexity_reason = f"short {best_type} task ({word_count} words)"
                complexity_confidence = 0.68
            else:
                complexity = "complex"
                complexity_reason = f"longer {best_type} task ({word_count} words)"
                complexity_confidence = 0.68

    # ── Step 3: Override rules ────────────────────────────────────────────────
    # Strategy is ALWAYS complex regardless
    if best_type == "strategy":
        complexity = "complex"
        complexity_reason = "strategy tasks are always complex"
        complexity_confidence = 0.99

    # Security + complex → stays complex
    if best_type == "security" and complexity == "complex":
        complexity_confidence = min(complexity_confidence + 0.05, 0.99)

    # ── Step 4: Subtype detection ────────────────────────────────────────────
    # Detect subcategory within the task type
    task_subtype = None
    for subtype, keywords in SUBTYPE_SIGNALS.items():
        # Only consider subtypes that match the detected task_type
        subtype_type = subtype.split("/")[0]
        if subtype_type == best_type:
            for kw in keywords:
                if kw in msg:
                    task_subtype = subtype
                    break
            if task_subtype:
                break

    # Final confidence = geometric mean of type + complexity confidences
    confidence = round((type_confidence * complexity_confidence) ** 0.5, 3)

    return {
        "complexity": complexity,
        "task_type": best_type,
        "task_subtype": task_subtype,
        "confidence": confidence,
        "reason": f"{complexity_reason}; type='{best_type}' (score={best_score})",
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 task_classifier.py \"Your message here\"")
        sys.exit(1)
    msg = " ".join(sys.argv[1:])
    result = classify(msg)
    print(json.dumps(result, indent=2))
