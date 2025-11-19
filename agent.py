from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import psutil, time, os, re
from typing import Optional, Dict, Any, List
from pathlib import Path

app = FastAPI()
START = time.time()

# GPU support (optional)
try:
    import pynvml
    pynvml.nvmlInit()
    GPU_OK = True
except Exception:
    GPU_OK = False

# regexes based on your logs
RE_JOIN   = re.compile(r"Joining round[:\s]+(\d+)", re.I)
RE_START  = re.compile(r"Starting round[:\s]+(\d+)\/\d+", re.I)
RE_MAP    = re.compile(r"Map:\s*(\d+)%", re.I)
RE_EXS    = re.compile(r"(\d+\.\d+)\s*examples\/s", re.I)
RE_OK     = re.compile(r"proof accepted|job completed|already finished round", re.I)
RE_FAIL   = re.compile(r"proof failed|job failed|error", re.I)

# Log search candidates - adjust if your node uses a different path
LOG_CANDIDATES = [
    Path("/home/user/rl-swarm/logs"),
    Path("/home/ubuntu/rl-swarm/logs"),
    Path("/root/rl-swarm/logs"),
    Path("/opt/rl-swarm/logs"),
    Path("/var/log/rl-swarm"),
    Path("/var/log/gensyn"),
    Path.cwd()
]

def gpu_data():
    if not GPU_OK:
        return {"available": False}
    out = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h).decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            out.append({
                "name": name,
                "util": int(util.gpu),
                "used_gb": round(mem.used / 1e9, 2),
                "total_gb": round(mem.total / 1e9, 2)
            })
        return {"available": True, "gpus": out}
    except Exception:
        return {"available": False}

def find_log_files(limit=6) -> List[Path]:
    found = []
    for base in LOG_CANDIDATES:
        try:
            if base.exists() and base.is_dir():
                for p in sorted(base.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
                    found.append(p)
                    if len(found) >= limit:
                        return found
        except Exception:
            continue
    # fallback: quick /home scan for rl-swarm/logs
    if Path("/home").exists():
        for home in Path("/home").iterdir():
            p = home / "rl-swarm" / "logs"
            if p.exists() and p.is_dir():
                for f in sorted(p.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
                    found.append(f)
                    if len(found) >= limit:
                        return found
    return found

def tail_file_bytes(path: Path, nbytes: int = 20000) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            to_read = min(size, nbytes)
            fh.seek(size - to_read)
            data = fh.read().decode(errors="ignore")
            return data
    except Exception:
        return ""

def parse_log_text(text: str) -> Dict[str, Any]:
    metrics = {
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

    exs_vals = []
    lines = text.splitlines()

    for line in lines:
        if not line:
            continue
        if m := RE_JOIN.search(line):
            try:
                metrics["current_round"] = int(m.group(1))
            except:
                pass
        if m := RE_START.search(line):
            try:
                metrics["latest_start_round"] = int(m.group(1))
            except:
                pass
        if m := RE_MAP.search(line):
            try:
                metrics["map_percent"] = int(m.group(1))
            except:
                pass
        if m := RE_EXS.search(line):
            try:
                val = float(m.group(1))
                exs_vals.append(val)
            except:
                pass
        if RE_OK.search(line):
            metrics["proofs_ok"] += 1
            metrics["rounds_completed"] += 1
        if RE_FAIL.search(line):
            metrics["proofs_fail"] += 1

    if exs_vals:
        metrics["examples_s_latest"] = exs_vals[-1]
        metrics["examples_s_avg"] = sum(exs_vals) / len(exs_vals)
        metrics["sample_count_examples_s"] = len(exs_vals)

    return metrics

def metrics_basic() -> Dict[str, Any]:
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.2)
    return {
        "uptime_sec": int(time.time() - START),
        "cpu": cpu,
        "ram_used_gb": round(ram.used / 1e9, 2),
        "ram_total_gb": round(ram.total / 1e9, 2),
        "gpu": gpu_data()
    }

@app.get("/metrics")
def main_metrics():
    return metrics_basic()

@app.get("/detailed-metrics")
def detailed_metrics(lines: Optional[int] = Query(20000, description="bytes to tail from recent logs"),
                     require_token: Optional[str] = Query(None, description="optional token if you enabled API token")):
    """
    Aggregate parsed node metrics from recent log files and return them together with system CPU/RAM/GPU.
    """
    # optional simple token protection (set env GENSYN_API_TOKEN in systemd if you want)
    api_token = os.environ.get("GENSYN_API_TOKEN", "").strip()
    if api_token:
        if require_token != api_token:
            raise HTTPException(status_code=401, detail="unauthorized")

    files = find_log_files(limit=6)
    if not files:
        return JSONResponse({"ok": False, "error": "no log files found"}, status_code=404)

    combined = ""
    for f in files:
        combined += tail_file_bytes(f, nbytes=lines) + "\n"

    parsed = parse_log_text(combined)
    sys = metrics_basic()
    parsed.update(sys)
    parsed["ok"] = True
    return parsed
