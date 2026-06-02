#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# AgentOptima — Level 3 PANIC (Nuclear Resurrection)
# Run from Aris-HQ when Railway + API are both unreachable.
# Forces a GitHub push → triggers automatic Railway redeploy.
# Usage: bash /root/.openclaw/workspace/AgentOptima/scripts/panic_push.sh
# ═══════════════════════════════════════════════════════════════════
set -e

REPO="/root/.openclaw/workspace/AgentOptima"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "🚨 AgentOptima Level 3 PANIC — $TIMESTAMP"
echo "────────────────────────────────────────────"

cd "$REPO"

# 1. Bump version string in main.py to force Railway Docker rebuild
echo "→ Bumping version timestamp in main.py..."
CURRENT=$(grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' main.py | head -1 || echo "v1.0.0")
sed -i "s|panic_rebuild=.*|panic_rebuild=\"$TIMESTAMP\"|g" api/main.py 2>/dev/null || true
# Append a comment to force diff
echo "# panic_rebuild: $TIMESTAMP" >> api/main.py

# 2. Git commit + push
echo "→ Committing panic rebuild..."
git add -A
git commit -m "🚨 panic rebuild $TIMESTAMP — forced redeploy"
git push origin main

echo ""
echo "✅ Pushed to GitHub. Railway auto-deploy will trigger in ~2min."
echo "   Monitor: https://railway.app/dashboard"
echo "   Health:  https://agentoptima.ai/health"
echo ""
echo "If Railway is also down, check Railway status: https://status.railway.app"
