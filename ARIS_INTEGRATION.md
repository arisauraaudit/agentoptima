# 🚀 AgentOptima + Aris Integration

**Status:** ⏳ Waiting for API deployment (PORT fix pushed, auto-deploying)

---

## What You Need

1. **AgentOptima API** - Should be live in 2-3 minutes (fix pushed: PORT env var)
2. **Aris Orchestrator** - `/root/.aris/orchestrator.py`
3. **Tracker Module** - Ready at `/root/.openclaw/workspace/AgentOptima/integration/aris_agent.py`

---

## Step 1: Verify API is Live

Run this:
```bash
curl https://agentoptima.ai/health
```

Expected: `{"status":"healthy","version":"0.1.0"}`

If still 502 → wait 2 more minutes → retry. If after 5 min, check Railway dashboard.

---

## Step 2: Inject Tracker into Aris

### Option A: Automated (Recommended)

Run this script:
```bash
python3 /root/.openclaw/workspace/AgentOptima/integration/insert_into_orchestrator.py
```

This will:
- Add `from integration.aris_agent import ArisTracker` to your orchestrator
- Initialize `tracker = ArisTracker(model_name="...")`

### Option B: Manual

Add to top of `/root/.aris/orchestrator.py`:

```python
import sys
sys.path.insert(0, '/root/.openclaw/workspace/AgentOptima')
from integration.aris_agent import ArisTracker

# Initialize tracker with your main model
tracker = ArisTracker(model_name="claude-sonnet-4-6")
```

---

## Step 3: Track Tasks

Wrap your task execution like this:

```python
# START: Before task
context = tracker.before_task(
    task_type="research",
    description="Analyze market opportunity for {topic}"
)

# ... do your work ...

# END: After task
success = True  # or False if failed
notes = "Completed analysis in {duration} min"

tracker.after_task(
    context,
    success=success,
    notes=notes
)
```

### Where to Insert

In your orchestrator, find where tasks are executed and add tracking:

**Example: After task completion in a loop**
```python
for task in tasks:
    context = tracker.before_task(
        task_type=task['type'],
        description=task['description']
    )
    
    try:
        result = execute_task(task)
        success = True
    except Exception as e:
        result = None
        success = False
        notes = str(e)
    finally:
        tracker.after_task(
            context,
            success=success,
            notes=f"Completed: {task['description']}" if success else f"Failed: {e}"
        )
```

---

## Step 4: Daily Recommendations (Optional)

Add to your startup or morning routine:

```python
# Fetch recommendations
recs = tracker.get_recommendations()

if recs and recs.get('recommendations'):
    print("\n📊 AgentOptima Daily Recommendations:")
    print(f"   Summary: {recs['summary']}")
    for rec in recs['recommendations']:
        print(f"   [{rec['priority'].upper()}] {rec['message']}")
        if rec.get('action'):
            print(f"   → Action: {rec['action']}")
```

---

## Verification Checklist

After integration:

✅ **API is live** → `curl https://agentoptima.ai/health` returns health check  
✅ **Tracker installed** → `imported ArisTracker` in orchestrator  
✅ **Task tracking** → `tracker.before_task()` called before work  
✅ **Task logging** → `tracker.after_task()` called after completion  
✅ **Daily check-in** → `tracker.get_recommendations()` runs (optional)

---

## Expected Behavior

**First task logged:**
```
💾 Logged task: a1b2c3d4 (research)
✅ Task a1b2c3d4 logged to AgentOptima
💡 Recommendations loaded: No data logged yet...
```

**After 10+ tasks:**
```
💾 Logged task: b2c3d4e5 (deployment)
✅ Task b2c3d4e5 logged to AgentOptima
💡 Recommendations loaded: Analyzed 10 tasks | Success rate: 9/10 | Avg duration: 245s | Total cost: $12.50
```

**Recommendations example:**
```
[LOW] Task success rate (9/10) is healthy.
[MEDIUM] Average task duration (245s) is moderate. Consider batching for similar tasks.
[HIGH] Total cost: $12.50 - review expensive tasks for optimization opportunities.
```

---

## What Happens Next

| Time | Action | Status |
|------|--------|--------|
| **Now** | API should be live (PORT fix deployed) | ⏳ |
| **After integration** | Run Aris normally | ⏳ |
| **24h** | 24 hours of task data logged | ⏳ |
| **Day 2** | Review analytics & recommendations | ⏳ |
| **Day 2** | Decide: Full MVP (Option A) or scale (A+) | ⏳ |

---

## Troubleshooting

**Issue: API still 502 after 5 min**
- Solution: Check Railway dashboard at https://railway.app/
- Look for deployment logs
- Click "Redeploy" if needed

**Issue: Tracker fails to connect**
- Solution: Verify API is live first (`curl https://agentoptima.ai/health`)
- Check network/firewall can reach `agentoptima.ai`

**Issue: No recommendations showing**
- Solution: This is normal until you have 3+ tasks logged
- Recommendations generate based on task patterns

---

**Bottom line:** 
1. API fix pushed, auto-deploying (5-7 min total) 
2. Inject tracker into Aris (5 min)
3. Run Aris normally
4. Review data after 24h
5. Scale or build MVP

Ready when you are, partner. ⚡

— meta: model=claude-sonnet-4-6 • tier=4 • provider=anthropic • requested=user • escalation=true • delegation=false • apex=true • reason=Priority 1 (API fix) & Priority 2 (Aris integration) execution with partner time constraints
