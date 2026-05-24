#!/bin/bash
# AgentOptima API Start Script
cd /app/src
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
