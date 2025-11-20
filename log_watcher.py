cat > /opt/gensyn-agent/log_watcher.py <<'PY'
#!/usr/bin/env python3
"""
log_watcher.py
Sidecar that tails rl-swarm logs and writes JSON summary to /opt/gensyn-agent/detailed.json
Non-invasive: only reads logs.
"""

import time
import json
import re
import os
from pathlib import Path
from collections import deque

# --- Config ---
LOG_DIRS = [
    "/home/user/rl-swarm/logs",
    "/home/ubuntu/rl-swarm/logs",
    "/var/log/rl-swarm",
    "/opt/rl-swarm/logs",
]
POLL_INTERVAL = 1.0
OUTPUT_FILE = "/opt/gensyn-agent/detailed.json"
SAMPLES_MAX = 200

# --- State ---
examples_samples = deque(maxlen=SAMPLES_MAX)
state = {
    "current_round": None,
    "latest_start_round": None,
    "map_percent": None,
    "examples_s_latest": None,
    "examples_s_avg": None,
    "sample_count_examples_s": 0,
    "proofs_ok": 0,
    "proofs_fail": 0,
    "rounds_completed": 0,
    "last_updated": int(time.time()),
    "files_tracked": []
}

# regexes (tune if needed)
RE_START = re.compile(r"Starting round[:\s]+(\d+)", re.I)
RE_JOIN = re.compile(r"Joining round[:\s]+(\d+)", re.I)
RE_MAP = re.compile(r"Map[:\s]+(\d+)\s*%", re.I)
RE_EXS = re.compile(r"(\d+(?:\.\d+)?)\s*examples\/s", re.I)
RE_OK = re.compile(r"(proof accepted|proof ok|proof result: True)", re.I)
RE_FAIL = re.compile(r"(proof failed|proof result: False|error|failed)", re.I)

def discover_log_files(limit=6):
    files = []
    for d in LOG_DIRS:
        try:
            p = Path(d)
            if p.is_dir():
                found = sorted(p.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
                for f in found:
                    files.append(f)
                    if len(files) >= limit:
                        return files
            elif p.is_file():
                files.append(p)
        except Exception:
            continue
    # fallback: search /home/*/rl-swarm/logs
    base = Path("/home")
    if base.exists():
        for u in base.iterdir():
            candidate = u / "rl-swarm" / "logs"
            if candidate.exists() and candidate.is_dir():
                for f in sorted(candidate.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
                    files.append(f)
                    if len(files) >= limit:
                        return files
    return files

def tail_file(path, last_pos):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size <= last_pos.get(path, 0):
                return "", size
            start = last_pos.get(path, 0)
            fh.seek(start)
            data = fh.read().decode(errors="ignore")
            return data, fh.tell()
    except Exception:
        return "", last_pos.get(path, 0)

def parse_lines(lines):
    changed = False
    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = RE_JOIN.search(line)
        if m:
            state["current_round"] = int(m.group(1))
            changed = True

        m = RE_START.search(line)
        if m:
            state["latest_start_round"] = int(m.group(1))
            changed = True

        m = RE_MAP.search(line)
        if m:
            state["map_percent"] = int(m.group(1))
            changed = True

        m = RE_EXS.search(line)
        if m:
            try:
                v = float(m.group(1))
                examples_samples.append(v)
                state["examples_s_latest"] = round(v, 2)
                if examples_samples:
                    state["examples_s_avg"] = round(sum(examples_samples) / len(examples_samples), 2)
                state["sample_count_examples_s"] = len(examples_samples)
                changed = True
            except:
                pass

        if RE_OK.search(line):
            state["proofs_ok"] += 1
            state["rounds_completed"] += 1
            changed = True

        if RE_FAIL.search(line):
            state["proofs_fail"] += 1
            changed = True

    if changed:
        state["last_updated"] = int(time.time())
    return changed

def write_output():
    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as fh:
            json.dump(state, fh, indent=None)
    except Exception:
        pass

def main_loop():
    last_pos = {}
    while True:
        files = discover_log_files(limit=8)
        state["files_tracked"] = [str(p) for p in files]
        for f in files:
            data, pos = tail_file(str(f), last_pos)
            last_pos[str(f)] = pos
            if data:
                lines = data.splitlines()
                parse_lines(lines)
        write_output()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main_loop()
PY
chmod 755 /opt/gensyn-agent/log_watcher.py
