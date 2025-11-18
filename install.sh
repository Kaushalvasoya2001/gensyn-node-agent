#!/bin/bash
echo "[+] Installing Gensyn Node Agent"

# Install deps
apt update -y
apt install -y python3 python3-pip

# Download agent
mkdir -p /opt/gensyn-agent
cd /opt/gensyn-agent
curl -sO https://raw.githubusercontent.com/YOURNAME/gensyn-node-agent/main/agent.py

# Install python libs
pip3 install fastapi uvicorn psutil pynvml

# Create systemd service
cat <<EOF >/etc/systemd/system/gensyn-agent.service
[Unit]
Description=Gensyn Node Agent
After=network.target

[Service]
ExecStart=/usr/bin/uvicorn agent:app --host 0.0.0.0 --port 9105
WorkingDirectory=/opt/gensyn-agent
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gensyn-agent
systemctl restart gensyn-agent

ufw allow 9105/tcp || true

echo "[+] DONE!"
echo "Check:  curl http://YOUR_IP:9105/metrics"
