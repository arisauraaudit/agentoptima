#!/usr/bin/env python3
"""
Aris Beta Agent Integration
AgentOptima tracker for Aris task logging and recommendations
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Configuration
API_BASE_URL = "https://agentoptima.ai/api/v1"  # Updated to match endpoint structure

class ArisTracker:
    """Integrates AgentOptima API with Aris task execution"""
    
    def __init__(self, model_name="claude-3.5-sonnet", base_url="https://agentoptima.ai/api/v1"):
        self.api_url = base_url
        self.model_name = model_name
        self.last_recommendations = None
    
    def track_task(self, task_type, task_description, duration_seconds=None, 
                   cost_cents=None, success=None, notes=None):
        """Log an Aris task to AgentOptima"""
        task_id = str(uuid.uuid4())[:8]
        
        payload = {
            "task_id": task_id,
            "task_type": task_type,
            "task_description": task_description,
            "model": self.model_name,
            "duration_seconds": duration_seconds,
            "cost_cents": cost_cents,
            "success": success,
            "notes": notes
        }
        
        try:
            response = requests.post(f"{self.api_url}/track", json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Task {task_id} logged to AgentOptima")
                return {"status": "success", "task_id": task_id}
            else:
                print(f"❌ Failed to log task: {response.status_code}")
                return {"status": "error", "code": response.status_code}
        except Exception as e:
            print(f"❌ Error logging task: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_recommendations(self):
        """Fetch performance recommendations from AgentOptima"""
        try:
            if self.last_recommendations:
                return self.last_recommendations
            
            response = requests.get(f"{self.api_url}/recommendations", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.last_recommendations = data
                print(f"💡 Recommendations loaded: {data['summary']}")
                return data
            else:
                print(f"❌ Failed to fetch recommendations: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error fetching recommendations: {e}")
            return {}
    
    def before_task(self, task_type, description):
        """Called before executing a task"""
        print(f"🚀 Starting task: {description}")
        return {"start_time": time.time(), "task_type": task_type}
    
    def after_task(self, context, success=True, notes=None):
        """Called after executing a task"""
        duration = int(time.time() - context["start_time"])
        
        # Log to AgentOptima
        self.track_task(
            task_type=context["task_type"],
            task_description=context.get("description", "unknown"),
            duration_seconds=duration,
            success=success,
            notes=notes
        )

# Example usage:
if __name__ == "__main__":
    tracker = ArisTracker()
    
    # Track a sample task
    context = tracker.before_task("deployment", "Test deployment workflow")
    time.sleep(2)  # Simulate work
    tracker.after_task(context, success=True, notes="Test completed")
    
    # Get recommendations
    recs = tracker.get_recommendations()
    print(json.dumps(recs, indent=2))
