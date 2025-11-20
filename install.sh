#!/bin/bash
set -euo pipefail
echo "🚀 Installing Gensyn Node Agent..."

# ---- Config (edit here if installing manually) ----
REPO_RAW_BASE="https://raw.githubusercontent.com/Kaushalvasoya2001/gensyn-node-agent/main"
AGENT_PY="agent.py"
LOG_AGENT_PY="log_watcher.py"
INSTALL_DIR="/opt/gensyn-agent"
VENV_DIR="$INSTALL_DIR/.venv"
SERVICE_NAME="gensyn-agent"
UVICORN_CMD="$VENV_DIR/bin/uvicorn"
# Optional envs (set in systemd below). If you want token protection, set a value here or via systemd edit:
# export GENSYN_API_TOKEN="some-secret"
# export GENSYN_ANALYTICS_SERVER="https://analytics.example.com/api/log-event"

# ---- 1) Install system packages (idempotent) ----
apt update -y || true
DEPS="python3 python3-venv python3-pip curl"
apt install -y $DEPS

# ---- 2) Create install dir and download agent files ----
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "Downloading agent files from repository..."
curl -fsSL "$REPO_RAW_BASE/$AGENT_PY" -o agent.py || { echo "Failed to download agent.py"; exit 1; }
# try to download the watcher; it is optional (the agent will still run without it)
curl -fsSL "$REPO_RAW_BASE/$LOG_AGENT_PY" -o log_watcher.py || echo "log_watcher.py not found in repo (optional) - continuing"

# ---- 3) Create venv and install python deps inside it ----
python3 -m venv "$VENV_DIR"
# ensure pip is available
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install fastapi "uvicorn[standard]" psutil pynvml requests || true

# ---- 4) Create log files and set permissions ----
mkdir -p /var/log
touch /var/log/gensyn-agent.log /var/log/gensyn-agent-error.log
chown root:root "$INSTALL_DIR" -R
chmod 755 "$INSTALL_DIR"
chmod 644 /var/log/gensyn-agent*.log

# ---- 5) Create systemd service for the API agent ----
cat <<EOF >/etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Gensyn Node Agent
After=network.target

[Service]
# Optional: set environment values here or override via 'systemctl edit' later
# Environment="GENSYN_API_TOKEN="
# Environment="GENSYN_ANALYTICS_SERVER="
WorkingDirectory=$INSTALL_DIR
ExecStart=$UVICORN_CMD agent:app --host 0.0.0.0 --port 9105
Restart=always
RestartSec=3
StandardOutput=append:/var/log/gensyn-agent.log
StandardError=append:/var/log/gensyn-agent-error.log
User=root

[Install]
WantedBy=multi-user.target
EOF

# ---- 6) (Optional) Create systemd service for log watcher if log_watcher.py exists ----
if [ -f "$INSTALL_DIR/$LOG_AGENT_PY" ]; then
  cat <<'EOF' >/etc/systemd/system/gensyn-log-watcher.service
[Unit]
Description=Gensyn Log Watcher
After=network.target

[Service]
WorkingDirectory=/opt/gensyn-agent
ExecStart=/usr/bin/python3 /opt/gensyn-agent/log_watcher.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/gensyn-agent.log
StandardError=append:/var/log/gensyn-agent-error.log
User=root

[Install]
WantedBy=multi-user.target
EOF
  echo "Created gensyn-log-watcher.service (disabled by default). It will be enabled below."
fi

# ---- 7) Enable & start services ----
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME" || { echo "Failed to start $SERVICE_NAME - check 'journalctl -u $SERVICE_NAME -n 200'"; exit 1; }

if systemctl list-unit-files | grep -q gensyn-log-watcher.service; then
  systemctl enable --now gensyn-log-watcher.service || echo "Log watcher failed to start (check journalctl)."
fi

# ---- 8) Open firewall port if ufw exists (non-fatal if ufw not installed) ----
if command -v ufw >/dev/null 2>&1; then
  ufw allow 9105/tcp || true
fi

echo "🎯 DONE — Gensyn Node Agent installed and running (port 9105)."
echo "Test endpoints:"
echo " - Basic metrics: curl http://<YOUR_IP>:9105/metrics"
echo " - Detailed metrics (if logs found or watcher running): curl http://<YOUR_IP>:9105/detailed-metrics"
echo ""
echo "If you want token protection for /detailed-metrics:"
echo "  sudo systemctl edit $SERVICE_NAME"
echo "  # add in the [Service] section e.g.:"
echo "  # Environment=\"GENSYN_API_TOKEN=your-secret-token\""
echo "  sudo systemctl daemon-reload && sudo systemctl restart $SERVICE_NAME"
