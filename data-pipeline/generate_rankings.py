#!/usr/bin/env python3
"""
AgentOptima Data Pipeline
- Generates weekly rankings.json
- Publishes to GitHub
- Used by website and Twitter bot
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, List

# Configuration
API_BASE_URL = "https://agentoptima.ai/api"
GITHUB_REPO = "https://github.com/arisauraaudit/agentoptima-data"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Get from Railway env vars

def fetch_model_data() -> List[Dict]:
    """Fetch model performance data from API"""
    # Placeholder - will integrate with actual API once built
    models = [
        {
            "model": "o3-pro",
            "category": "coding",
            "success_rate": 0.98,
            "avg_duration": 2.1,
            "cost_per_1k": 0.75,
            "tasks_logged": 1523,
            "rating": 5.0
        },
        {
            "model": "claude-3.7-sonnet",
            "category": "research",
            "success_rate": 0.97,
            "avg_duration": 1.8,
            "cost_per_1k": 0.60,
            "tasks_logged": 2341,
            "rating": 5.0
        },
        {
            "model": "gpt-4o",
            "category": "writing",
            "success_rate": 0.95,
            "avg_duration": 1.2,
            "cost_per_1k": 0.80,
            "tasks_logged": 3421,
            "rating": 4.5
        },
        {
            "model": "llama-3.3-70b",
            "category": "cost_efficiency",
            "success_rate": 0.92,
            "avg_duration": 1.9,
            "cost_per_1k": 0.15,
            "tasks_logged": 892,
            "rating": 4.5
        },
        {
            "model": "qwen-2.5-max",
            "category": "general",
            "success_rate": 0.94,
            "avg_duration": 2.3,
            "cost_per_1k": 0.30,
            "tasks_logged": 1654,
            "rating": 4.5
        }
    ]
    return models

def calculate_rankings(models: List[Dict]) -> Dict:
    """Calculate rankings by use case category"""
    rankings = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_models": len(models),
        "total_tasks_tracked": sum(m.get("tasks_logged", 0) for m in models),
        "top_models_by_category": {},
        "best_value_models": [],
        "fastest_models": [],
        "highest_success_models": []
    }
    
    # Group by category
    categories = {}
    for model in models:
        cat = model.get("category", "general")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(model)
    
    # Find top model per category
    for category, category_models in categories.items():
        sorted_models = sorted(category_models, key=lambda x: x.get("rating", 0), reverse=True)
        if sorted_models:
            rankings["top_models_by_category"][category] = sorted_models[0]["model"]
    
    # Best value (high rating, low cost)
    value_models = sorted(
        models,
        key=lambda x: x.get("rating", 0) / (x.get("cost_per_1k", 1) or 1),
        reverse=True
    )[:3]
    rankings["best_value_models"] = [m["model"] for m in value_models]
    
    # Fastest responses
    fast_models = sorted(
        models,
        key=lambda x: x.get("avg_duration", float('inf'))
    )[:3]
    rankings["fastest_models"] = [m["model"] for m in fast_models]
    
    # Highest success rates
    success_models = sorted(
        models,
        key=lambda x: x.get("success_rate", 0),
        reverse=True
    )[:3]
    rankings["highest_success_models"] = [m["model"] for m in success_models]
    
    return rankings

def generate_rankings_json():
    """Generate full rankings.json"""
    models = fetch_model_data()
    rankings = calculate_rankings(models)
    
    data = {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "models": models,
        "rankings": rankings
    }
    
    return data

def publish_to_github(data: Dict):
    """Publish rankings to GitHub (placeholder)"""
    # This would use GitHub API to push to agentoptima-data repo
    # For now, just save to local file
    output_path = "/root/.openclaw/workspace/AgentOptima/rankings.json"
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Rankings saved to: {output_path}")
    return output_path

if __name__ == "__main__":
    print("🤖 AgentOptima Data Pipeline")
    print("=" * 50)
    
    data = generate_rankings_json()
    output_path = publish_to_github(data)
    
    print(f"\n📊 Summary:")
    print(f"  - Models tracked: {data['rankings']['total_models']}")
    print(f"  - Total tasks: {data['rankings']['total_tasks_tracked']:,}")
    print(f"  - Best value: {', '.join(data['rankings']['best_value_models'])}")
    print(f"  - Fastest: {', '.join(data['rankings']['fastest_models'])}")
    print(f"\n✅ Pipeline complete!")
