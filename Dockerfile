# AgentOptima Dockerfile - Railway compatible
FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Copy Next.js static export to /app/frontend
RUN if [ -d dashboard/out ]; then cp -r dashboard/out /app/frontend; fi

# Expose port (Railway will inject PORT env var)
EXPOSE 8000

# Start command - use uvicorn directly via main.py
# Main.py handles loading the app from api.main
CMD ["python", "main.py"]
