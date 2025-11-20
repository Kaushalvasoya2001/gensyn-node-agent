#!/usr/bin/env python3
# agent.py — merged metrics + detailed endpoint (use as /opt/gensyn-agent/agent.py)
import time
import os
import json
import glob
import re
from typing import Any, Dict
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
import psutil

# optional token support
REQUIRE_TOKEN = os.environ.get("GENSYN_API_TOKEN")

app = FastAPI(title="Gensyn Node Agent")

START = time.time()

def gpu_data():
    try:
        import pynvml
        pynvml.nvmlInit()
        cnt = pynvml.nvmlDeviceGetCount()
        out = []
        for i in range(cnt):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            out.append({
                "name": pynvml.nvmlDeviceGetName(h).decode() if hasattr(pynvml.nvmlDeviceGetName(h), "decode") else str(pynvml.nvmlDeviceGetName(h)),
                "util": int(util.gpu),
                "used_gb": round(mem.used/1e9,2),
                "total_gb": round(mem.total/1e9,2)
            })
        return {"available": True, "gpus": out}
    except Exception:
        return {"available": False}

@app.get("/metrics")
def metrics():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    return {
        "uptime_sec": int(time.time() - START),
        "cpu": round(cpu,1),
        "ram_used_gb": round(ram.used/1e9,2),
        "ram_total_gb": round(ram.total/1e9,2),
        "gpu": gpu_data()
    }

# Attempt 1: ask local sidecar HTTP port (if present)
def fetch_sidecar():
    import requests
    try:
        r = requests.get("http://127.0.0.1:9106/watch-metrics", timeout=1.2)
        if r.ok:
            j = r.json()
            # expecting { "ok": True, "data": { ... } }
            if isinstance(j, dict) and j.get("ok"):
                return j.get("data")
    except Exception:
        pass
    return None

# Attempt 2: read JSON written by the log watcher sidecar
def read_sidecar_file():
    fn = "/opt/gensyn-agent/detailed.json"
    try:
        if os.path.exists(fn):
            with open(fn, "r") as fh:
                return json.load(fh)
    except Exception:
        pass
    return None

@app.get("/detailed-metrics")
async def detailed(request: Request, require_token: str|None = Query(None)):
    # token check (use require_token query for external calls)
    if REQUIRE_TOKEN:
        token_q = require_token or request.query_params.get("token") or request.query_params.get("require_token")
        header = request.headers.get("x-api-token") or request.headers.get("authorization")
        if token_q != REQUIRE_TOKEN and header != REQUIRE_TOKEN:
            return JSONResponse({"ok": False, "error": "invalid token"}, status_code=401)

    # base metrics
    base = metrics()

    # try local sidecar HTTP first (fast)
    side = fetch_sidecar()
    if side and isinstance(side, dict):
        # flatten: put side (detailed fields) into the top-level data object
        merged = base.copy()
        merged.update(side)
        return JSONResponse({"ok": True, "data": merged})

    # try sidecar JSON file
    sfile = read_sidecar_file()
    if sfile and isinstance(sfile, dict):
        merged = base.copy()
        merged.update(sfile)
        return JSONResponse({"ok": True, "data": merged})

    # fallback — quick log scan (non-blocking, minimal)
    detailed = {
        "current_round": None,
        "latest_start_round": None,
        "map_percent": None,
        "examples_s_latest": None,
        "examples_s_avg": None,
        "sample_count_examples_s": 0,
        "proofs_ok": 0,
        "proofs_fail": 0,
        "rounds_completed": 0
    }

    LOG_CANDIDATES = [
        "/home/user/rl-swarm/logs",
        "/home/ubuntu/rl-swarm/logs",
        "/var/log/rl-swarm",
        "/opt/rl-swarm/logs",
        "/root/rl-swarm/logs"
    ]

    RE_JOIN = re.compile(r"Joining round[:\s]+(\d+)", re.I)
    RE_START = re.compile(r"Starting round[:\s]+(\d+)", re.I)
    RE_EXS = re.compile(r"(\d+(?:\.\d+)?)\s*examples\/s", re.I)
    RE_OK = re.compile(r"(proof accepted|proof ok|Proof accepted|Proof ok|proof result: True)", re.I)
    RE_FAIL = re.compile(r"(proof failed|Proof failed|job failed|error|proof result: False)", re.I)

    for p in LOG_CANDIDATES:
        try:
            files = glob.glob(os.path.join(p, "*.log"))
        except Exception:
            files = []
        files = sorted(files, key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
        for f in files[:6]:
            try:
                with open(f, "rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    size = fh.tell()
                    read_from = max(0, size - 64_000)  # read last 64KB
                    fh.seek(read_from)
                    data = fh.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
            for line in data.splitlines():
                m = RE_JOIN.search(line)
                if m:
                    detailed["current_round"] = int(m.group(1))
                m = RE_START.search(line)
                if m and not detailed["latest_start_round"]:
                    detailed["latest_start_round"] = int(m.group(1))
                m = RE_EXS.search(line)
                if m:
                    try:
                        val = float(m.group(1))
                        detailed["examples_s_latest"] = val
                        if detailed["examples_s_avg"] is None:
                            detailed["examples_s_avg"] = val
                        detailed["sample_count_examples_s"] += 1
                    except Exception:
                        pass
                if RE_OK.search(line):
                    detailed["proofs_ok"] += 1
                    detailed["rounds_completed"] += 1
                if RE_FAIL.search(line):
                    detailed["proofs_fail"] += 1

    merged = base.copy()
    merged.update(detailed)
    return JSONResponse({"ok": True, "data": merged})
