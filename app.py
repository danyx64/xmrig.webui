import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

APP_NAME = "XMRig Unified WebUI"
DB_PATH = os.environ.get("DB_PATH", "/data/xmrig-webui.db")
REFRESH_SECONDS = max(10, int(os.environ.get("REFRESH_SECONDS", "30")))
HISTORY_DAYS = max(1, int(os.environ.get("HISTORY_DAYS", "7")))
HTTP_TIMEOUT = max(2, int(os.environ.get("HTTP_TIMEOUT", "6")))
DEFAULT_POOL_URL = os.environ.get("DEFAULT_POOL_URL", "https://supportxmr.com").strip()
DEFAULT_WALLET = os.environ.get("DEFAULT_WALLET", "").strip()
AUTO_ADD_LOCAL_MINER = os.environ.get("AUTO_ADD_LOCAL_MINER", "0") == "1"
DEFAULT_MINER_NAME = os.environ.get("DEFAULT_MINER_NAME", "ZimaOS").strip() or "ZimaOS"
DEFAULT_MINER_API = os.environ.get("DEFAULT_MINER_API", "http://host.docker.internal:18088").strip()
DEFAULT_AGENT_URL = os.environ.get("DEFAULT_AGENT_URL", "http://host.docker.internal:18089").strip()
USER_AGENT = "xmrig.webui/1.0 (+https://github.com/danyx64/xmrig.webui)"

app = Flask(__name__)
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
_sampler_started = False
_sampler_lock = threading.Lock()

def now_ts():
    return int(time.time())

def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS miners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            api_url TEXT NOT NULL,
            agent_url TEXT,
            token TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            miner_id INTEGER,
            hashrate REAL,
            temp_c REAL,
            online INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(miner_id) REFERENCES miners(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
        CREATE INDEX IF NOT EXISTS idx_samples_miner_ts ON samples(miner_id, ts);
        """)
        for key, value in {"pool_url": DEFAULT_POOL_URL, "wallet": DEFAULT_WALLET}.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",(key,value))
        if AUTO_ADD_LOCAL_MINER:
            count = conn.execute("SELECT COUNT(*) AS n FROM miners").fetchone()["n"]
            if count == 0:
                conn.execute(
                    "INSERT INTO miners(name,api_url,agent_url,token,enabled,created_at) VALUES (?,?,?,?,1,?)",
                    (DEFAULT_MINER_NAME, DEFAULT_MINER_API, DEFAULT_AGENT_URL, "", now_ts()),
                )
        conn.commit()

def get_settings():
    with closing(db()) as conn:
        rows = conn.execute("SELECT key,value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}

def set_settings(payload):
    with closing(db()) as conn:
        for key in ("pool_url","wallet"):
            if key in payload:
                conn.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(payload[key]).strip()))
        conn.commit()

def clean_url(value, default_scheme="http"):
    value=(value or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" not in value:
        value=f"{default_scheme}://{value}"
    parsed=urlparse(value)
    if parsed.scheme not in ("http","https") or not parsed.netloc:
        raise ValueError("URL non valido")
    return value

def pool_api_base(pool_url):
    value=clean_url(pool_url,"https")
    host=(urlparse(value).hostname or "").lower()
    if "supportxmr.com" in host:
        return "https://supportxmr.com/api"
    if "moneroocean.stream" in host or "moneroocean.com" in host:
        return "https://api.moneroocean.stream"
    return value if value.endswith("/api") else value + "/api"

def pool_kind(pool_url):
    host=(urlparse(clean_url(pool_url,"https")).hostname or "").lower()
    if "supportxmr.com" in host: return "SupportXMR"
    if "moneroocean" in host: return "MoneroOcean"
    return host or "Custom nodejs-pool"

def fetch_json(url, token=""):
    headers={}
    if token: headers["Authorization"]=f"Bearer {token}"
    r=session.get(url,headers=headers,timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()

def numeric(source, keys, default=0.0):
    if not isinstance(source,dict): return default
    for key in keys:
        try:
            if key in source and source[key] is not None:
                return float(source[key])
        except (TypeError,ValueError):
            pass
    return default

def first_text(source, keys, default=""):
    if not isinstance(source,dict): return default
    for key in keys:
        value=source.get(key)
        if value not in (None,""): return str(value)
    return default

def piconero_to_xmr(value):
    try: return float(value)/1_000_000_000_000.0
    except (TypeError,ValueError): return 0.0

def normalize_pool_workers(data):
    if not isinstance(data,dict): return []
    result=[]
    for name,raw in data.items():
        if name=="global": continue
        rows=raw if isinstance(raw,list) else [raw]
        row=next((x for x in reversed(rows) if isinstance(x,dict)),{})
        parent=raw if isinstance(raw,dict) else {}
        c=dict(parent); c.update(row)
        hraw=numeric(c,["hash","hs","hsh","rawHashrate"])
        hxmr=numeric(c,["hash2","hs2","hsh2","xmrHashrate"],hraw)
        result.append({"name":name,"hashrate":hxmr or hraw,"raw_hashrate":hraw,"algo":first_text(c,["lastShareAlgo","algo"]),"valid":numeric(c,["validShares","valid","shares","s"]),"invalid":numeric(c,["invalidShares","invalid","badShares"]),"last":numeric(c,["lastShare","lastHash","lts","last","ts","tme"])})
    return sorted(result,key=lambda x:x["hashrate"],reverse=True)

def fetch_pool_state(settings=None):
    settings=settings or get_settings()
    wallet=settings.get("wallet","").strip()
    pool_url=settings.get("pool_url","").strip()
    state={"configured":bool(wallet and pool_url),"pool":pool_kind(pool_url) if pool_url else "","pool_url":pool_url,"api_base":"","wallet":wallet,"online":False,"pending_xmr":0.0,"paid_xmr":0.0,"hashrate":0.0,"raw_hashrate":0.0,"valid_shares":0,"invalid_shares":0,"total_hashes":0,"workers":[],"chart":[],"payments":[],"error":None}
    if not state["configured"]: return state
    try:
        base=pool_api_base(pool_url); state["api_base"]=base
        stats=fetch_json(f"{base}/miner/{wallet}/stats")
        state.update({"online":True,"pending_xmr":piconero_to_xmr(stats.get("amtDue",0)),"paid_xmr":piconero_to_xmr(stats.get("amtPaid",0)),"hashrate":numeric(stats,["hash2","hash","hashrate"]),"raw_hashrate":numeric(stats,["hash","hashrate"]),"valid_shares":int(numeric(stats,["validShares","valid","shares"])),"invalid_shares":int(numeric(stats,["invalidShares","invalid","badShares"])),"total_hashes":int(numeric(stats,["totalHash","totalHashes","hashes"]))})
        try: state["workers"]=normalize_pool_workers(fetch_json(f"{base}/miner/{wallet}/stats/allWorkers"))
        except Exception: pass
        try:
            chart=fetch_json(f"{base}/miner/{wallet}/chart/hashrate")
            if isinstance(chart,list): state["chart"]=chart[-240:]
            elif isinstance(chart,dict):
                rows=chart.get("charts") or chart.get("stats") or []
                if isinstance(rows,list): state["chart"]=rows[-240:]
        except Exception: pass
        try:
            payments=fetch_json(f"{base}/miner/{wallet}/payments?page=0&limit=10")
            if isinstance(payments,dict): payments=payments.get("payments") or payments.get("data") or []
            if isinstance(payments,list): state["payments"]=payments[:10]
        except Exception: pass
    except Exception as exc:
        state["error"]=str(exc)
    return state

def list_miners():
    with closing(db()) as conn:
        rows=conn.execute("SELECT id,name,api_url,agent_url,token,enabled,created_at FROM miners ORDER BY id").fetchall()
    return [dict(r) for r in rows]

def xmrig_summary(miner):
    api_url=clean_url(miner["api_url"])
    token=miner.get("token") or ""
    summary=None; errors=[]
    for endpoint in ("/2/summary","/1/summary"):
        try:
            summary=fetch_json(api_url+endpoint,token); break
        except Exception as exc: errors.append(str(exc))
    if summary is None: raise RuntimeError(errors[-1] if errors else "XMRig API non raggiungibile")
    totals=(summary.get("hashrate") or {}).get("total") or []
    totals=list(totals) if isinstance(totals,(list,tuple)) else []
    def rate(i):
        try: return float(totals[i]) if totals[i] is not None else 0.0
        except (IndexError,TypeError,ValueError): return 0.0
    results=summary.get("results") or {}; connection=summary.get("connection") or {}
    good=int(numeric(results,["shares_good","accepted","good"])); total=int(numeric(results,["shares_total","total"],good))
    return {"worker_id":summary.get("worker_id") or miner["name"],"hashrate_10s":rate(0),"hashrate_60s":rate(1),"hashrate_15m":rate(2),"accepted":good,"rejected":max(0,total-good),"uptime":int(numeric(summary,["uptime"]) or numeric(connection,["uptime"])),"pool":first_text(connection,["pool","url"]),"algo":first_text(connection,["algo"]),"version":summary.get("version","")}

def agent_metrics(miner):
    u=clean_url(miner.get("agent_url") or "")
    if not u: return {"temperature_c":None,"load1":None,"cpu_count":None,"uptime":None}
    data=fetch_json(u+"/v1/metrics")
    return {"temperature_c":data.get("temperature_c"),"load1":data.get("load1"),"cpu_count":data.get("cpu_count"),"uptime":data.get("uptime"),"cpu_model":data.get("cpu_model","")}

def fetch_miner_state(miner):
    result={"id":miner["id"],"name":miner["name"],"api_url":miner["api_url"],"agent_url":miner.get("agent_url") or "","enabled":bool(miner["enabled"]),"online":False,"error":None,"temperature_c":None,"load1":None,"cpu_count":None}
    if not result["enabled"]: return result
    try:
        result.update(xmrig_summary(miner)); result["online"]=True
    except Exception as exc:
        result["error"]=str(exc); return result
    try: result.update(agent_metrics(miner))
    except Exception as exc: result["agent_error"]=str(exc)
    return result

def current_miners():
    return [fetch_miner_state(m) for m in list_miners()]

def save_samples(states):
    ts=now_ts(); cutoff=ts-HISTORY_DAYS*86400
    with closing(db()) as conn:
        for s in states:
            conn.execute("INSERT INTO samples(ts,miner_id,hashrate,temp_c,online) VALUES (?,?,?,?,?)",(ts,s["id"],s.get("hashrate_10s") or 0.0,s.get("temperature_c"),1 if s.get("online") else 0))
        conn.execute("DELETE FROM samples WHERE ts < ?",(cutoff,)); conn.commit()

def sampler_loop():
    while True:
        try: save_samples(current_miners())
        except Exception as exc: app.logger.warning("sampler error: %s",exc)
        time.sleep(REFRESH_SECONDS)

def ensure_sampler():
    global _sampler_started
    with _sampler_lock:
        if not _sampler_started and os.environ.get("DISABLE_SAMPLER","0")!="1":
            threading.Thread(target=sampler_loop,daemon=True,name="xmrig-sampler").start()
            _sampler_started=True

def history(hours=6):
    hours=min(24*HISTORY_DAYS,max(1,int(hours))); since=now_ts()-hours*3600
    with closing(db()) as conn:
        rows=conn.execute("""SELECT s.ts,s.miner_id,m.name,s.hashrate,s.temp_c,s.online
        FROM samples s LEFT JOIN miners m ON m.id=s.miner_id
        WHERE s.ts>=? ORDER BY s.ts ASC""",(since,)).fetchall()
    return [dict(r) for r in rows]

@app.route("/")
def index():
    ensure_sampler(); return render_template("index.html",app_name=APP_NAME)

@app.get("/healthz")
def healthz():
    return jsonify({"ok":True,"time":datetime.now(timezone.utc).isoformat()})

@app.get("/api/settings")
def api_settings_get(): return jsonify(get_settings())

@app.put("/api/settings")
def api_settings_put():
    payload=request.get_json(silent=True) or {}
    try:
        if payload.get("pool_url"): clean_url(payload["pool_url"],"https")
        set_settings(payload); return jsonify(get_settings())
    except ValueError as exc: return jsonify({"error":str(exc)}),400

@app.get("/api/miners")
def api_miners_get(): return jsonify(list_miners())

@app.post("/api/miners")
def api_miners_post():
    payload=request.get_json(silent=True) or {}
    try:
        name=str(payload.get("name") or "").strip(); api_url=clean_url(payload.get("api_url") or "")
        agent_url=clean_url(payload.get("agent_url") or "") if payload.get("agent_url") else ""
        if not name or not api_url: raise ValueError("Nome e URL XMRig sono obbligatori")
        with closing(db()) as conn:
            cur=conn.execute("INSERT INTO miners(name,api_url,agent_url,token,enabled,created_at) VALUES (?,?,?,?,1,?)",(name,api_url,agent_url,str(payload.get("token") or ""),now_ts()))
            conn.commit()
        return jsonify({"id":cur.lastrowid}),201
    except ValueError as exc: return jsonify({"error":str(exc)}),400

@app.delete("/api/miners/<int:miner_id>")
def api_miners_delete(miner_id):
    with closing(db()) as conn:
        conn.execute("DELETE FROM samples WHERE miner_id=?",(miner_id,))
        conn.execute("DELETE FROM miners WHERE id=?",(miner_id,))
        conn.commit()
    return jsonify({"ok":True})

@app.get("/api/overview")
def api_overview():
    ensure_sampler(); settings=get_settings(); pool=fetch_pool_state(settings); miners=current_miners()
    total=sum(x.get("hashrate_10s") or 0 for x in miners if x.get("online"))
    temps=[x.get("temperature_c") for x in miners if isinstance(x.get("temperature_c"),(int,float))]
    return jsonify({"settings":settings,"pool":pool,"miners":miners,"totals":{"hashrate":total,"online":sum(1 for x in miners if x.get("online")),"configured":len(miners),"max_temp_c":max(temps) if temps else None},"refreshed_at":now_ts()})

@app.get("/api/history")
def api_history():
    try: hours=int(request.args.get("hours","6"))
    except ValueError: hours=6
    return jsonify(history(hours))

init_db()
if __name__=="__main__":
    ensure_sampler(); app.run(host="0.0.0.0",port=int(os.environ.get("PORT","8080")),threaded=True)
