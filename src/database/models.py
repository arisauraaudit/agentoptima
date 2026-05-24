# AgentOptima Database Models (SQLAlchemy)
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Agent(Base):
    __tablename__ = 'agents'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(String, unique=True, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    tier = Column(String, default='free')  # free, pro, enterprise
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime)
    
    performance_logs = relationship("PerformanceEvent", back_populates="agent")

class PerformanceEvent(Base):
    __tablename__ = 'performance_events'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(String, ForeignKey('agents.agent_id'), nullable=False)
    task_type = Column(String, nullable=False)
    model_used = Column(String, nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    cost_usd = Column(Float, nullable=False)
    success = Column(Boolean, nullable=False)
    quality_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    agent = relationship("Agent", back_populates="performance_logs")
    
    __table_args__ = (
        Index('ix_performance_task_model', 'task_type', 'model_used'),
    )

class ResearchAlert(Base):
    __tablename__ = 'research_alerts'
    
    id = Column(Integer, primary_key=True)
    paper_url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    categories = Column(JSON, default=list)
    implications = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

class AgentRecommendation(Base):
    __tablename__ = 'agent_recommendations'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(String, ForeignKey('agents.agent_id'), nullable=False)
    task_type = Column(String, nullable=False)
    recommendation_type = Column(String, nullable=False)
    recommendation_json = Column(JSON, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
