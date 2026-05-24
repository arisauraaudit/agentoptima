# AgentOptima API - Recommendations
import sys
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.engine import get_optimization_insights
from database.models import Agent
from database import get_db

router = APIRouter()

class RecommendationRequest(BaseModel):
    task_type: str

class RecommendationResponse(BaseModel):
    agent_id: str
    task_type: str
    insights: list

@router.get("/recommendations")
async def get_recommendations(
    agent_id: str,
    task_type: str = None,
    db = Depends(get_db)
):
    """Get optimization insights for an agent"""
    
    # Check if agent exists
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Get insights
    try:
        insights = get_optimization_insights(db, agent_id, task_type)
    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        raise HTTPException(status_code=500, detail="Analytics engine error")
    
    return {
        "agent_id": agent_id,
        "task_type": task_type or "all",
        "insights": insights,
        "generated_at": datetime.now().isoformat()
    }
