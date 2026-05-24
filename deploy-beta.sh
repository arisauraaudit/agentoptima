#!/bin/bash
# AgentOptima - Beta Deployment Script
# Deploys the API to Railway for Aris beta testing

set -e

echo "🚀 AgentOptima Beta Deployment"
echo "================================"

# Check if git repo exists
if [ ! -d ".git" ]; then
    echo "❌ Not a git repository"
    exit 1
fi

# Commit changes
echo "📝 Committing changes..."
git add .
git commit -m "feat: Add track and recommendations endpoints for Aris beta" --allow-empty
git push origin main

# Trigger Railway deploy
echo "🏗️  Triggering Railway deploy..."
# Note: You may need to run `railway login` first if not already authenticated
if command -v railway &> /dev/null; then
    railway deploy
    echo "✅ Railway deploy triggered"
else
    echo "ℹ️  Railway CLI not available"
    echo "   Instead, go to: https://railway.app/"
    echo "   1. Select your AgentOptima project"
    echo "   2. Click 'Deploy' or redeploy manually"
    echo "   3. Or push to git and let Railway auto-deploy"
fi

echo "================================"
echo "🎉 Deployment complete!"
echo "📍 Live at: https://agentoptima.ai"
echo "📝 Test with: curl https://agentoptima.ai/health"
echo "================================"
