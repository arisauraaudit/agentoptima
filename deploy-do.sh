#!/bin/bash
# AgentOptima - One-Click DigitalOcean Deploy
cd /root/.openclaw/workspace/AgentOptima

# Install dependencies
pip install fastapi uvicorn pydantic httpx requests --user 2>/dev/null

# Create systemd service
sudo tee /etc/systemd/system/agentoptima.service > /dev/null << EOF
[Unit]
Description=AgentOptima API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/.openclaw/workspace/AgentOptima
ExecStart=/root/.local/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable agentoptima
sudo systemctl start agentoptima

echo "=== AgentOptima deployed ==="
echo "API running at: http://localhost:8000"
echo "Test: curl http://localhost:8000/health"
