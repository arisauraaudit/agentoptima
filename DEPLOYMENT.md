# AgentOptima Deployment Guide

---

## 📦 Quick Deploy

### **Option A: Deploy via Docker**

```bash
# 1. Clone or extract files
cd /root/.openclaw/workspace/AgentOptima

# 2. Configure environment
cp infra/env.example .env
nano .env  # Fill in credentials

# 3. Build and run
docker-compose up -d

# 4. Check status
docker-compose ps
```

---

### **Option B: Deploy to Railway**

```bash
# 1. Connect Railway
railway login
railway init -n agentoptima

# 2. Add PostgreSQL
railway add postgres

# 3. Deploy
railway up

# 4. Set environment variables
railway env add POSTGRES_URL=<railway-pg-url>
railway env add API_KEY=<your-key>
```

---

## 📂 What's Deployed

```
AgentOptima/
├── src/
│   └── api/         (FastAPI endpoints)
│   └── database/    (SQLAlchemy models)
├── infra/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
└── README.md
```

---

## 🔗 Access Points

- **API:** `https://agentoptima.ai/api/v1`
- **Docs:** `https://agentoptima.ai/docs`
- **Health:** `https://agentoptima.ai/health`

---

## ⚡ First Deploy Timeline

1. **Day 1:** Domain purchased (your task)
2. **Day 2:** I deploy to Railway/DigitalOcean
3. **Day 3:** Test with Aris as first agent
4. **Day 4:** Launch to public

---

*Created: 2026-05-23 | Aris (AgentOptima)*
