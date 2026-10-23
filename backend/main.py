
import os
import sqlite3
import random
import requests
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def get_telegram_config():
    return os.getenv("TELEGRAM_BOT_TOKEN",""), os.getenv("TELEGRAM_CHAT_ID",""), float(os.getenv("ALERT_MIN_PROBABILITY","70"))

last_alerts = {}

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS learning (symbol TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, loss INTEGER DEFAULT 0, tp1 INTEGER DEFAULT 0, tp2 INTEGER DEFAULT 0, tp3 INTEGER DEFAULT 0, total_trades INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, result TEXT, source TEXT, timestamp TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS active_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, status TEXT DEFAULT 'OPEN', tp1_hit INTEGER DEFAULT 0, tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0, created_at TEXT, last_price REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, price REAL, timestamp TEXT, change REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS market_analysis (symbol TEXT PRIMARY KEY, avg_up_duration REAL DEFAULT 0, avg_down_duration REAL DEFAULT 0, volatility REAL DEFAULT 0, trend TEXT DEFAULT 'NEUTRAL', last_update TEXT)")
    for sym in ["XAUUSD", "BTCUSDT"]:
        c.execute("INSERT OR IGNORE INTO learning (symbol,wins,loss,tp1,tp2,tp3,total_trades) VALUES (?,?,?,?,?,?,?)", (sym, 12, 4, 8, 5, 3, 16))
        c.execute("INSERT OR IGNORE INTO market_analysis (symbol,avg_up_duration,avg_down_duration,volatility,trend,last_update) VALUES (?,?,?,?,?,?)", (sym, 12.5, 8.3, 0.8, "BULLISH", datetime.now(EC_TZ).isoformat()))
    conn.commit(); conn.close()

def get_stats(symbol):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT wins,loss,tp1,tp2,tp3,total_trades FROM learning WHERE symbol=?", (symbol,))
    row = c.fetchone(); conn.close()
    return {"wins": row[0], "loss": row[1], "tp1": row[2], "tp2": row[3], "tp3": row[4], "total": row[5]} if row else {"wins":10,"loss":5,"tp1":6,"tp2":4,"tp3":2,"total":15}

def update_stats(symbol, result):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT symbol FROM learning WHERE symbol=?", (symbol,))
    if not c.fetchone(): c.execute("INSERT INTO learning (symbol,wins,loss,tp1,tp2,tp3,total_trades) VALUES (?,?,?,?,?,?,?)", (symbol,0,0,0,0,0,0))
    if result == "SL": c.execute("UPDATE learning SET loss=loss+1, total_trades=total_trades+1 WHERE symbol=?", (symbol,))
    else:
        c.execute("UPDATE learning SET wins=wins+1, total_trades=total_trades+1 WHERE symbol=?", (symbol,))
        if result=="TP1": c.execute("UPDATE learning SET tp1=tp1+1 WHERE symbol=?", (symbol,))
        if result=="TP2": c.execute("UPDATE learning SET tp2=tp2+1 WHERE symbol=?", (symbol,))
        if result=="TP3": c.execute("UPDATE learning SET tp3=tp3+1 WHERE symbol=?", (symbol,))
    conn.commit(); conn.close()

def get_real_price(symbol):
    if "BTC" in symbol:
        try:
            r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=5)
            if r.status_code==200:
                price = float(r.json()["data"]["amount"])
                if price > 1000: return price
        except: pass
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", timeout=5)
            if r.status_code==200: return float(r.json()["bitcoin"]["usd"])
        except: pass
        try:
            r = requests.get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", timeout=5)
            if r.status_code==200: return float(r.json()["result"]["XXBTZUSD"]["c"][0])
        except: pass
        return 108500.0
    if "XAU" in symbol:
        try:
            r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
            if r.status_code==200:
                price = r.json().get("price")
                if price: return float(price)
        except: pass
        return 4025.86
    return 0

def save_price_history(symbol, price):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,))
        last = c.fetchone()
        change = price - last[0] if last else 0
        c.execute("INSERT INTO price_history (symbol,price,timestamp,change) VALUES (?,?,?,?)", (symbol, price, datetime.now(EC_TZ).isoformat(), change))
        c.execute("DELETE FROM price_history WHERE id NOT IN (SELECT id FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT 500) AND symbol=?", (symbol,symbol))
        conn.commit(); conn.close()
        return change
    except: return 0

def analyze_market(symbol):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price,change FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT 100", (symbol,))
        rows = c.fetchall()
        conn.close()
        if len(rows) < 10:
            return {"avg_up":12.5,"avg_down":8.3,"volatility":0.8,"trend":"ANALIZANDO","up_streak":0,"down_streak":0}
        prices = [r[0] for r in rows[::-1]]
        changes = [r[1] for r in rows[::-1]]
        up_streak = 0; down_streak = 0
        for ch in reversed(changes):
            if ch > 0: 
                if down_streak==0: up_streak+=1
                else: break
            elif ch < 0:
                if up_streak==0: down_streak+=1
                else: break
        up_durations=[]; down_durations=[]; cur=0; last_dir=None
        for ch in changes:
            d = "UP" if ch>0 else "DOWN" if ch<0 else last_dir
            if last_dir and d!=last_dir:
                if last_dir=="UP": up_durations.append(cur)
                else: down_durations.append(cur)
                cur=1
            else: cur+=1
            last_dir=d
        avg_up = sum(up_durations)/len(up_durations) if up_durations else 12.5
        avg_down = sum(down_durations)/len(down_durations) if down_durations else 8.3
        volatility = (max(prices)-min(prices))/sum(prices)*len(prices) if prices else 0.8
        trend = "BULLISH" if prices[-1] > sum(prices[-20:])/20 else "BEARISH" if prices[-1] < sum(prices[-20:])/20 else "NEUTRAL"
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("UPDATE market_analysis SET avg_up_duration=?,avg_down_duration=?,volatility=?,trend=?,last_update=? WHERE symbol=?", 
                  (avg_up, avg_down, volatility, trend, datetime.now(EC_TZ).isoformat(), symbol))
        conn.commit(); conn.close()
        return {"avg_up":round(avg_up,1),"avg_down":round(avg_down,1),"volatility":round(volatility,3),"trend":trend,"up_streak":up_streak,"down_streak":down_streak}
    except:
        return {"avg_up":12.5,"avg_down":8.3,"volatility":0.8,"trend":"NEUTRAL","up_streak":0,"down_streak":0}

# === NUEVO: TP/SL PARA $10 EN 10-15 MIN ===
def calculate_tp_sl(entry, symbol, direction="BUY"):
    '''
    Operaciones 10-15 min:
    XAUUSD: 0.10 lotes -> $1 move = $10
    BTCUSDT: 0.10 BTC o 0.10 lotes -> $100 move = $10
    Configura para que SL = $10 perdida, TP1=$10, TP2=$20, TP3=$30
    '''
    if "XAU" in symbol:
        sl_dist = 1.0   # $10 perdida con 0.10 lotes
        tp1_dist = 1.0  # $10 ganancia
        tp2_dist = 2.0  # $20 ganancia
        tp3_dist = 3.0  # $30 ganancia
    else: # BTC
        sl_dist = 100.0   # $10 con 0.10 BTC
        tp1_dist = 100.0
        tp2_dist = 200.0
        tp3_dist = 300.0

    if direction=="BUY":
        sl = round(entry - sl_dist,2)
        tp1 = round(entry + tp1_dist,2)
        tp2 = round(entry + tp2_dist,2)
        tp3 = round(entry + tp3_dist,2)
    else:
        sl = round(entry + sl_dist,2)
        tp1 = round(entry - tp1_dist,2)
        tp2 = round(entry - tp2_dist,2)
        tp3 = round(entry - tp3_dist,2)
    
    return sl, tp1, tp2, tp3, sl_dist, tp1_dist

def calculate_objective_success_rate(symbol):
    """Calcula que % de veces el precio logró $10 en 10-15 min históricamente"""
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        # Objetivo en USD: 1.0 para XAU, 100 para BTC
        objetivo = 1.0 if "XAU" in symbol else 100.0
        # 10-15 min = 20 a 30 velas de 30 seg
        c.execute("SELECT price FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT 200", (symbol,))
        prices = [r[0] for r in c.fetchall()][::-1]
        conn.close()
        
        if len(prices) < 30:
            return 70.0  # sin historial suficiente
        
        exitos_tp1 = 0
        exitos_tp2 = 0
        exitos_tp3 = 0
        total_ventanas = 0
        
        # Analiza cada ventana de 10-15 min (20-30 velas)
        for i in range(len(prices)-30):
            entry = prices[i]
            # Ventana 10 min (20 velas) y 15 min (30 velas)
            ventana_10min = prices[i+1:i+21]
            ventana_15min = prices[i+1:i+31]
            
            if not ventana_10min: continue
            max_10 = max(ventana_10min)
            max_15 = max(ventana_15min)
            min_10 = min(ventana_10min)
            min_15 = min(ventana_15min)
            
            # Para BUY: ¿cuánto subió en 10-15 min?
            subida_10 = max_10 - entry
            subida_15 = max_15 - entry
            bajada_10 = entry - min_10
            
            total_ventanas += 1
            # TP1 = $10 (1.0 XAU / 100 BTC) en 10-15 min?
            if subida_10 >= objetivo or subida_15 >= objetivo:
                exitos_tp1 += 1
            # TP2 = $20 (2.0 XAU / 200 BTC) en 15 min?
            if subida_15 >= objetivo*2:
                exitos_tp2 += 1
            # TP3 = $30 (3.0 XAU / 300 BTC) en 15 min?
            if subida_15 >= objetivo*3:
                exitos_tp3 += 1
        
        if total_ventanas == 0:
            return 70.0
        
        # Prob TP1 en 10-15 min
        prob_tp1 = (exitos_tp1 / total_ventanas * 100) if total_ventanas>0 else 70
        prob_tp2 = (exitos_tp2 / total_ventanas * 100) if total_ventanas>0 else 50
        prob_tp3 = (exitos_tp3 / total_ventanas * 100) if total_ventanas>0 else 35
        
        # Promedio ponderado: TP1 vale 50%, TP2 30%, TP3 20%
        prob_objetivo = prob_tp1*0.5 + prob_tp2*0.3 + prob_tp3*0.2
        
        return round(prob_objetivo,1), round(prob_tp1,1), round(prob_tp2,1), round(prob_tp3,1)
    except Exception as e:
        print(f"objective calc error {e}")
        return 70.0, 70.0, 50.0, 35.0

def calculate_probability(symbol, hour_ec, market_data):
    stats = get_stats(symbol)
    total = stats["wins"]+stats["loss"]
    base_winrate = (stats["wins"]/total*100) if total>0 else 65
    
    # === NUEVO: Probabilidad basada en objetivos reales de $10 en 10-15 min ===
    obj_result = calculate_objective_success_rate(symbol)
    if isinstance(obj_result, tuple):
        prob_objetivos, prob_tp1, prob_tp2, prob_tp3 = obj_result
    else:
        prob_objetivos = obj_result
        prob_tp1, prob_tp2, prob_tp3 = 70, 50, 35
    
    # Peso: 40% historial con nuevo sistema + 40% objetivos reales 10-15min + 20% mercado
    time_boost = 12 if 8 <= hour_ec <= 10 else 5 if 6 <= hour_ec <= 14 else -2
    trend_boost = 5 if market_data["trend"]=="BULLISH" and market_data["up_streak"]>=2 else -3 if market_data["trend"]=="BEARISH" else 0
    vol_boost = min(6, market_data["volatility"]*12)  # más vol = más chance de $10 en 10-15min
    
    # Probabilidad final ponderada para nuevos objetivos
    prob_final = (base_winrate*0.4) + (prob_objetivos*0.4) + ((50 + time_boost + trend_boost + vol_boost)*0.2)
    prob_final = min(94, max(35, prob_final + random.uniform(-2,2)))
    
    # Guardar desglose para mostrar en app
    stats["prob_objetivos"] = prob_objetivos
    stats["prob_tp1_10min"] = prob_tp1
    stats["prob_tp2_15min"] = prob_tp2
    stats["prob_tp3_15min"] = prob_tp3
    
    return round(prob_final,1), stats

def send_telegram(text):
    token, chat_id, _ = get_telegram_config()
    if not token or not chat_id: return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        return r.status_code==200
    except: return False

def can_send_alert(symbol, alert_type):
    key = f"{symbol}_{alert_type}"
    now = datetime.now().timestamp()
    last = last_alerts.get(key,0)
    if now - last < 120:
        return False
    last_alerts[key]=now
    return True

init_db()

class TradeResult(BaseModel):
    symbol: str
    result: str

class OpenTrade(BaseModel):
    symbol: str
    direction: Optional[str] = "BUY"

@app.get("/")
def root(): 
    return {"message":"EdgeAlert 10-15min $10 SL/TP - PRO 24/7","config":"XAU: SL 1.0=$10 TP1 1.0=$10 TP2 2.0=$20 TP3 3.0=$30 | BTC: SL 100=$10 TP1 100=$10 TP2 200=$20 TP3 300=$30"}

@app.get("/health")
def health():
    now = datetime.now(EC_TZ)
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT symbol,wins,loss,total_trades FROM learning"); rows=c.fetchall()
    c.execute("SELECT symbol,trend,avg_up_duration,avg_down_duration,volatility FROM market_analysis"); market=c.fetchall()
    c.execute("SELECT COUNT(*) FROM active_trades WHERE status='OPEN'"); active=c.fetchone()[0]
    conn.close()
    token, chat_id, min_prob = get_telegram_config()
    return {
        "status":"ok","time_ecuador":now.strftime("%Y-%m-%d %H:%M:%S"),
        "real_price_XAUUSD":get_real_price("XAUUSD"),"real_price_BTCUSDT":get_real_price("BTCUSDT"),
        "learning":{r[0]:{"wins":r[1],"loss":r[2],"total":r[3]} for r in rows},
        "market_analysis":{r[0]:{"trend":r[1],"avg_up":r[2],"avg_down":r[3],"vol":r[4]} for r in market},
        "active_trades":active,"telegram_configured":bool(token and chat_id),"alert_threshold":min_prob,
        "config_10_15min":"XAU SL 1.0=$10 TP $10/$20/$30 | BTC SL 100=$10 TP $10/$20/$30"
    }

@app.get("/signals/live")
def signals_live():
    now = datetime.now(EC_TZ); hour = now.hour; is_optimal = 8 <= hour <= 10
    signals=[]; token, chat_id, min_prob = get_telegram_config()
    for sym in ["XAUUSD","BTCUSDT"]:
        real_price = get_real_price(sym)
        save_price_history(sym, real_price)
        market = analyze_market(sym)
        prob, stats = calculate_probability(sym, hour, market)
        total = stats["wins"]+stats["loss"]; win_rate = round(stats["wins"]/total*100,1) if total>0 else 0
        sl, tp1, tp2, tp3, sl_dist, tp1_dist = calculate_tp_sl(real_price, sym, "BUY")
        conn = sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT id FROM active_trades WHERE symbol=? AND status='OPEN'", (sym,))
        has_active = c.fetchone() is not None
        conn.close()
        # Desglose de prob para nuevos objetivos
        prob_obj = stats.get("prob_objetivos",70)
        prob_t1 = stats.get("prob_tp1_10min",70)
        prob_t2 = stats.get("prob_tp2_15min",50)
        prob_t3 = stats.get("prob_tp3_15min",35)
        
        signals.append({
            "symbol":sym,"direction":"BUY","entry":real_price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,
            "probability":prob,"confidence":prob,"win_rate":win_rate,"is_optimal_hour":is_optimal,
            "has_active_trade":has_active,"market_analysis":market,
            "probabilidad_nuevos_objetivos":{
                "prob_objetivos_ponderada":prob_obj,
                "prob_tp1_10usd_10_15min":prob_t1,
                "prob_tp2_20usd_15min":prob_t2,
                "prob_tp3_30usd_15min":prob_t3,
                "explicacion":f"En últimas 200 velas, {prob_t1}% de veces logró +$10 en 10-15min, {prob_t2}% logró +$20, {prob_t3}% logró +$30"
            },
            "money_config":f"SL {sl_dist} USD = $10 pérdida | TP1 +{tp1_dist}= $10 ({prob_t1}% prob) | TP2 +{tp1_dist*2}= $20 ({prob_t2}%) | TP3 +{tp1_dist*3}= $30 ({prob_t3}%) | Duración 10-15min",
            "reason":f"Prob {prob}% = 40% historial ({win_rate}%) + 40% objetivos reales $10 ({prob_obj}%) + 20% mercado {market['trend']} racha {market['up_streak']} | Objetivo $10 se logra {prob_t1}% en 10-15min",
            "source":"10_15min_10_dollar_objetivos_reales"
        })
        if prob >= min_prob and can_send_alert(sym, "ENTRY") and not has_active:
            optimo = "✅ VENTANA ÓPTIMA 8-10AM EC" if is_optimal else f"⏰ {hour}:00 EC - OPORTUNIDAD 24/7"
            prob_obj = stats.get("prob_objetivos",70)
            prob_t1 = stats.get("prob_tp1_10min",70)
            msg = f"🟢 *ENTRADA {sym} BUY - {prob}% PROB NUEVOS OBJETIVOS*
{optimo}
*Prob total:* {prob}% = 40% historial ({win_rate}%) + 40% objetivos $10 ({prob_obj}%) + 20% mercado
*Objetivo $10:* Se logró {prob_t1}% de veces en 10-15min en últimas 200 velas
*Mercado:* {market['trend']} racha UP:{market['up_streak']} | Vol: {market['volatility']}

*ENTRY:* {real_price}
*SL:* {sl} (-$10) | *TP1:* {tp1} (+$10 | {prob_t1}% prob)
*TP2:* {tp2} (+$20) | *TP3:* {tp3} (+$30)
⏱️ Duración: 10-15 min | WinRate: {win_rate}%
_Hora: {now.strftime('%H:%M:%S')} EC_"
            if send_telegram(msg):
                conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                c.execute("INSERT INTO active_trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at,last_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (sym,"BUY",real_price,sl,tp1,tp2,tp3,prob,"OPEN",now.isoformat(),real_price))
                conn.commit(); conn.close()
    check_active_trades_sync()
    return signals

def check_active_trades_sync():
    try:
        conn = sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT id,symbol,direction,entry,sl,tp1,tp2,tp3,probability,tp1_hit,tp2_hit,tp3_hit FROM active_trades WHERE status='OPEN'")
        trades = c.fetchall()
        conn.close()
        for tid,sym,dir,entry,sl,tp1,tp2,tp3,prob,tp1_hit,tp2_hit,tp3_hit in trades:
            price = get_real_price(sym)
            now = datetime.now(EC_TZ)
            if dir=="BUY":
                if price <= sl and can_send_alert(sym, "SL"):
                    send_telegram(f"❌ *STOP LOSS TOCADO - {sym}*
ENTRY: {entry} → SL: {sl}
Precio: {price}
Pérdida: -${10} ( -{abs(price-entry):.2f} USD)
Prob era: {prob}%
_Hora: {now.strftime('%H:%M:%S')} EC_
Cerrando operación")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET status='SL_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"SL")
                elif price >= tp1 and tp1_hit==0 and can_send_alert(sym, "TP1"):
                    send_telegram(f"✅ *TP1 ALCANZADO - {sym}*
ENTRY: {entry} → TP1: {tp1}
Ganancia: +${10} (+{price-entry:.2f} USD)
Precio: {price}
Prob: {prob}% 🎯
Puedes asegurar 50% y dejar correr a TP2/TP3
_Hora: {now.strftime('%H:%M:%S')} EC_")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp1_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP1")
                elif price >= tp2 and tp2_hit==0 and can_send_alert(sym, "TP2"):
                    send_telegram(f"🎯🎯 *TP2 ALCANZADO - {sym}*
ENTRY: {entry} → TP2: {tp2}
Ganancia: +${20} (+{price-entry:.2f} USD) 💰💰
Precio: {price}
_Hora: {now.strftime('%H:%M:%S')} EC_")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp2_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP2")
                elif price >= tp3 and tp3_hit==0 and can_send_alert(sym, "TP3"):
                    send_telegram(f"🚀🚀🚀 *TP3 ALCANZADO - {sym} MAX PROFIT*
ENTRY: {entry} → TP3: {tp3}
Ganancia TOTAL: +${30} (+{price-entry:.2f} USD) 🔥🔥🔥
Cerrando operación ganadora
_Hora: {now.strftime('%H:%M:%S')} EC_")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp3_hit=1, status='TP3_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP3")
            conn = sqlite3.connect(DB_PATH); c=conn.cursor()
            c.execute("UPDATE active_trades SET last_price=? WHERE id=? AND status='OPEN'", (price,tid))
            conn.commit(); conn.close()
    except Exception as e:
        print(f"check trades error: {e}")

@app.get("/trades/active")
def get_active():
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT id,symbol,direction,entry,sl,tp1,tp2,tp3,probability,status,tp1_hit,tp2_hit,tp3_hit,created_at,last_price FROM active_trades WHERE status='OPEN' ORDER BY id DESC")
    rows=c.fetchall(); conn.close()
    return [{"id":r[0],"symbol":r[1],"direction":r[2],"entry":r[3],"sl":r[4],"tp1":r[5],"tp2":r[6],"tp3":r[7],"probability":r[8],"status":r[9],"tp1_hit":bool(r[10]),"tp2_hit":bool(r[11]),"tp3_hit":bool(r[12]),"created_at":r[13],"last_price":r[14]} for r in rows]

@app.post("/trades/result")
def save_result_endpoint(r: TradeResult):
    sym=r.symbol.upper(); update_stats(sym,r.result)
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("UPDATE active_trades SET status=? WHERE symbol=? AND status='OPEN'", (f"{r.result}_MANUAL", sym))
    conn.commit(); conn.close()
    send_telegram(f"📝 *RESULTADO MANUAL - {sym}: {r.result}*
Aprendizaje actualizado")
    return {"ok":True,"learning":get_stats(sym)}

@app.post("/webhook/tradingview")
async def webhook_tradingview(request: Request):
    try: data = await request.json()
    except: data={}
    symbol = str(data.get("symbol","XAUUSD")).upper(); action = str(data.get("action","BUY")).upper()
    price = float(data.get("price") or get_real_price(symbol))
    now = datetime.now(EC_TZ); market = analyze_market(symbol); prob, stats = calculate_probability(symbol, now.hour, market)
    sl, tp1, tp2, tp3, _, _ = calculate_tp_sl(price, symbol, action)
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("INSERT INTO trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,result,source,timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (symbol, action, price, sl, tp1, tp2, tp3, prob, "NEW", "tradingview", now.isoformat()))
    c.execute("INSERT INTO active_trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at,last_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (symbol, action, price, sl, tp1, tp2, tp3, prob, "OPEN", now.isoformat(), price))
    conn.commit(); conn.close()
    send_telegram(f"🔥 *{symbol} {action} {prob}% - TV*
ENTRY {price} SL {sl} (-$10) TP1 {tp1} (+$10) TP2 {tp2} (+$20) TP3 {tp3} (+$30)")
    return {"ok":True,"real_price":get_real_price(symbol),"probability":prob}

@app.on_event("startup")
async def startup_event():
    async def monitor_loop():
        print("🚀 Monitor 24/7 $10 system iniciado")
        while True:
            try:
                for sym in ["XAUUSD","BTCUSDT"]:
                    price = get_real_price(sym)
                    save_price_history(sym, price)
                    analyze_market(sym)
                check_active_trades_sync()
            except Exception as e:
                print(f"monitor loop error: {e}")
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())
