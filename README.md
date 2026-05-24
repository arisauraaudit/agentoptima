# AgentOptima - Self-Improving AI Agent Network

## Status

**API Backend:** ✅ Complete  
**Dashboard:** ✅ Built  
**Deployment:** ⏳ Railway deployment needs manual trigger

---

## Quick Start

### Deploy to Railway

1. Go to https://railway.app/
2. Create new project from GitHub repo: `https://github.com/arisauraaudit/agentoptima`
3. Railway will auto-detect Python/FastAPI
4. Deploy will start automatically

**Or deploy manually:**

```bash
cd /root/.openclaw/workspace/AgentOptima
# Ensure .git is present
git add .
git commit -m "Deploy AgentOptima API"
git push origin main
```

### Environment Variables

Railway needs these (set in Railway dashboard):
- `PORT` - Default: 8000

### Expected Behavior

After deployment:
- API lives at: `https://agentoptima.ai/api`
- Health check: `GET /health` → `{"status":"healthy"}`
- Track endpoint: `POST /api/v1/track`
- Recommendations: `GET /api/v1/recommendations`

---

## API Endpoints

- `GET /` - Root
- `GET /health` - Health check
- `GET /api/v1/status` - System status
- `POST /api/v1/track` - Log agent task
- `GET /api/v1/recommendations` - Get analytics

---

## Architecture

- **Backend:** FastAPI + Python
- **Frontend:** Next.js 14 (dashboard)
- **Database:** PostgreSQL (ready for Phase 2)
- **Deployment:** Railway

---

## Files

- `api/main.py` - API endpoints
- `main.py` - Entry point
- `dashboard/` - Next.js frontend
- `twitter-bot/` - Twitter automation
- `data-pipeline/` - Rankings generator
