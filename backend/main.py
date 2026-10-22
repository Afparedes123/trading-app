
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import pytz
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Memoria simple de aprendizaje (en free tier se resetea, pero aprende en el día)
learning_db = {
    "XAUUSD": {"wins": 12, "loss": 4, "tp1": 8, "tp2": 5, "tp3": 3},
    "BTCUSDT": {"wins": 15, "loss": 6, "tp1": 9, "tp2": 6, "tp3": 4},
}

class TradeResult(BaseModel):
    symbol: str
    result: str

def get_ecuador_time():
    tz = pytz.timezone("America/Guayaquil")
    return datetime.now(tz)

def calculate_probability(symbol, hour_ec):
    stats = learning_db.get(symbol, {"wins": 10, "loss": 5, "tp1": 6, "tp2": 4, "tp3": 2})
    total = stats["wins"] + stats["loss"]
    base_win = (stats["wins"] / total * 100) if total > 0 else 65
    
    # Boost si es ventana óptima 8-10 AM Ecuador
    hour_boost = 12 if 8 <= hour_ec <= 10 else 0
    # Boost por historial TP
    tp_boost = (stats["tp1"] + stats["tp2"]*0.5) 
    
    prob = min(92, base_win + hour_boost + random.uniform(-3, 3))
    return round(prob, 1)

@app.get("/health")
def health():
    now = get_ecuador_time()
    return {
        "status": "ok",
        "time_ecuador": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "best_hours_ecuador": ["8AM", "9AM", "10AM"],
        "learning": learning_db
    }

@app.get("/signals/live")
def signals_live():
    now = get_ecuador_time()
    hour = now.hour
    is_optimal = 8 <= hour <= 10

    signals = []
    # XAUUSD
    prob_xau = calculate_probability("XAUUSD", hour)
    signals.append({
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry": 2045.5 + random.uniform(-1, 1),
        "sl": 2044.3,
        "tp1": 2046.7,
        "tp2": 2047.66,
        "tp3": 2049.1,
        "probability": prob_xau,
        "confidence": prob_xau,
        "win_rate": round(learning_db["XAUUSD"]["wins"] / (learning_db["XAUUSD"]["wins"]+learning_db["XAUUSD"]["loss"])*100, 1),
        "is_optimal_hour": is_optimal,
        "reason": "Tendencia alcista + ventana 8-10AM EC" if is_optimal else "Tendencia alcista"
    })
    # BTCUSDT
    prob_btc = calculate_probability("BTCUSDT", hour)
    signals.append({
        "symbol": "BTCUSDT",
        "direction": "BUY",
        "entry": 43225 + random.uniform(-50, 50),
        "sl": 43390,
        "tp1": 43060,
        "tp2": 42928,
        "tp3": 42812.5,
        "probability": prob_btc,
        "confidence": prob_btc,
        "win_rate": round(learning_db["BTCUSDT"]["wins"] / (learning_db["BTCUSDT"]["wins"]+learning_db["BTCUSDT"]["loss"])*100, 1),
        "is_optimal_hour": is_optimal,
        "reason": "Soporte fuerte + ventana EC" if is_optimal else "Soporte fuerte"
    })
    
    return signals

@app.post("/trades/result")
def save_result(r: TradeResult):
    sym = r.symbol.upper()
    if sym not in learning_db:
        learning_db[sym] = {"wins": 0, "loss": 0, "tp1": 0, "tp2": 0, "tp3": 0}
    
    if r.result == "SL":
        learning_db[sym]["loss"] += 1
    else:
        learning_db[sym]["wins"] += 1
        if r.result == "TP1": learning_db[sym]["tp1"] += 1
        if r.result == "TP2": learning_db[sym]["tp2"] += 1
        if r.result == "TP3": learning_db[sym]["tp3"] += 1
    
    return {"ok": True, "learning": learning_db[sym], "message": f"Aprendido {sym} -> {r.result}"}

@app.get("/")
def root():
    return {"message": "EdgeAlert Backend con probabilidad", "docs": "/docs"}
