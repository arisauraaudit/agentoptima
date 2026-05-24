# AgentOptima Beta Integration Guide

## Status: ✅ Ready for Aris Beta Testing

### What's Live

1. **API Endpoints** (https://agentoptima.ai/api)
   - `GET /health` - Health check
   - `GET /api/v1/recommendations` - Get performance insights
   - `POST /api/v1/track` - Log agent tasks
   - `GET /api/v1/status` - System status

2. **Aris Integration Module**
   - Location: `/root/.openclaw/workspace/AgentOptima/integration/aris_agent.py`
   - Usage: `from integration.aris_agent import ArisTracker`

---

## Quick Start for Aris (Option B)

### Step 1: Import the Tracker
```python
from integration.aris_agent import ArisTracker

# Initialize
tracker = ArisTracker(model_name="claude-sonnet-4-6")  # Match your model
```

### Step 2: Wrap Your Tasks
```python
# Before task
context = tracker.before_task(
    task_type="research", 
    description="Analyze market opportunity"
)

# ... execute your task ...

# After task (success or failure)
tracker.after_task(
    context, 
    success=True, 
    notes="Completed 4-hour analysis"
)
```

### Step 3: Get Recommendations
```python
# Morning check-in
recs = tracker.get_recommendations()
if recs and recs.get('recommendations'):
    for rec in recs['recommendations']:
        print(f"[{rec['priority'].upper()}] {rec['message']}")
```

---

## Example: Track Your First Task

```bash
# Test the tracker locally
cd /root/.openclaw/workspace/AgentOptima
python3 integration/aris_agent.py
```

Expected output:
```
💾 Logged task: a1b2c3d4 (deployment)
✅ Task a1b2c3d4 logged to AgentOptima
💡 Recommendations loaded: Analyzed 1 tasks | Success rate: 1/1 | Avg duration: 2.0s | Total cost: $0.00
```

---

## Integration Points to Add to Aris

### 1. Post-Task Tracking
**Where**: After every Aris completion message

**Add**:
```python
# In /root/.aris/orchestrator.py or main agent loop
tracker = ArisTracker()

# After task completion
tracker.after_task(context, success=True, notes=f"Completed {task_description}")
```

### 2. Morning Recommendations Check
**Where**: At agent startup or via cron

**Add**:
```python
# Daily recommendations fetch
recs = tracker.get_recommendations()
# Log any high-priority recommendations to your partner
```

### 3. Error Tracking
**Where**: In exception handlers

**Add**:
```python
try:
    # ... task logic ...
except Exception as e:
    tracker.after_task(context, success=False, notes=str(e))
    raise
```

---

## MVP Roadmap (Option A - Later)

When ready to build out the full analytics engine:

1. **PostgreSQL deployment** on Railway or DO
2. **Analytics engine** - Real-time performance dashboard
3. **Research monitor** - Auto-scrape arXiv for AI papers
4. **Batch processing** - Aggregate task data for insights

---

## Testing

### Test API endpoints
```bash
curl https://agentoptima.ai/health
curl https://agentoptima.ai/api/v1/status
curl -X POST https://agentoptima.ai/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{"task_id":"test","task_type":"test","task_description":"Beta test","model":"test"}'
curl https://agentoptima.ai/api/v1/recommendations
```

### Run Aris tracker locally
```bash
cd /root/.openclaw/workspace/AgentOptima
python3 integration/aris_agent.py
```

---

## Support

- API docs: https://agentoptima.ai/docs
- Code location: `/root/.openclaw/workspace/AgentOptima/`
- Issues: File on GitHub or ask in Telegram

---

**Next Step**: Add tracker to Aris and run for 24 hours → Review recommendations → Decide on full MVP (Option A) or scale up (custom analytics/models).

⚡
