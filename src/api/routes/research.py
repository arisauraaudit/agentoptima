# AgentOptima API - Research Alerts
import sys
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import ResearchAlert
from database import get_db

router = APIRouter()

class ResearchRequest(BaseModel):
    categories: list[str] = None

@router.get("/research")
async def get_research_alerts(
    categories: list[str] = None,
    limit: int = 10,
    db = Depends(get_db)
):
    """Get recent research alerts"""
    
    query = db.query(ResearchAlert).order_by(ResearchAlert.created_at.desc())
    
    if categories:
        query = query.filter(ResearchAlert.categories.any(category.lower() for category in categories))
    
    alerts = query.limit(limit).all()
    
    return {
        "alerts": [
            {
                "title": alert.title,
                "paper": alert.paper_url,
                "summary": alert.summary,
                "implications": alert.implications,
                "created_at": alert.created_at.isoformat()
            }
            for alert in alerts
        ],
        "total": len(alerts),
        "last_updated": datetime.now().isoformat()
    }
