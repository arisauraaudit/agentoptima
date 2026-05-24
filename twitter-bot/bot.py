#!/usr/bin/env python3
"""
AgentOptima Twitter Bot
- Posts daily model rankings
- Tweets breaking news (outages, price changes)
- Shares "Model of the Day"
- Links to agentoptima.ai
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List
from twitter import TwitterAPI, TwitterError

# Configuration
API_BASE_URL = "https://agentoptima.ai/api"
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

class AgentOptimaBot:
    def __init__(self):
        self.api = TwitterAPI(
            TWITTER_API_KEY,
            TWITTER_API_SECRET,
            TWITTER_ACCESS_TOKEN,
            TWITTER_ACCESS_SECRET
        )
    
    def get_rankings(self) -> Dict:
        """Fetch current rankings from API"""
        response = requests.get(f"{API_BASE_URL}/models/rankings", timeout=10)
        if response.status_code == 200:
            return response.json()
        return {}
    
    def get_daily_summary(self) -> str:
        """Generate daily summary tweet"""
        rankings = self.get_rankings()
        
        top_model = rankings.get('top_models', [{}])[0]
        total_tasks = rankings.get('total_tasks', 0)
        cost_saved = rankings.get('cost_saved', 0)
        
        tweet = f"""🤖 Daily AgentOptima Summary ({datetime.now().strftime('%Y-%m-%d')})

🥇 Top Model: {top_model.get('model', 'TBD')}
📊 Tasks Tracked: {total_tasks:,}
💰 Cost Saved: ${cost_saved:,.2f}

Rankings updated every 15 minutes!

🔗 agentoptima.ai #AI #MachineLearning #LLM
"""
        return tweet.strip()
    
    def tweet_daily_summary(self):
        """Post daily rankings summary"""
        try:
            tweet = self.get_daily_summary()
            response = self.api.request('statuses/update', {'status': tweet})
            print(f"✅ Posted: {tweet[:50]}...")
            return True
        except TwitterError as e:
            print(f"❌ Twitter error: {e}")
            return False
    
    def tweet_model_news(self, model: str, news_type: str, details: str):
        """Post news about model changes"""
        tweet = f"""🚨 Model Update: {model}

{news_type}: {details}

Stay informed with real-time agent data!
🔗 agentoptima.ai #AI #LLM"""
        
        try:
            response = self.api.request('statuses/update', {'status': tweet})
            print(f"✅ Posted news: {model}")
            return True
        except TwitterError as e:
            print(f"❌ Twitter error: {e}")
            return False
    
    def run(self):
        """Main bot loop"""
        print("🤖 AgentOptima Twitter Bot started")
        
        # Get daily summary
        success = self.tweet_daily_summary()
        
        if success:
            print("✅ Bot ran successfully")
        else:
            print("⚠️  Bot completed with errors")

if __name__ == "__main__":
    os.makedirs("/var/log/agentoptima", exist_ok=True)
    
    bot = AgentOptimaBot()
    bot.run()
