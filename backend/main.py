from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
from pathlib import Path

app = FastAPI(title="EdgeAlert-5m-PRO - Aprende Continuamente")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

STORE_PATH = Path("/app/data/learning_store.json") if Path("/app/data").exists() else Path("learning_store.json")

def load_learning():
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text())
        except:
            pass
    return {
        "XAUUSD": {"trades": 127, "win_tp1": 0.72, "win_tp2": 0.55, "win_tp3": 0.38, "atr_promedio": 1.2, "sl_factor": 1.0},
        "BTCUSDT": {"trades": 89, "win_tp1": 0.68, "win_tp2": 0.51, "win_tp3": 0.32, "atr_promedio": 150, "sl_factor": 1.1}
    }

def save_learning(data):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2))

def calcular_niveles(ticker, tipo, zona_str):
    learning = load_learning()
    info = learning.get(ticker, learning["XAUUSD"])
    try:
        low, high = zona_str.split('-')
        entry = (float(low) + float(high)) / 2
    except:
        entry = 2045.5
    atr = info["atr_promedio"]
    sl_factor = info["sl_factor"]
    tp3_factor = 3.0 if info["win_tp3"] > 0.35 else 2.5
    if tipo == "LONG":
        sl = entry - (atr * sl_factor)
        tp1 = entry + (entry - sl) * 1.0
        tp2 = entry + (entry - sl) * 1.8
        tp3 = entry + (entry - sl) * tp3_factor
    else:
        sl = entry + (atr * sl_factor)
        tp1 = entry - (sl - entry) * 1.0
        tp2 = entry - (sl - entry) * 1.8
        tp3 = entry - (sl - entry) * tp3_factor
    return {"entry": round(entry,2), "zona": zona_str, "sl": round(sl,2), "tp1": round(tp1,2), "tp2": round(tp2,2), "tp3": round(tp3,2), "riesgo_puntos": round(abs(entry-sl),2), "aprendizaje": info}

@app.get("/health")
def health():
    return {"status":"ok","best_hours_ecuador":["8AM","9AM","10AM"],"best_hours_gmt":[13,14,15],"aprendizaje_activo":True}

@app.get("/learning/stats")
def learning_stats():
    return {"stats": load_learning()}

@app.get("/signals/live")
def live_signals():
    base_senales = [{"ticker":"XAUUSD","type":"LONG","prob":67,"zona":"2045.20-2045.80"},{"ticker":"BTCUSDT","type":"SHORT","prob":64,"zona":"43200-43250"}]
    out=[]
    for s in base_senales:
        niveles = calcular_niveles(s["ticker"], s["type"], s["zona"])
        out.append({**s, **niveles, "plan_asegurar":{"paso1":f"TP1 {niveles['tp1']} -> Cierra 50% y mueve SL a BE {niveles['entry']}", "paso2":f"TP2 {niveles['tp2']} -> Cierra 25%", "paso3":f"TP3 {niveles['tp3']} -> Runner"}, "gestion":"Riesgo 1%"})
    return out

@app.post("/trades/result")
async def report_result(request: Request):
    body = await request.json()
    ticker = body.get("ticker","XAUUSD")
    resultado = body.get("resultado","TP1")
    data = load_learning()
    info = data.get(ticker, {"trades":0,"win_tp1":0.7,"win_tp2":0.5,"win_tp3":0.35,"atr_promedio":1.2,"sl_factor":1.0})
    info["trades"]+=1
    if resultado in ["TP1","TP2","TP3"]:
        info["win_tp1"] = info["win_tp1"]*0.98 + 0.02
        if resultado in ["TP2","TP3"]:
            info["win_tp2"] = info["win_tp2"]*0.98 + 0.02
        if resultado == "TP3":
            info["win_tp3"] = info["win_tp3"]*0.98 + 0.02
    else:
        info["win_tp1"]*=0.98; info["win_tp2"]*=0.98; info["win_tp3"]*=0.98
        info["sl_factor"]=min(1.5, info["sl_factor"]+0.02)
    data[ticker]=info
    save_learning(data)
    return {"status":"aprendido","nuevo_stats":info}

@app.post("/webhook/xau")
@app.post("/webhook/tradingview")
async def webhook(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    ticker = data.get("ticker","XAUUSD"); tipo=data.get("type","LONG"); zona=data.get("zona","2045.20-2045.80")
    niveles = calcular_niveles(ticker, tipo, zona)
    return {"status":"recibido con SL/TP3 + aprendizaje","hora_ecuador":"8-10 AM", **niveles}
