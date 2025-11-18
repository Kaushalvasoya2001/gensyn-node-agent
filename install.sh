#!/bin/bash
echo "🚀 Installing Gensyn Node Agent..."

set -e

# Install system dependencies
apt update -y
apt install -y python3 python3-venv python3-pip curl

# Create agent directory
mkdir -p /opt/gensyn-agent
cd /opt/gensyn-agent

# Download latest agent code
curl -sO https://raw.githubusercontent.com/Kaushalvasoya2001/gensyn-node-agent/main/agent.py

# Create and use a virtual environment (avoids PEP 668)
python3 -m venv .venv
/opt/gensyn-agent/.venv/bin/pip install --upgrade pip
/opt/gensyn-agent/.venv/bin/pip install fastapi "uvicorn[standard]" psutil pynvml

# Create systemd service
cat <<EOF >/etc/systemd/system/gensyn-agent.service
[Unit]
Description=Gensyn Node Agent
After=network.target

[Service]
ExecStart=/opt/gensyn-agent/.venv/bin/uvicorn agent:app --host 0.0.0.0 --port 9105
WorkingDirectory=/opt/gensyn-agent
Restart=always
StandardOutput=append:/var/log/gensyn-agent.log
StandardError=append:/var/log/gensyn-agent-error.log
User=root

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable gensyn-agent
systemctl restart gensyn-agent

# Open firewall port if ufw exists
if command -v ufw >/dev/null 2>&1; then
  ufw allow 9105/tcp || true
fi

echo "🎯 DONE — Gensyn Node Agent is running."
echo "Test with: curl http://YOUR_SERVER_IP:9105/metrics"
