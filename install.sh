#!/bin/bash
echo "🚀 Installing Gensyn Node Agent..."

set -e

# Install dependencies
apt update -y
apt install -y python3 python3-pip curl

# Create agent dir
mkdir -p /opt/gensyn-agent
cd /opt/gensyn-agent

# Download latest agent from GitHub
curl -sO https://raw.githubusercontent.com/Kaushalvasoya2001/gensyn-node-agent/main/agent.py

# Install Python packages
pip3 install fastapi uvicorn psutil pynvml --ignore-installed

# Create systemd service
cat <<EOF >/etc/systemd/system/gensyn-agent.service
[Unit]
Description=Gensyn Node Agent
After=network.target

[Service]
ExecStart=/usr/bin/uvicorn agent:app --host 0.0.0.0 --port 9105
WorkingDirectory=/opt/gensyn-agent
Restart=always
StandardOutput=append:/var/log/gensyn-agent.log
StandardError=append:/var/log/gensyn-agent-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gensyn-agent
systemctl restart gensyn-agent

ufw allow 9105/tcp || true
echo "🎯 DONE — Agent running!"
echo "Check: curl http://YOUR_IP:9105/metrics"

