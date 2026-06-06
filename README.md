# AgentOptima — AI Routing OS

> Plug AgentOptima into any agent and immediately do more with less. Smarter routing, lower costs, zero rewrite.

## What It Does

AgentOptima is a plug-and-play API that turns any AI agent into a cost-optimized, self-improving routing machine.

- **Route smarter** — classify tasks and match them to the right model automatically
- **Spend less** — 60-80% cost reduction by avoiding Sonnet for simple tasks  
- **Retry intelligently** — 3-model cascade before escalating to expensive models
- **Learn continuously** — tracks outcomes and improves recommendations over time

## Quick Start (2 minutes)

### 1. Get OpenRouter (recommended)
For access to 20+ models: [openrouter.ai/?via=agentoptima](https://openrouter.ai/?via=agentoptima)

### 2. Classify your task
```python
import requests

response = requests.post(
    "https://agentoptima.ai/api/v1/classify",
    headers={"X-API-Key": "your-key"},
    json={"message": "build a REST API for user auth"}
)
# → {"task_type": "coding", "recommended_cascade": ["gpt-4o-mini", "claude-haiku-4.5", "o3-mini"]}
```

### 3. Get model recommendation
```python
rec = requests.get(
    "https://agentoptima.ai/api/v1/recommend?task_type=coding",
    headers={"X-API-Key": "your-key"}
).json()
model = rec["recommended_model"]  # data-driven, improves over time
```

### 4. Log outcomes (makes recommendations smarter)
```python
requests.post(
    "https://agentoptima.ai/api/v1/track",
    headers={"X-API-Key": "your-key"},
    json={
        "task_id": "task-001",
        "task_type": "coding",
        "model": "openai/gpt-4o-mini",
        "success": True,
        "duration_seconds": 4.2,
        "cost_cents": 0.02
    }
)
```

## API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/classify` | POST | Required | Classify task → get type + model cascade |
| `/api/v1/recommend` | GET | Required | Best model for task type (data-driven) |
| `/api/v1/cascade` | GET | None | Retry waterfall for task type |
| `/api/v1/registry` | GET | Required | All tracked models with cost/performance |
| `/api/v1/track` | POST | Required | Log task outcome for learning |
| `/api/v1/status` | GET | Required | API health + task counts |

## Model Registry

AgentOptima tracks 8 models across 4 tiers:

| Tier | Models | Best For |
|------|--------|----------|
| Ultra-cheap | gpt-4o-mini, deepseek-v4-flash | Simple tasks, drafts |
| Free | gpt-oss-120b, gemma-4-31b | Experimentation |
| Mid | claude-haiku-4.5, o3-mini | Complex tasks, reasoning |
| Quality | claude-sonnet-4-6 | Strategy, critical decisions |
| Oracle | claude-opus-4 | High-stakes verification |

## The Cascade Pattern

Instead of always using your most expensive model, AgentOptima gives you a retry waterfall:
```
Task fails on gpt-4o-mini → retry with claude-haiku-4.5 → retry with o3-mini → escalate to sonnet
```

Get the cascade for any task type:
```bash
curl https://agentoptima.ai/api/v1/cascade?task_type=coding
```

## Status
- **Version:** 1.1.10
- **Tasks tracked:** 400K+
- **Uptime:** Railway managed PostgreSQL + auto-deploy
- **Beta:** Contact for API access

## Built With
- FastAPI + PostgreSQL (Railway)
- OpenRouter for multi-model access
- 400K+ real task outcomes powering recommendations
