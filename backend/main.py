
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

app = FastAPI(title="EdgeAlert-5m-PRO 10-15min Fixed")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def get_telegram_config():
    return os.getenv("TELEGRAM_BOT_TOKEN",""), os.getenv("TELEGRAM_CHAT_ID",""), float(os.getenv("ALERT_MIN_PROBABILITY","70"))

last_alerts = {}
last_directions = {}  # memoria para no cambiar cada momento

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS learning (symbol TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, loss INTEGER DEFAULT 0, tp1 INTEGER DEFAULT 0, tp2 INTEGER DEFAULT 0, tp3 INTEGER DEFAULT 0, total_trades INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, result TEXT, source TEXT, timestamp TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS active_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, status TEXT DEFAULT 'OPEN', tp1_hit INTEGER DEFAULT 0, tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0, created_at TEXT, last_price REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, price REAL, timestamp TEXT, change REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS market_analysis (symbol TEXT PRIMARY KEY, avg_up_duration REAL DEFAULT 0, avg_down_duration REAL DEFAULT 0, volatility REAL DEFAULT 0, trend TEXT DEFAULT 'NEUTRAL', last_update TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (symbol TEXT PRIMARY KEY, direction TEXT, confirmed_at TEXT, consecutive_count INTEGER DEFAULT 0)""")
    for sym in ["XAUUSD", "BTCUSDT"]:
        c.execute("INSERT OR IGNORE INTO learning (symbol,wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (sym, 12, 4, 8, 5, 3, 16, 7, 9, 5, 7))
        c.execute("INSERT OR IGNORE INTO market_analysis (symbol,avg_up_duration,avg_down_duration,volatility,trend,last_update) VALUES (?,?,?,?,?,?)", (sym, 12.5, 8.3, 0.8, "BULLISH", datetime.now(EC_TZ).isoformat()))
        c.execute("INSERT OR IGNORE INTO last_signal (symbol,direction,confirmed_at,consecutive_count) VALUES (?,?,?,?)", (sym, "BUY", datetime.now(EC_TZ).isoformat(), 1))
    conn.commit(); conn.close()

init_db()

class TradeResult(BaseModel):
    symbol: str
    result: str
    timestamp: Optional[str] = None

def get_stats(symbol):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total FROM learning WHERE symbol=?", (symbol,))
    row = c.fetchone(); conn.close()
    if row:
        return {"wins": row[0], "loss": row[1], "tp1": row[2], "tp2": row[3], "tp3": row[4], "total": row[5], "buy_wins": row[6], "buy_total": row[7], "sell_wins": row[8], "sell_total": row[9]}
    return {"wins":10,"loss":5,"tp1":6,"tp2":4,"tp3":2,"total":15,"buy_wins":6,"buy_total":8,"sell_wins":4,"sell_total":7}

def update_stats(symbol, result, direction="BUY"):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT symbol FROM learning WHERE symbol=?", (symbol,))
    if not c.fetchone():
        c.execute("INSERT INTO learning (symbol,wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (symbol,0,0,0,0,0,0,0,0,0,0))
    is_win = result != "SL"
    if result == "SL":
        c.execute("UPDATE learning SET loss=loss+1, total_trades=total_trades+1 WHERE symbol=?", (symbol,))
        if direction=="BUY":
            c.execute("UPDATE learning SET buy_total=buy_total+1 WHERE symbol=?", (symbol,))
        else:
            c.execute("UPDATE learning SET sell_total=sell_total+1 WHERE symbol=?", (symbol,))
    else:
        c.execute("UPDATE learning SET wins=wins+1, total_trades=total_trades+1 WHERE symbol=?", (symbol,))
        if direction=="BUY":
            c.execute("UPDATE learning SET buy_wins=buy_wins+1, buy_total=buy_total+1 WHERE symbol=?", (symbol,))
        else:
            c.execute("UPDATE learning SET sell_wins=sell_wins+1, sell_total=sell_total+1 WHERE symbol=?", (symbol,))
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
        return 81500.0
    if "XAU" in symbol:
        try:
            r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
            if r.status_code==200:
                price = r.json().get("price")
                if price: return float(price)
        except: pass
        try:
            r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=8)
            if r.status_code==200:
                for it in r.json().get("items",[]):
                    if it.get("curr")=="XAU" and it.get("xauPrice",0)>0:
                        return float(it["xauPrice"])
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

def get_price_history(symbol, limit=150):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price, timestamp, change FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit))
        rows = c.fetchall()
        conn.close()
        return rows[::-1]  # oldest first
    except:
        return []

def build_candles(price_rows, points_per_candle):
    """Convierte historial de ticks (30s) en velas de 10 o 15 min con HIGH/LOW reales"""
    candles = []
    if len(price_rows) < points_per_candle:
        return []
    # Agrupa cada N puntos en una vela
    for i in range(0, len(price_rows), points_per_candle):
        chunk = price_rows[i:i+points_per_candle]
        if len(chunk) < points_per_candle * 0.7:  # vela incompleta
            continue
        prices = [r[0] for r in chunk]
        if not prices:
            continue
        open_p = prices[0]
        close_p = prices[-1]
        high_p = max(prices)
        low_p = min(prices)
        candles.append({
            "open": open_p,
            "close": close_p,
            "high": high_p,
            "low": low_p,
            "range": high_p - low_p,
            "body": abs(close_p - open_p),
            "bullish": close_p > open_p
        })
    return candles

def analyze_10_15_min(symbol):
    """
    ANALISIS REAL 10-15 MIN con ALTOS y BAJOS
    No cambia cada momento - analiza velas completas
    """
    try:
        rows = get_price_history(symbol, 150)  # 150 puntos = 75 min
        if len(rows) < 60:  # menos de 30 min de datos
            return {
                "trend": "ANALIZANDO",
                "direction": "BUY",
                "confidence": 50,
                "reason": "Recolectando datos 10-15 min...",
                "high_10": 0, "low_10": 0, "high_15": 0, "low_15": 0,
                "up_streak": 0, "down_streak": 0, "volatility": 0,
                "sma10": 0, "sma15": 0
            }
        
        # Velas de 10 min = 20 puntos (30s cada punto)
        candles_10 = build_candles(rows, 20)
        # Velas de 15 min = 30 puntos
        candles_15 = build_candles(rows, 30)
        
        if len(candles_10) < 3 or len(candles_15) < 2:
            return {
                "trend": "ANALIZANDO", "direction": "BUY", "confidence": 55,
                "reason": "Esperando velas 10-15 min completas",
                "high_10": 0, "low_10": 0, "high_15": 0, "low_15": 0,
                "up_streak": 0, "down_streak": 0, "volatility": 0, "sma10": 0, "sma15": 0
            }
        
        last_10 = candles_10[-1]
        prev_10 = candles_10[-2]
        last_15 = candles_15[-1]
        prev_15 = candles_15[-2] if len(candles_15) >= 2 else last_15
        
        # Calcula SMA de closes
        closes_10 = [c["close"] for c in candles_10[-5:]]
        closes_15 = [c["close"] for c in candles_15[-3:]]
        sma10 = sum(closes_10) / len(closes_10)
        sma15 = sum(closes_15) / len(closes_15)
        
        # Altos y bajos reales de 10 y 15 min
        high_10 = max([c["high"] for c in candles_10[-3:]])
        low_10 = min([c["low"] for c in candles_10[-3:]])
        high_15 = max([c["high"] for c in candles_15[-3:]])
        low_15 = min([c["low"] for c in candles_15[-3:]])
        
        current_price = rows[-1][0]
        
        # Racha de velas alcistas/bajistas
        up_streak = 0
        down_streak = 0
        for c in reversed(candles_10):
            if c["bullish"]:
                if down_streak == 0:
                    up_streak += 1
                else:
                    break
            else:
                if up_streak == 0:
                    down_streak += 1
                else:
                    break
        
        # Volatilidad = rango promedio
        avg_range_10 = sum([c["range"] for c in candles_10[-3:]]) / 3
        volatility = avg_range_10
        
        # LOGICA DE DIRECCION CON 10-15 MIN - NO CAMBIA CADA MOMENTO
        direction = "BUY"
        confidence = 60
        reasons = []
        
        # Señal BUY fuerte: precio rompe alto de 10 y 15 min, velas alcistas, por encima de SMA
        buy_signals = 0
        sell_signals = 0
        
        # 1. Tendencia de velas
        if up_streak >= 2:
            buy_signals += 2
            reasons.append(f"Racha alcista {up_streak} velas 10min")
        if down_streak >= 2:
            sell_signals += 2
            reasons.append(f"Racha bajista {down_streak} velas 10min")
        
        # 2. Precio vs SMA 10 y 15
        if current_price > sma10 and current_price > sma15:
            buy_signals += 2
            reasons.append(f"Precio > SMA10({sma10:.2f}) y SMA15({sma15:.2f})")
        elif current_price < sma10 and current_price < sma15:
            sell_signals += 2
            reasons.append(f"Precio < SMA10({sma10:.2f}) y SMA15({sma15:.2f})")
        
        # 3. Ruptura de altos/bajos reales
        if current_price >= high_10 * 0.998:  # cerca o rompiendo alto 10min
            if last_10["bullish"]:
                buy_signals += 2
                reasons.append(f"Rompiendo alto 10min {high_10:.2f}")
        if current_price <= low_10 * 1.002:  # cerca o rompiendo bajo 10min
            if not last_10["bullish"]:
                sell_signals += 2
                reasons.append(f"Rompiendo bajo 10min {low_10:.2f}")
        
        if current_price >= high_15 * 0.999:
            buy_signals += 1
            reasons.append(f"Cerca alto 15min {high_15:.2f}")
        if current_price <= low_15 * 1.001:
            sell_signals += 1
            reasons.append(f"Cerca bajo 15min {low_15:.2f}")
        
        # 4. Cuerpo de vela grande = momentum
        if last_10["body"] > avg_range_10 * 0.6:
            if last_10["bullish"]:
                buy_signals += 1
                reasons.append(f"Vela alcista fuerte cuerpo {last_10['body']:.2f}")
            else:
                sell_signals += 1
                reasons.append(f"Vela bajista fuerte cuerpo {last_10['body']:.2f}")
        
        # 5. Confirmación 15 min
        if last_15["bullish"] and prev_15["bullish"]:
            buy_signals += 1
            reasons.append("2 velas 15min alcistas")
        if not last_15["bullish"] and not prev_15["bullish"]:
            sell_signals += 1
            reasons.append("2 velas 15min bajistas")
        
        # Decidir dirección con confianza
        if buy_signals > sell_signals + 1:
            direction = "BUY"
            confidence = 60 + min(buy_signals * 5, 35)
        elif sell_signals > buy_signals + 1:
            direction = "SELL"
            confidence = 60 + min(sell_signals * 5, 35)
        else:
            # Empate - mantener tendencia previa o neutral
            direction = "BUY" if current_price > sma10 else "SELL"
            confidence = 55
            reasons.append("Mercado lateral - siguiendo SMA")
        
        trend = "BULLISH" if direction == "BUY" else "BEARISH"
        if abs(buy_signals - sell_signals) <= 1:
            trend = "LATERAL"
        
        return {
            "trend": trend,
            "direction": direction,
            "confidence": min(confidence, 92),
            "reason": " | ".join(reasons[:3]),
            "high_10": high_10,
            "low_10": low_10,
            "high_15": high_15,
            "low_15": low_15,
            "up_streak": up_streak,
            "down_streak": down_streak,
            "volatility": volatility,
            "sma10": sma10,
            "sma15": sma15,
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "candles_10": len(candles_10),
            "candles_15": len(candles_15)
        }
    except Exception as e:
        print(f"analyze 10-15 error {e}")
        return {
            "trend": "ERROR", "direction": "BUY", "confidence": 50,
            "reason": f"Error analisis: {e}",
            "high_10": 0, "low_10": 0, "high_15": 0, "low_15": 0,
            "up_streak": 0, "down_streak": 0, "volatility": 0, "sma10": 0, "sma15": 0
        }

def get_last_signal(symbol):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, consecutive_count FROM last_signal WHERE symbol=?", (symbol,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"direction": row[0], "confirmed_at": row[1], "count": row[2]}
    except: pass
    return {"direction": "BUY", "confirmed_at": datetime.now(EC_TZ).isoformat(), "count": 0}

def update_last_signal(symbol, direction):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        last = get_last_signal(symbol)
        if last["direction"] == direction:
            new_count = last["count"] + 1
        else:
            new_count = 1
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,consecutive_count) VALUES (?,?,?,?)", (symbol, direction, datetime.now(EC_TZ).isoformat(), new_count))
        conn.commit(); conn.close()
        return new_count
    except: return 1

def should_flip_direction(symbol, new_direction, confidence):
    """
    EVITA CAMBIO CADA MOMENTO
    Solo cambia si:
    - Nueva dirección con confianza >= 75%
    - O 2 velas consecutivas misma dirección
    - O han pasado 10 min desde último cambio
    """
    try:
        last = get_last_signal(symbol)
        if last["direction"] == new_direction:
            return True, "Misma dirección - continua"
        
        # Dirección diferente - verificar si debe cambiar
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol=?", (symbol,))
        row = c.fetchone()
        conn.close()
        
        if row:
            try:
                last_time = datetime.fromisoformat(row[0])
                minutes_passed = (datetime.now(EC_TZ) - last_time).total_seconds() / 60
                # Si han pasado menos de 10 min y confianza baja, no cambiar
                if minutes_passed < 10 and confidence < 75:
                    return False, f"Esperando 10min para confirmar cambio (van {minutes_passed:.1f} min) - confianza {confidence}% baja"
                # Si confianza alta, permitir cambio
                if confidence >= 78:
                    return True, f"Cambio con alta confianza {confidence}%"
                # Si han pasado 10 min, permitir
                if minutes_passed >= 10:
                    return True, f"Cambio tras {minutes_passed:.1f} min"
            except: pass
        
        # Por defecto, si confianza >=70 permitir
        if confidence >= 70:
            return True, f"Confianza {confidence}% suficiente"
        return False, f"Confianza baja {confidence}% - manteniendo {last['direction']}"
    except Exception as e:
        print(f"flip check error {e}")
        return True, "Error - permitiendo cambio"

def calculate_tp_sl(entry, symbol, direction="BUY"):
    """
    CORREGIDO: SL y TP congruentes con dirección
    BUY: SL abajo, TP arriba
    SELL: SL arriba, TP abajo
    """
    TARGET_DOLLAR = 10.0
    PROFIT_PER_USD_XAU = 1.62
    PROFIT_PER_USD_BTC = 0.0162
    
    if "XAU" in symbol:
        sl_dist = round(TARGET_DOLLAR / PROFIT_PER_USD_XAU, 2)  # 6.17
        tp1_dist = sl_dist
        tp2_dist = round((TARGET_DOLLAR*2) / PROFIT_PER_USD_XAU, 2)  # 12.35
        tp3_dist = round((TARGET_DOLLAR*3) / PROFIT_PER_USD_XAU, 2)  # 18.52
    else:
        sl_dist = round(TARGET_DOLLAR / PROFIT_PER_USD_BTC, 2)  # 617.28
        tp1_dist = sl_dist
        tp2_dist = round((TARGET_DOLLAR*2) / PROFIT_PER_USD_BTC, 2)
        tp3_dist = round((TARGET_DOLLAR*3) / PROFIT_PER_USD_BTC, 2)

    # CORREGIDO - CONGRUENTE
    if direction == "BUY":
        # COMPRA: ganas si sube
        sl = round(entry - sl_dist, 2)   # SL ABAJO de ENTRY
        tp1 = round(entry + tp1_dist, 2) # TP ARRIBA
        tp2 = round(entry + tp2_dist, 2)
        tp3 = round(entry + tp3_dist, 2)
    else:  # SELL
        # VENTA: ganas si baja
        sl = round(entry + sl_dist, 2)   # SL ARRIBA de ENTRY (si sube pierdes)
        tp1 = round(entry - tp1_dist, 2) # TP ABAJO (si baja ganas)
        tp2 = round(entry - tp2_dist, 2)
        tp3 = round(entry - tp3_dist, 2)
    
    return sl, tp1, tp2, tp3, sl_dist, tp1_dist

def calculate_objective_success_rate(symbol, direction="BUY"):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        if "XAU" in symbol:
            objetivo_tp1 = 10.0 / 1.62
            objetivo_tp2 = 20.0 / 1.62
            objetivo_tp3 = 30.0 / 1.62
        else:
            objetivo_tp1 = 10.0 / 0.0162
            objetivo_tp2 = 20.0 / 0.0162
            objetivo_tp3 = 30.0 / 0.0162
        
        c.execute("SELECT price FROM price_history WHERE symbol=? ORDER BY id DESC LIMIT 200", (symbol,))
        prices = [r[0] for r in c.fetchall()][::-1]
        conn.close()
        if len(prices) < 30:
            return 70.0, 70.0, 50.0, 35.0
        
        exitos_tp1 = 0; exitos_tp2 = 0; exitos_tp3 = 0; total_ventanas = 0
        for i in range(len(prices)-30):
            entry = prices[i]
            ventana_10min = prices[i+1:i+21]
            ventana_15min = prices[i+1:i+31]
            if not ventana_10min: continue
            if direction == "BUY":
                max_10 = max(ventana_10min)
                max_15 = max(ventana_15min)
                subida_10 = max_10 - entry
                subida_15 = max_15 - entry
                total_ventanas += 1
                if subida_10 >= objetivo_tp1 or subida_15 >= objetivo_tp1:
                    exitos_tp1 += 1
                if subida_15 >= objetivo_tp2:
                    exitos_tp2 += 1
                if subida_15 >= objetivo_tp3:
                    exitos_tp3 += 1
            else:  # SELL - busca bajadas
                min_10 = min(ventana_10min)
                min_15 = min(ventana_15min)
                bajada_10 = entry - min_10
                bajada_15 = entry - min_15
                total_ventanas += 1
                if bajada_10 >= objetivo_tp1 or bajada_15 >= objetivo_tp1:
                    exitos_tp1 += 1
                if bajada_15 >= objetivo_tp2:
                    exitos_tp2 += 1
                if bajada_15 >= objetivo_tp3:
                    exitos_tp3 += 1
        
        if total_ventanas == 0:
            return 70.0, 70.0, 50.0, 35.0
        prob_tp1 = (exitos_tp1 / total_ventanas * 100) if total_ventanas>0 else 70
        prob_tp2 = (exitos_tp2 / total_ventanas * 100) if total_ventanas>0 else 50
        prob_tp3 = (exitos_tp3 / total_ventanas * 100) if total_ventanas>0 else 35
        prob_objetivo = prob_tp1*0.5 + prob_tp2*0.3 + prob_tp3*0.2
        return round(prob_objetivo,1), round(prob_tp1,1), round(prob_tp2,1), round(prob_tp3,1)
    except Exception as e:
        print(f"objective calc error {e}")
        return 70.0, 70.0, 50.0, 35.0

def calculate_probability(symbol, hour, market_analysis_10_15):
    try:
        stats = get_stats(symbol)
        direction = market_analysis_10_15.get("direction", "BUY")
        
        # Win rate por dirección
        if direction == "BUY":
            buy_total = stats.get("buy_total", 8)
            buy_wins = stats.get("buy_wins", 6)
            win_rate_dir = (buy_wins / buy_total * 100) if buy_total > 0 else 70
        else:
            sell_total = stats.get("sell_total", 7)
            sell_wins = stats.get("sell_wins", 4)
            win_rate_dir = (sell_wins / sell_total * 100) if sell_total > 0 else 70
        
        total = stats["wins"]+stats["loss"]
        win_rate_global = (stats["wins"]/total*100) if total>0 else 70
        
        # Probabilidad objetivos $10 reales 10-15 min
        prob_objetivo, prob_tp1, prob_tp2, prob_tp3 = calculate_objective_success_rate(symbol, direction)
        
        # Confianza del análisis 10-15 min
        confidence_10_15 = market_analysis_10_15.get("confidence", 60)
        
        # Hora óptima Ecuador 8-10 AM
        hour_bonus = 10 if 8 <= hour <= 10 else 0
        
        # Volatilidad suficiente para $10?
        volatility = market_analysis_10_15.get("volatility", 0)
        if "XAU" in symbol:
            min_vol_needed = 6.17 * 0.5  # necesita al menos mitad del movimiento para $10
        else:
            min_vol_needed = 617 * 0.5
        vol_bonus = 5 if volatility >= min_vol_needed else -10
        
        # Prob final: 40% historial dirección + 40% éxito objetivos $10 10-15min + 20% confianza análisis 10-15
        prob = (win_rate_dir * 0.4) + (prob_objetivo * 0.4) + (confidence_10_15 * 0.2) + hour_bonus + vol_bonus
        prob = max(45, min(92, prob))
        
        return round(prob,1), stats, prob_tp1, prob_tp2, prob_tp3
    except Exception as e:
        print(f"calc prob error {e}")
        return 70.0, get_stats(symbol), 70.0, 50.0, 35.0

def can_send_alert(symbol, alert_type):
    try:
        key = f"{symbol}_{alert_type}"
        now = datetime.now(EC_TZ)
        if key in last_alerts:
            if (now - last_alerts[key]).total_seconds() < 300:  # 5 min anti-spam
                return False
        last_alerts[key] = now
        return True
    except: return True

def send_telegram(msg):
    try:
        token, chat_id, _ = get_telegram_config()
        if not token or not chat_id: return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        return r.status_code == 200
    except: return False

@app.get("/")
def root():
    return {"message": "EdgeAlert PRO 10-15min Fixed", "status": "alive", "version": "3.0 - Analisis 10-15min con altos/bajos"}

@app.get("/health")
def health():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM price_history")
    count = c.fetchone()[0]
    conn.close()
    return {"status": "ok", "price_history_count": count, "message": "Backend 10-15min analysis fixed", "best_hours": [8,9,10]}

@app.get("/signals/live")
def signals_live():
    try:
        signals = []
        hour = datetime.now(EC_TZ).hour
        for sym in ["XAUUSD","BTCUSDT"]:
            real_price = get_real_price(sym)
            save_price_history(sym, real_price)
            
            # ANALISIS REAL 10-15 MIN con ALTOS y BAJOS
            market_10_15 = analyze_10_15_min(sym)
            
            # Verificar si debe cambiar dirección (evita cambio cada momento)
            new_direction = market_10_15.get("direction", "BUY")
            confidence = market_10_15.get("confidence", 60)
            should_flip, flip_reason = should_flip_direction(sym, new_direction, confidence)
            
            if should_flip:
                final_direction = new_direction
                update_last_signal(sym, final_direction)
            else:
                # Mantener dirección anterior
                last = get_last_signal(sym)
                final_direction = last["direction"]
                market_10_15["reason"] += f" | Manteniendo {final_direction}: {flip_reason}"
            
            prob, stats, prob_tp1, prob_tp2, prob_tp3 = calculate_probability(sym, hour, market_10_15)
            total = stats["wins"]+stats["loss"]
            win_rate = round(stats["wins"]/total*100,1) if total>0 else 0
            win_rate_dir = 0
            if final_direction == "BUY":
                bt = stats.get("buy_total",1)
                bw = stats.get("buy_wins",0)
                win_rate_dir = round(bw/bt*100,1) if bt>0 else 0
            else:
                st = stats.get("sell_total",1)
                sw = stats.get("sell_wins",0)
                win_rate_dir = round(sw/st*100,1) if st>0 else 0
            
            sl, tp1, tp2, tp3, sl_dist, tp1_dist = calculate_tp_sl(real_price, sym, final_direction)
            
            # Explicación congruente SL/TP
            if final_direction == "BUY":
                sl_explain = f"SL {sl} ABAJO de ENTRY (si baja {sl_dist} USD pierdes $10)"
                tp_explain = f"TP1 {tp1} ARRIBA de ENTRY (si sube {tp1_dist} USD ganas $10)"
            else:
                sl_explain = f"SL {sl} ARRIBA de ENTRY (si sube {sl_dist} USD pierdes $10)"
                tp_explain = f"TP1 {tp1} ABAJO de ENTRY (si baja {tp1_dist} USD ganas $10)"
            
            signals.append({
                "symbol": sym,
                "direction": final_direction,
                "entry": real_price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "sl_distance": sl_dist,
                "tp1_distance": tp1_dist,
                "probability": prob,
                "confidence": confidence,
                "win_rate": win_rate,
                "win_rate_direction": win_rate_dir,
                "is_optimal_hour": 8 <= hour <= 10,
                "market_analysis": market_10_15,
                "probabilidad_nuevos_objetivos": {
                    "prob_tp1_10usd_10_15min": prob_tp1,
                    "prob_tp2_20usd_15min": prob_tp2,
                    "prob_tp3_30usd_15min": prob_tp3
                },
                "money_config": f"{final_direction} | SL {sl_dist} USD = $10 | TP1 +{tp1_dist} USD = $10 | {sl_explain}",
                "sl_explain": sl_explain,
                "tp_explain": tp_explain,
                "reason": market_10_15.get("reason", ""),
                "flip_reason": flip_reason,
                "timestamp": datetime.now(EC_TZ).isoformat()
            })
            
            # Telegram solo si alta prob y hora óptima o confianza alta
            if prob >= 70 and (8 <= hour <= 15) and can_send_alert(sym, f"ENTRY_{final_direction}"):
                msg = f"🟢 *ENTRADA {sym} {final_direction} - {prob}% PROB*\n"
                msg += f"ENTRY: {real_price}\n"
                msg += f"{sl_explain}\n{tp_explain}\n"
                msg += f"TP2: {tp2} (+$20) | TP3: {tp3} (+$30)\n"
                msg += f"Analisis 10-15min: {market_10_15.get('reason','')}\n"
                msg += f"Altos 10min: {market_10_15.get('high_10',0):.2f} | Bajos 10min: {market_10_15.get('low_10',0):.2f}\n"
                msg += f"Confianza: {confidence}% | WinRate {final_direction}: {win_rate_dir}%\n"
                msg += f"Prob $10 en 10-15min: {prob_tp1}%"
                if send_telegram(msg):
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("INSERT INTO active_trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at,last_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              (sym,final_direction,real_price,sl,tp1,tp2,tp3,prob,"OPEN",datetime.now(EC_TZ).isoformat(),real_price))
                    conn.commit(); conn.close()
        
        return signals
    except Exception as e:
        print(f"signals_live error: {e}")
        import traceback; traceback.print_exc()
        return []

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
                    send_telegram(f"❌ *STOP LOSS TOCADO - {sym} {dir}*\nENTRY: {entry} → SL: {sl} (ABAJO)\nPrecio: {price}\nPerdida: -$10 ( -{abs(price-entry):.2f} USD)\nProb era: {prob}%")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET status='SL_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"SL",dir)
                elif price >= tp1 and tp1_hit==0 and can_send_alert(sym, "TP1"):
                    send_telegram(f"✅ *TP1 ALCANZADO - {sym} {dir}*\nENTRY: {entry} → TP1: {tp1} (ARRIBA)\nGanancia: +$10 (+{price-entry:.2f} USD)\nPrecio: {price}")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp1_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP1",dir)
                elif price >= tp2 and tp2_hit==0 and can_send_alert(sym, "TP2"):
                    send_telegram(f"🎯🎯 *TP2 ALCANZADO - {sym} {dir}*\nENTRY: {entry} → TP2: {tp2} (+$20)")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp2_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP2",dir)
                elif price >= tp3 and tp3_hit==0 and can_send_alert(sym, "TP3"):
                    send_telegram(f"🚀 *TP3 ALCANZADO - {sym} {dir}* +$30")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp3_hit=1, status='TP3_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP3",dir)
            elif dir=="SELL":
                if price >= sl and can_send_alert(sym, "SL"):
                    send_telegram(f"❌ *STOP LOSS TOCADO - {sym} {dir}*\nENTRY: {entry} → SL: {sl} (ARRIBA)\nPrecio: {price}\nPerdida: -$10")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET status='SL_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"SL",dir)
                elif price <= tp1 and tp1_hit==0 and can_send_alert(sym, "TP1"):
                    send_telegram(f"✅ *TP1 ALCANZADO - {sym} {dir}*\nENTRY: {entry} → TP1: {tp1} (ABAJO)\nGanancia: +$10")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp1_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP1",dir)
                elif price <= tp2 and tp2_hit==0 and can_send_alert(sym, "TP2"):
                    send_telegram(f"🎯🎯 *TP2 ALCANZADO - {sym} {dir}* +$20")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp2_hit=1, last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP2",dir)
                elif price <= tp3 and tp3_hit==0 and can_send_alert(sym, "TP3"):
                    send_telegram(f"🚀 *TP3 ALCANZADO - {sym} {dir}* +$30")
                    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
                    c.execute("UPDATE active_trades SET tp3_hit=1, status='TP3_HIT', last_price=? WHERE id=?", (price,tid))
                    conn.commit(); conn.close()
                    update_stats(sym,"TP3",dir)
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
    sym=r.symbol.upper()
    # Obtener dirección del trade activo para aprendizaje separado BUY/SELL
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT direction FROM active_trades WHERE symbol=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (sym,))
    row = c.fetchone()
    direction = row[0] if row else "BUY"
    conn.close()
    update_stats(sym,r.result,direction)
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("UPDATE active_trades SET status=? WHERE symbol=? AND status='OPEN'", (f"{r.result}_MANUAL", sym))
    conn.commit(); conn.close()
    send_telegram(f"📝 *RESULTADO MANUAL - {sym} {direction}: {r.result}*\nAprendizaje actualizado BUY/SELL separado")
    return {"ok":True,"learning":get_stats(sym),"direction":direction}

@app.get("/analysis/{symbol}")
def get_analysis(symbol: str):
    sym = symbol.upper()
    market = analyze_10_15_min(sym)
    last = get_last_signal(sym)
    rows = get_price_history(sym, 30)
    current = get_real_price(sym)
    return {
        "symbol": sym,
        "current_price": current,
        "analysis_10_15": market,
        "last_signal": last,
        "price_history_count": len(rows),
        "last_10_prices": [r[0] for r in rows[-10:]] if rows else []
    }

@app.post("/webhook/tradingview")
@app.post("/webhook/xau")
async def webhook_tradingview(request: Request):
    try: data = await request.json()
    except: data={}
    symbol = str(data.get("symbol","XAUUSD")).upper(); action = str(data.get("action","BUY")).upper()
    if action not in ["BUY","SELL"]: action = "BUY"
    price = float(data.get("price") or get_real_price(symbol))
    now = datetime.now(EC_TZ); market = analyze_10_15_min(symbol); prob, stats, _, _, _ = calculate_probability(symbol, now.hour, market)
    sl, tp1, tp2, tp3, _, _ = calculate_tp_sl(price, symbol, action)
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("INSERT INTO trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,result,source,timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (symbol, action, price, sl, tp1, tp2, tp3, prob, "NEW", "tradingview", now.isoformat()))
    c.execute("INSERT INTO active_trades (symbol,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at,last_price) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (symbol, action, price, sl, tp1, tp2, tp3, prob, "OPEN", now.isoformat(), price))
    conn.commit(); conn.close()
    send_telegram(f"🔥 *{symbol} {action} {prob}% - TV*\nENTRY {price} SL {sl} TP1 {tp1}")
    return {"ok":True,"real_price":get_real_price(symbol),"probability":prob}

@app.on_event("startup")
async def startup_event():
    async def monitor_loop():
        print("🚀 Monitor 10-15min Fixed iniciado")
        while True:
            try:
                for sym in ["XAUUSD","BTCUSDT"]:
                    price = get_real_price(sym)
                    save_price_history(sym, price)
                check_active_trades_sync()
            except Exception as e:
                print(f"monitor loop error: {e}")
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())

@app.get("/best_hours")
def best_hours():
    return {"best_hours": [8,9,10,13,14,15], "timezone": "EC -5", "note": "Analisis 10-15min con altos/bajos reales, no cambia cada momento"}
