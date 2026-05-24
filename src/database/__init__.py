# AgentOptima Database Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://agentoptima:CHANGE_ME@localhost:5432/agentoptima")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
