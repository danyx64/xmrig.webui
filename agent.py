import glob
import os
import platform
from pathlib import Path
from flask import Flask, jsonify

app = Flask(__name__)
HOST_SYS = Path(os.environ.get("HOST_SYS", "/host/sys"))
if not HOST_SYS.exists():
    HOST_SYS = Path("/sys")

def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""

def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
            if line.lower().startswith("model name") or line.lower().startswith("hardware"):
                return line.split(":",1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()

def temperature_readings():
    readings=[]
    for hwmon in glob.glob(str(HOST_SYS / "class" / "hwmon" / "hwmon*")):
        p=Path(hwmon); name=read_text(p/"name") or p.name
        for f in p.glob("temp*_input"):
            prefix=f.stem.replace("_input","")
            label=read_text(p/f"{prefix}_label") or prefix
            try: value=float(read_text(f))/1000.0
            except (TypeError,ValueError): continue
            if -20 <= value <= 150:
                readings.append({"sensor":name,"label":label,"temperature_c":round(value,1)})
    for zone in glob.glob(str(HOST_SYS / "class" / "thermal" / "thermal_zone*")):
        p=Path(zone)
        try: value=float(read_text(p/"temp"))/1000.0
        except (TypeError,ValueError): continue
        if -20 <= value <= 150:
            readings.append({"sensor":"thermal","label":read_text(p/"type") or p.name,"temperature_c":round(value,1)})
    return readings

def host_uptime():
    try: return int(float(read_text("/proc/uptime").split()[0]))
    except Exception: return None

@app.get("/healthz")
def healthz():
    return jsonify({"ok":True})

@app.get("/v1/metrics")
def metrics():
    readings=temperature_readings()
    temps=[x["temperature_c"] for x in readings]
    try: load1=os.getloadavg()[0]
    except Exception: load1=None
    return jsonify({"temperature_c":max(temps) if temps else None,"temperatures":readings,"load1":load1,"cpu_count":os.cpu_count(),"cpu_model":cpu_model(),"uptime":host_uptime()})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("AGENT_PORT","18089")),threaded=True)
