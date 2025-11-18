from fastapi import FastAPI
import psutil, time, json

try:
    import pynvml
    pynvml.nvmlInit()
    GPU_OK = True
except:
    GPU_OK = False

app = FastAPI()
START = time.time()

def gpu_data():
    if not GPU_OK:
        return {"available": False}

    import pynvml
    count = pynvml.nvmlDeviceGetCount()
    arr = []
    for i in range(count):
        h = pynvml.nvmlDeviceGetHandleByIndex(i)
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        util = pynvml.nvmlDeviceGetUtilizationRates(h)
        arr.append({
            "name": pynvml.nvmlDeviceGetName(h).decode(),
            "util": util.gpu,
            "used_gb": round(mem.used / 1e9, 2),
            "total_gb": round(mem.total / 1e9, 2)
        })
    return {"available": True, "gpus": arr}

@app.get("/metrics")
def main():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent()

    return {
        "uptime_sec": int(time.time() - START),
        "cpu": cpu,
        "ram_used_gb": round(ram.used / 1e9, 2),
        "ram_total_gb": round(ram.total / 1e9, 2),
        "gpu": gpu_data()
    }
