import time
import json
import re
import os

LOG_DIR = "/home/user/rl-swarm/logs"   # default path (your VPS used this)
OUTPUT_FILE = "/opt/gensyn-agent/detailed.json"

latest = {
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

round_times = []
examples_rates = []

def parse_line(line):
    """Parse one log line from rl-swarm."""
    global latest, examples_rates, round_times

    # Round start
    m = re.search(r"Starting round: (\d+)", line)
    if m:
        r = int(m.group(1))
        latest["current_round"] = r
        latest["latest_start_round"] = r
        return

    # Map %
    m = re.search(r"Map: (\d+)%", line)
    if m:
        latest["map_percent"] = int(m.group(1))
        return

    # Examples/s metric
    m = re.search(r"\[(\d+\.\d+) examples/s\]", line)
    if m:
        val = float(m.group(1))
        latest["examples_s_latest"] = val
        examples_rates.append(val)
        if len(examples_rates) > 20:
            examples_rates.pop(0)
        latest["examples_s_avg"] = round(sum(examples_rates) / len(examples_rates), 2)
        return

    # Proof success/fail
    if "proof result: True" in line or "proof ok" in line.lower():
        latest["proofs_ok"] += 1
        latest["rounds_completed"] += 1

    if "proof result: False" in line or "failed proof" in line.lower():
        latest["proofs_fail"] += 1
        latest["rounds_completed"] += 1


def write_output():
    with open(OUTPUT_FILE, "w") as f:
        json.dump(latest, f)


def follow_logs():
    """Attach to all log files in rl-swarm/logs and track updates."""
    print("🔄 Watching RL-SWARM logs...")

    while True:
        if not os.path.exists(LOG_DIR):
            time.sleep(2)
            continue

        files = [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.endswith(".log")]

        for file in files:
            try:
                with open(file, "r") as f:
                    for line in f:
                        parse_line(line)
            except:
                pass

        write_output()
        time.sleep(2)


if __name__ == "__main__":
    follow_logs()
