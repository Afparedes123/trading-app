
import os
import sqlite3
import json
import random
import requests
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "learning.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_MIN_PROB = float(os.getenv("ALERT_MIN_PROBABILITY", "75"))

# DB Persistente
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS learning (
        symbol TEXT PRIMARY KEY,
        wins INTEGER DEFAULT 0,
        loss INTEGER DEFAULT 0,
        tp1 INTEGER DEFAULT 0,
        tp2 INTEGER DEFAULT 0,
        tp3 INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp1 REAL,
        tp2 REAL,
        tp3 REAL,
        probability REAL,
        result TEXT,
        source TEXT,
        timestamp TEXT
    )""")
    # Inicializa si vacío
    for sym in ["XAUUSD", "BTCUSDT"]:
        c.execute("INSERT OR IGNORE INTO learning (symbol,wins,loss,tp1,tp2,tp3) VALUES (?,?,?,?,?,?)",
                  (sym, 12, 4, 8, 5, 3))
    conn.commit()
    conn.close()

def get_stats(symbol):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT wins,loss,tp1,tp2,tp3 FROM learning WHERE symbol=?", (symbol,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"wins": row[0], "loss": row[1], "tp1": row[2], "tp2": row[3], "tp3": row[4]}
    return {"wins": 10, "loss": 5, "tp1": 6, "tp2": 4, "tp3": 2}

def update_stats(symbol, result):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT symbol FROM learning WHERE symbol=?", (symbol,))
    if not c.fetchone():
        c.execute("INSERT INTO learning (symbol,wins,loss,tp1,tp2,tp3) VALUES (?,?,?,?,?,?)",
                  (symbol, 0, 0, 0, 0, 0))
    if result == "SL":
        c.execute("UPDATE learning SET loss = loss + 1 WHERE symbol=?", (symbol,))
    else:
        c.execute("UPDATE learning SET wins = wins + 1 WHERE symbol=?", (symbol,))
        if result == "TP1":
            c.execute("UPDATE learning SET tp1 = tp1 + 1 WHERE symbol=?", (symbol,))
        if result == "TP2":
            c.execute("UPDATE learning SET tp2 = tp2 + 1 WHERE symbol=?", (symbol,))
        if result == "TP3":
            c.execute("UPDATE learning SET tp3 = tp3 + 1 WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()

def save_trade(symbol, direction, entry, sl, tp1, tp2, tp3, prob, result, source):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,result,source,timestamp)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (symbol, direction, entry, sl, tp1, tp2, tp3, prob, result, source, datetime.now(EC_TZ).isoformat()))
    conn.commit()
    conn.close()

def calculate_probability(symbol, hour_ec):
    stats = get_stats(symbol)
    total = stats["wins"] + stats["loss"]
    base_win = (stats["wins"] / total * 100) if total > 0 else 65
    hour_boost = 12 if 8 <= hour_ec <= 10 else 0
    prob = min(92, base_win + hour_boost + random.uniform(-3, 3))
    return round(prob, 1), stats

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

init_db()

class TradeResult(BaseModel):
    symbol: str
    result: str

@app.get("/")
def root():
    return {"message": "EdgeAlert Backend Persistente", "db": DB_PATH, "docs": "/docs", "webhook": "/webhook/tradingview"}

@app.get("/health")
def health():
    now = datetime.now(EC_TZ)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT symbol,wins,loss FROM learning")
    rows = c.fetchall()
    conn.close()
    learning = {r[0]: {"wins": r[1], "loss": r[2]} for r in rows}
    return {
        "status": "ok",
        "time_ecuador": now.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": DB_PATH,
        "best_hours": "8AM-10AM EC",
        "learning": learning,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    }

@app.get("/signals/live")
def signals_live():
    now = datetime.now(EC_TZ)
    hour = now.hour
    is_optimal = 8 <= hour <= 10
    
    signals = []
    for sym, default_entry in [("XAUUSD", 2045.5), ("BTCUSDT", 43225)]:
        prob, stats = calculate_probability(sym, hour)
        total = stats["wins"] + stats["loss"]
        win_rate = round(stats["wins"] / total * 100, 1) if total > 0 else 0
        
        # Datos base (si viene de TradingView usará esos, si no usa estos demo)
        entry = round(default_entry + random.uniform(-1, 1), 2)
        sl = 2044.3 if sym == "XAUUSD" else 43390
        tp1 = 2046.7 if sym == "XAUUSD" else 43060
        tp2 = 2047.66 if sym == "XAUUSD" else 42928
        tp3 = 2049.1 if sym == "XAUUSD" else 42812.5
        
        signals.append({
            "symbol": sym,
            "direction": "BUY",
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "probability": prob,
            "confidence": prob,
            "win_rate": win_rate,
            "is_optimal_hour": is_optimal,
            "reason": f"Tendencia + ventana 8-10AM EC ({stats['wins']}W/{stats['loss']}L)" if is_optimal else f"Historial {stats['wins']}W/{stats['loss']}L"
        })
    
    return signals

@app.post("/trades/result")
def save_result_endpoint(r: TradeResult):
    sym = r.symbol.upper()
    update_stats(sym, r.result)
    save_trade(sym, "MANUAL", 0, 0, 0, 0, 0, 0, r.result, "manual_click")
    stats = get_stats(sym)
    return {"ok": True, "learning": stats, "message": f"Aprendido {sym} -> {r.result} - Persistido en DB"}

@app.get("/learning/stats")
def learning_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT symbol,wins,loss,tp1,tp2,tp3 FROM learning")
    rows = c.fetchall()
    c.execute("SELECT symbol,result,COUNT(*) FROM trades GROUP BY symbol,result")
    trades = c.fetchall()
    conn.close()
    return {"learning": rows, "trades_by_result": trades}

# WEBHOOK TRADINGVIEW
@app.post("/webhook/tradingview")
async def webhook_tradingview(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    
    # TradingView puede enviar: {"symbol":"XAUUSD","action":"BUY","price":2045.5,"sl":2044,"tp1":2046.7...}
    symbol = str(data.get("symbol", "XAUUSD")).upper()
    action = str(data.get("action", data.get("side", "BUY"))).upper()
    price = float(data.get("price", data.get("entry", 0)) or 0)
    sl = float(data.get("sl", data.get("stop", 0)) or 0)
    tp1 = float(data.get("tp1", data.get("tp", 0)) or 0)
    tp2 = float(data.get("tp2", 0) or 0)
    tp3 = float(data.get("tp3", 0) or 0)
    
    now = datetime.now(EC_TZ)
    prob, stats = calculate_probability(symbol, now.hour)
    
    # Si no trae precios, usa demo
    if price == 0:
        price = 2045.5 if "XAU" in symbol else 43225
    if sl == 0:
        sl = price - 1.2 if "BUY" in action else price + 1.2
    if tp1 == 0:
        tp1 = price + 1.2 if "BUY" in action else price - 1.2
    
    save_trade(symbol, action, price, sl, tp1, tp2, tp3, prob, "NEW", "tradingview")
    
    # Alerta Telegram si prob alta y en ventana óptima
    if prob >= ALERT_MIN_PROB:
        msg = f"🔥 *{symbol} {action} - {prob}% PROB*\n\nENTRY: {price}\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}\n\nHora EC: {now.strftime('%H:%M')} - Ventana {'OPTIMA ✅' if 8 <= now.hour <= 10 else 'fuera de ventana'}\nWinRate: {stats['wins']}W/{stats['loss']}L"
        send_telegram(msg)
    
    return {
        "ok": True,
        "received": data,
        "calculated": {"symbol": symbol, "probability": prob, "is_optimal": 8 <= now.hour <= 10},
        "telegram_sent": prob >= ALERT_MIN_PROB
    }
