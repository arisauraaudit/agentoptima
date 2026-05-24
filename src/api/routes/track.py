# AgentOptima API - Track Performance
import sys
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import PerformanceEvent
from database import get_db

router = APIRouter()

class PerformanceLog(BaseModel):
    agent_id: str
    task_type: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    success: bool
    quality_score: float = None

@router.post("/track")
async def track_performance(log: PerformanceLog, db = Depends(get_db)):
    """Log agent performance data"""
    
    event = PerformanceEvent(
        agent_id=log.agent_id,
        task_type=log.task_type,
        model_used=log.model_used,
        input_tokens=log.input_tokens,
        output_tokens=log.output_tokens,
        latency_ms=log.latency_ms,
        cost_usd=log.cost_usd,
        success=log.success,
        quality_score=log.quality_score
    )
    
    db.add(event)
    db.commit()
    db.refresh(event)
    
    logger.info(f"✅ Performance logged: {log.task_type} | {log.model_used} | {log.latency_ms}ms")
    
    return {
        "status": "ok",
        "event_id": str(event.id),
        "message": "Performance data recorded"
    }

@router.post("/track/batch")
async def track_batch(logs: list[PerformanceLog], db = Depends(get_db)):
    """Log multiple performance events at once"""
    
    events = []
    for log in logs:
        event = PerformanceEvent(
            agent_id=log.agent_id,
            task_type=log.task_type,
            model_used=log.model_used,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            latency_ms=log.latency_ms,
            cost_usd=log.cost_usd,
            success=log.success,
            quality_score=log.quality_score
        )
        events.append(event)
    
    db.add_all(events)
    db.commit()
    
    logger.info(f"✅ Batch logged: {len(logs)} events")
    
    return {
        "status": "ok",
        "count": len(logs),
        "message": f"{len(logs)} performance records added"
    }
