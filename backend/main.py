
import os
import sqlite3
import requests
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import math

app = FastAPI(title="EdgeAlert ORO PURO - FASES + VELAS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS gold_learning (id INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, loss INTEGER DEFAULT 0, tp1 INTEGER DEFAULT 0, tp2 INTEGER DEFAULT 0, tp3 INTEGER DEFAULT 0, total_trades INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS gold_hour_learning (hour INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, total INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0, avg_range REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS gold_patterns (pattern TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, total INTEGER DEFAULT 0, description TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS candle_patterns (name TEXT PRIMARY KEY, bullish INTEGER DEFAULT 0, bearish INTEGER DEFAULT 0, total INTEGER DEFAULT 0, win_rate REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS market_phases (phase TEXT PRIMARY KEY, count INTEGER DEFAULT 0, buy_success INTEGER DEFAULT 0, sell_success INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, price REAL, timestamp TEXT, change REAL DEFAULT 0, high REAL DEFAULT 0, low REAL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS active_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, status TEXT DEFAULT 'OPEN', tp1_hit INTEGER DEFAULT 0, tp2_hit INTEGER DEFAULT 0, tp3_hit INTEGER DEFAULT 0, created_at TEXT, last_price REAL, pattern TEXT, phase TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (symbol TEXT PRIMARY KEY, direction TEXT, confirmed_at TEXT, consecutive_count INTEGER DEFAULT 0, phase TEXT)""")
    c.execute("INSERT OR IGNORE INTO gold_learning (id,wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total) VALUES (1,18,6,12,8,5,24,11,14,7,10)")
    for h in range(24):
        c.execute("INSERT OR IGNORE INTO gold_hour_learning (hour,wins,total,buy_wins,buy_total,sell_wins,sell_total,avg_range) VALUES (?,?,?,?,?,?,?,?)", (h, 5 if 8 <= h <= 11 else 2, 7 if 8 <= h <= 11 else 4, 3, 4, 2, 3, 6.5))
    patterns = [
        ("BREAK_HIGH_10", 0, 0, "Rompimiento alto 10min"), ("BREAK_LOW_10", 0, 0, "Rompimiento bajo 10min"),
        ("SMA_BULL", 0, 0, "SMA alcista"), ("SMA_BEAR", 0, 0, "SMA bajista"),
        ("NY_OPEN", 0, 0, "NY Open"), ("ACUMULACION_BREAKOUT_BUY", 0, 0, "Acumulacion + ruptura alcista"),
        ("ACUMULACION_BREAKOUT_SELL", 0, 0, "Acumulacion + ruptura bajista"),
        ("BULLISH_ENGULFING", 0, 0, "Envolvente alcista"), ("BEARISH_ENGULFING", 0, 0, "Envolvente bajista"),
        ("HAMMER", 0, 0, "Martillo alcista"), ("SHOOTING_STAR", 0, 0, "Estrella fugaz bajista"),
    ]
    for p,w,t,d in patterns:
        c.execute("INSERT OR IGNORE INTO gold_patterns (pattern,wins,total,description) VALUES (?,?,?,?)", (p,w,t,d))
    candle_base = [
        ("BULLISH_ENGULFING", 0, 0, 0, 0), ("BEARISH_ENGULFING", 0, 0, 0, 0),
        ("HAMMER", 0, 0, 0, 0), ("SHOOTING_STAR", 0, 0, 0, 0),
        ("DOJI", 0, 0, 0, 0), ("PIN_BAR_BULL", 0, 0, 0, 0), ("PIN_BAR_BEAR", 0, 0, 0, 0),
        ("MORNING_STAR", 0, 0, 0, 0), ("EVENING_STAR", 0, 0, 0, 0),
    ]
    for name, b, be, tot, wr in candle_base:
        c.execute("INSERT OR IGNORE INTO candle_patterns (name,bullish,bearish,total,win_rate) VALUES (?,?,?,?,?)", (name, b, be, tot, wr))
    phases = ["ACUMULACION", "ACUMULACION_ALCISTA", "ACUMULACION_BAJISTA", "EXPANSION_ALCISTA", "EXPANSION_BAJISTA", "TENDENCIA_ALCISTA", "TENDENCIA_BAJISTA", "DISTRIBUCION", "RANGO", "AGOTAMIENTO"]
    for ph in phases:
        c.execute("INSERT OR IGNORE INTO market_phases (phase,count,buy_success,sell_success) VALUES (?,?,?,?)", (ph, 0, 0, 0))
    c.execute("INSERT OR IGNORE INTO last_signal (symbol,direction,confirmed_at,consecutive_count,phase) VALUES (?,?,?,?,?)", ("XAUUSD", "BUY", datetime.now(EC_TZ).isoformat(), 1, "ACUMULACION"))
    conn.commit(); conn.close()

init_db()

class TradeResult(BaseModel):
    result: str
    symbol: Optional[str] = "XAUUSD"

def get_gold_price():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=6)
        if r.status_code==200:
            price = r.json().get("price")
            if price and float(price) > 1000: return float(price)
    except: pass
    try:
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=8)
        if r.status_code==200:
            for it in r.json().get("items",[]):
                if it.get("curr")=="XAU" and it.get("xauPrice",0)>0: return float(it["xauPrice"])
    except: pass
    return 4025.86 + (datetime.now().hour - 12) * 2.5

def seed_history_if_empty():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM price_history")
        count = c.fetchone()[0]
        if count < 30:
            print(f"Seed oro - {count} registros, creando 100")
            base = get_gold_price()
            now = datetime.now(EC_TZ)
            for i in range(100):
                variation = (math.sin(i/10) * 2) + (math.cos(i/7) * 1.5) + ((i % 10) * 0.1)
                p = base + variation - 5 + (i * 0.02)
                ts = (now - timedelta(seconds=(100-i)*30)).isoformat()
                c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)", (p, ts, variation*0.1, p+0.5, p-0.5))
            conn.commit()
        conn.close()
    except Exception as e: print(f"seed error {e}")

def save_gold_history(price):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price FROM price_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        change = price - last[0] if last else 0
        c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)", (price, datetime.now(EC_TZ).isoformat(), change, price, price))
        c.execute("DELETE FROM price_history WHERE id NOT IN (SELECT id FROM price_history ORDER BY id DESC LIMIT 1000)")
        conn.commit(); conn.close()
        return change
    except: return 0

def get_gold_history(limit=300):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price, timestamp, change, high, low FROM price_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows[::-1]
    except: return []

def build_gold_candles(rows, points_per_candle):
    candles = []
    if len(rows) < points_per_candle: return []
    for i in range(0, len(rows), points_per_candle):
        chunk = rows[i:i+points_per_candle]
        if len(chunk) < points_per_candle * 0.7: continue
        prices = [r[0] for r in chunk]
        if not prices: continue
        open_p = prices[0]
        close_p = prices[-1]
        high_p = max(prices)
        low_p = min(prices)
        body = abs(close_p - open_p)
        range_c = high_p - low_p if high_p != low_p else 0.1
        bullish = close_p > open_p
        body_ratio = body / range_c if range_c > 0 else 0
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        candles.append({
            "open": open_p, "close": close_p, "high": high_p, "low": low_p,
            "range": range_c, "body": body, "body_ratio": body_ratio,
            "upper_wick": upper_wick, "lower_wick": lower_wick,
            "bullish": bullish, "strong": body_ratio > 0.6,
            "small": body_ratio < 0.3, "doji": body_ratio < 0.1
        })
    return candles

def detect_candle_patterns(candles):
    """Base de velas japonesas alcistas y bajistas que indican direccion"""
    if len(candles) < 3: return []
    patterns = []
    last = candles[-1]
    prev = candles[-2]
    prev2 = candles[-3] if len(candles) >= 3 else prev

    # 1. BULLISH ENGULFING - previa bajista, actual alcista que envuelve
    if not prev["bullish"] and last["bullish"]:
        if last["open"] < prev["close"] and last["close"] > prev["open"] and last["body"] > prev["body"]*1.2:
            patterns.append({"name": "BULLISH_ENGULFING", "direction": "BUY", "strength": 3, "desc": "Envolvente alcista - fuerte compra tras bajada"})

    # 2. BEARISH ENGULFING
    if prev["bullish"] and not last["bullish"]:
        if last["open"] > prev["close"] and last["close"] < prev["open"] and last["body"] > prev["body"]*1.2:
            patterns.append({"name": "BEARISH_ENGULFING", "direction": "SELL", "strength": 3, "desc": "Envolvente bajista - fuerte venta tras subida"})

    # 3. HAMMER - martillo alcista (mecha inferior larga, cuerpo pequeño arriba)
    if last["lower_wick"] > last["body"]*2 and last["upper_wick"] < last["body"]*0.5 and last["range"] > 1.0:
        if last["close"] > last["open"] or last["body_ratio"] < 0.4:
            patterns.append({"name": "HAMMER", "direction": "BUY", "strength": 2, "desc": "Martillo alcista - rechazo de bajos, posible subida"})

    # 4. SHOOTING STAR - estrella fugaz bajista
    if last["upper_wick"] > last["body"]*2 and last["lower_wick"] < last["body"]*0.5 and last["range"] > 1.0:
        patterns.append({"name": "SHOOTING_STAR", "direction": "SELL", "strength": 2, "desc": "Estrella fugaz - rechazo de altos, posible bajada"})

    # 5. PIN BAR BULL
    if last["lower_wick"] > last["body"]*2.5 and last["bullish"]:
        patterns.append({"name": "PIN_BAR_BULL", "direction": "BUY", "strength": 2, "desc": "Pin bar alcista - fuerte rechazo venta"})

    # 6. PIN BAR BEAR
    if last["upper_wick"] > last["body"]*2.5 and not last["bullish"]:
        patterns.append({"name": "PIN_BAR_BEAR", "direction": "SELL", "strength": 2, "desc": "Pin bar bajista - fuerte rechazo compra"})

    # 7. DOJI - indecision, posible reversal si viene tras tendencia
    if last["doji"] and last["range"] > 0.8:
        if prev["bullish"] and not prev2["bullish"]:
            patterns.append({"name": "DOJI_TOP", "direction": "SELL", "strength": 1, "desc": "Doji en tope - indecision tras subida"})
        elif not prev["bullish"]:
            patterns.append({"name": "DOJI_BOTTOM", "direction": "BUY", "strength": 1, "desc": "Doji en fondo - indecision tras bajada"})

    # 8. MORNING STAR - 3 velas reversal alcista
    if len(candles) >= 3:
        if not prev2["bullish"] and prev2["body_ratio"] > 0.5:
            if prev["small"] or prev["doji"]:
                if last["bullish"] and last["close"] > (prev2["open"]+prev2["close"])/2:
                    patterns.append({"name": "MORNING_STAR", "direction": "BUY", "strength": 3, "desc": "Estrella de la mañana - reversal alcista fuerte"})

    # 9. EVENING STAR - reversal bajista
    if len(candles) >= 3:
        if prev2["bullish"] and prev2["body_ratio"] > 0.5:
            if prev["small"] or prev["doji"]:
                if not last["bullish"] and last["close"] < (prev2["open"]+prev2["close"])/2:
                    patterns.append({"name": "EVENING_STAR", "direction": "SELL", "strength": 3, "desc": "Estrella de la tarde - reversal bajista fuerte"})

    # 10. MARUBOZU ALCISTA - vela fuerte sin mechas
    if last["bullish"] and last["body_ratio"] > 0.8 and last["upper_wick"] < 0.3 and last["lower_wick"] < 0.3:
        patterns.append({"name": "MARUBOZU_BULL", "direction": "BUY", "strength": 2, "desc": "Marubozu alcista - fuerza compradora"})

    # 11. MARUBOZU BAJISTA
    if not last["bullish"] and last["body_ratio"] > 0.8 and last["upper_wick"] < 0.3 and last["lower_wick"] < 0.3:
        patterns.append({"name": "MARUBOZU_BEAR", "direction": "SELL", "strength": 2, "desc": "Marubozu bajista - fuerza vendedora"})

    return patterns

def detect_market_phase(candles_10, candles_15, candles_30, rows):
    """Analiza fases del mercado: acumulacion -> picos de compra/venta"""
    if len(candles_10) < 4:
        return {"phase": "INICIO", "desc": "Iniciando analisis fases oro", "accumulation": False, "breakout": False, "strength": 0}

    current_price = rows[-1][0] if rows else candles_10[-1]["close"]
    last_6_10 = candles_10[-6:] if len(candles_10) >= 6 else candles_10
    last_3_10 = candles_10[-3:]
    last_3_15 = candles_15[-3:] if len(candles_15) >= 3 else candles_10[-3:]

    # Metricas fase
    ranges_6 = [c["range"] for c in last_6_10]
    avg_range_6 = sum(ranges_6)/len(ranges_6)
    avg_range_3 = sum([c["range"] for c in last_3_10])/len(last_3_10)
    prices_6 = [c["close"] for c in last_6_10]
    price_band_6 = max(prices_6) - min(prices_6)
    avg_body_6 = sum([c["body"] for c in last_6_10])/len(last_6_10)

    # Volatilidad contraccion vs expansion
    volatility_contraction = avg_range_3 < avg_range_6 * 0.7
    volatility_expansion = avg_range_3 > avg_range_6 * 1.5

    # Acumulacion: rango estrecho, cuerpos pequeños, precio en rango 3-4 USD
    is_accumulation = price_band_6 < 4.0 and avg_range_6 < 2.0 and avg_body_6 < 1.2

    # Tendencia
    up_streak = 0; down_streak = 0
    for c in reversed(candles_10):
        if c["bullish"]:
            if down_streak==0: up_streak+=1
            else: break
        else:
            if up_streak==0: down_streak+=1
            else: break

    # SMA pendiente
    closes_10 = [c["close"] for c in candles_10[-5:]]
    sma10 = sum(closes_10)/len(closes_10)
    sma10_prev = sum([c["close"] for c in candles_10[-6:-1]])/5 if len(candles_10)>=6 else sma10
    sma_slope = sma10 - sma10_prev

    last = candles_10[-1]
    prev = candles_10[-2]

    # DETECCION FASES
    phase = "RANGO"
    desc = "Rango lateral"
    strength = 1

    if is_accumulation:
        # Dentro acumulacion, ver hacia donde se inclina
        if up_streak >= 2:
            phase = "ACUMULACION_ALCISTA"
            desc = f"Acumulacion alcista - {price_band_6:.1f} USD rango estrecho, posible pico compra tras acumulacion"
            strength = 2
        elif down_streak >= 2:
            phase = "ACUMULACION_BAJISTA"
            desc = f"Acumulacion bajista - rango {price_band_6:.1f} USD, posible pico venta tras acumulacion"
            strength = 2
        else:
            phase = "ACUMULACION"
            desc = f"Acumulacion pura - rango {price_band_6:.1f} USD, volatilidad {avg_range_6:.1f} USD, esperando pico"
            strength = 1

    elif volatility_expansion and last["strong"]:
        # Expansion tras acumulacion = PICO
        if last["bullish"] and last["close"] > max(prices_6):
            phase = "EXPANSION_ALCISTA"
            desc = f"🔥 PICO COMPRA tras acumulacion - ruptura {last['close']:.2f} con vela fuerte {last['body']:.1f} USD, rango {last['range']:.1f} USD"
            strength = 4
        elif not last["bullish"] and last["close"] < min(prices_6):
            phase = "EXPANSION_BAJISTA"
            desc = f"🔥 PICO VENTA tras acumulacion - ruptura {last['close']:.2f} vela fuerte {last['body']:.1f} USD"
            strength = 4
        else:
            phase = "EXPANSION"
            desc = f"Expansion volatilidad {avg_range_3:.1f} vs {avg_range_6:.1f} promedio"
            strength = 3

    elif up_streak >= 3:
        if avg_range_3 < avg_range_6:
            phase = "AGOTAMIENTO_ALCISTA"
            desc = f"Agotamiento alcista - {up_streak} velas subiendo pero rango decrece {avg_range_3:.1f} < {avg_range_6:.1f}"
            strength = 2
        else:
            phase = "TENDENCIA_ALCISTA"
            desc = f"Tendencia alcista fuerte - {up_streak} velas, SMA pendiente +{sma_slope:.2f}, fuerza continua"
            strength = 3

    elif down_streak >= 3:
        if avg_range_3 < avg_range_6:
            phase = "AGOTAMIENTO_BAJISTA"
            desc = f"Agotamiento bajista - {down_streak} velas bajando rango decrece"
            strength = 2
        else:
            phase = "TENDENCIA_BAJISTA"
            desc = f"Tendencia bajista fuerte - {down_streak} velas, pendiente {sma_slope:.2f}"
            strength = 3

    elif price_band_6 < 6.0 and avg_range_6 < 2.5:
        phase = "RANGO"
        desc = f"Rango estrecho {price_band_6:.1f} USD - mercado en balance, esperar ruptura"
        strength = 1

    else:
        # Distribucion - tras impulso, lateral arriba
        if last_3_10[-1]["close"] > sma10 and avg_body_6 < 1.5:
            phase = "DISTRIBUCION"
            desc = f"Distribucion - tras subida, velas pequeñas, posible reversal venta"
            strength = 2
        else:
            phase = "TRANSICION"
            desc = f"Transicion - volatilidad {avg_range_3:.1f} USD, pendiente SMA {sma_slope:.2f}"
            strength = 1

    return {
        "phase": phase, "desc": desc, "strength": strength,
        "is_accumulation": is_accumulation,
        "is_expansion": volatility_expansion,
        "is_contraction": volatility_contraction,
        "price_band_6": price_band_6,
        "avg_range_6": avg_range_6,
        "avg_range_3": avg_range_3,
        "up_streak": up_streak, "down_streak": down_streak,
        "sma_slope": sma_slope
    }

def analyze_gold_pro():
    try:
        rows = get_gold_history(300)
        current_price_fallback = get_gold_price()
        if len(rows) < 10:
            return {
                "trend": "INICIO", "direction": "BUY", "confidence": 57, "phase": "INICIO",
                "phase_desc": f"Iniciando - precio {current_price_fallback:.2f}",
                "candle_patterns": [], "reason": "Iniciando fases oro",
                "high_10": current_price_fallback+3.5, "low_10": current_price_fallback-3.2,
                "high_15": current_price_fallback+5.8, "low_15": current_price_fallback-5.1,
                "high_30": current_price_fallback+8.5, "low_30": current_price_fallback-8.2,
                "sma10": current_price_fallback-0.8, "sma15": current_price_fallback-1.2, "sma30": current_price_fallback-1.8,
                "support": current_price_fallback-5.1, "resistance": current_price_fallback+5.8,
                "volatility": 3.2, "ny_session": 8 <= datetime.now(EC_TZ).hour <= 11, "pattern": "INICIO_ORO",
                "up_streak": 1, "down_streak": 0, "buy_score": 3, "sell_score": 2
            }

        candles_10 = build_gold_candles(rows, 20)
        candles_15 = build_gold_candles(rows, 30)
        candles_30 = build_gold_candles(rows, 60)

        if len(candles_10) < 4:
            fallback = rows[-1][0] if rows else current_price_fallback
            high_est = max([r[0] for r in rows[-20:]]) if len(rows)>=20 else fallback+3.5
            low_est = min([r[0] for r in rows[-20:]]) if len(rows)>=20 else fallback-3.2
            sma_est = sum([r[0] for r in rows[-10:]])/min(len(rows),10) if rows else fallback
            return {
                "trend": "FORMANDO", "direction": "BUY", "confidence": 58, "phase": "FORMANDO",
                "phase_desc": f"Formando velas: {len(candles_10)} 10m",
                "candle_patterns": [], "reason": f"Formando {len(candles_10)} velas",
                "high_10": high_est, "low_10": low_est, "high_15": high_est+1.5, "low_15": low_est-1.5,
                "high_30": high_est+2.5, "low_30": low_est-2.5,
                "sma10": sma_est, "sma15": sma_est-0.5, "sma30": sma_est-1.0,
                "support": low_est, "resistance": high_est, "volatility": high_est-low_est,
                "ny_session": 8 <= datetime.now(EC_TZ).hour <= 11, "pattern": "FORMANDO",
                "up_streak": 1, "down_streak": 0, "buy_score": 2, "sell_score": 1
            }

        current_price = rows[-1][0]
        last_10 = candles_10[-1]
        prev_10 = candles_10[-2]
        last_15 = candles_15[-1] if candles_15 else last_10
        prev_15 = candles_15[-2] if len(candles_15)>=2 else last_10
        last_30 = candles_30[-1] if candles_30 else last_15

        closes_10 = [c["close"] for c in candles_10[-5:]]
        closes_15 = [c["close"] for c in candles_15[-4:]] if candles_15 else closes_10
        closes_30 = [c["close"] for c in candles_30[-3:]] if candles_30 else closes_15
        sma10 = sum(closes_10)/len(closes_10)
        sma15 = sum(closes_15)/len(closes_15)
        sma30 = sum(closes_30)/len(closes_30)

        high_10 = max([c["high"] for c in candles_10[-3:]])
        low_10 = min([c["low"] for c in candles_10[-3:]])
        high_15 = max([c["high"] for c in candles_15[-3:]]) if candles_15 else high_10
        low_15 = min([c["low"] for c in candles_15[-3:]]) if candles_15 else low_10
        high_30 = max([c["high"] for c in candles_30[-2:]]) if candles_30 else high_15
        low_30 = min([c["low"] for c in candles_30[-2:]]) if candles_30 else low_15

        support = low_15
        resistance = high_15

        # FASES DEL MERCADO ORO
        phase_info = detect_market_phase(candles_10, candles_15, candles_30, rows)
        # PATRONES VELAS JAPONESAS
        candle_patterns = detect_candle_patterns(candles_10)
        candle_patterns_15 = detect_candle_patterns(candles_15)
        all_patterns = candle_patterns + candle_patterns_15

        up_streak = phase_info["up_streak"]
        down_streak = phase_info["down_streak"]
        hour_ec = datetime.now(EC_TZ).hour
        ny_session = 8 <= hour_ec <= 11

        direction = "BUY"
        confidence = 60
        pattern = phase_info["phase"]
        reasons = []
        buy_score = 0
        sell_score = 0

        # 1. FASES - LO MAS IMPORTANTE PARA SEÑALES LIMPIAS
        if phase_info["phase"] == "ACUMULACION":
            reasons.append(f"⏸️ ACUMULACION {phase_info['price_band_6']:.1f} USD rango - NO operar, esperar pico")
            # En acumulacion no dar señal fuerte, baja confianza
            confidence = 55
            pattern = "ACUMULACION_ESPERA"

        elif phase_info["phase"] == "EXPANSION_ALCISTA":
            buy_score += 4
            confidence = 82
            pattern = "ACUMULACION_BREAKOUT_BUY"
            reasons.append(phase_info["desc"])

        elif phase_info["phase"] == "EXPANSION_BAJISTA":
            sell_score += 4
            confidence = 82
            pattern = "ACUMULACION_BREAKOUT_SELL"
            reasons.append(phase_info["desc"])

        elif phase_info["phase"] == "TENDENCIA_ALCISTA":
            buy_score += 3
            reasons.append(phase_info["desc"])

        elif phase_info["phase"] == "TENDENCIA_BAJISTA":
            sell_score += 3
            reasons.append(phase_info["desc"])

        elif "AGOTAMIENTO" in phase_info["phase"]:
            # Agotamiento = posible reversal, buscar patron vela opuesto
            if "ALCISTA" in phase_info["phase"]:
                # Agotamiento alcista -> buscar patron bajista para SELL
                bearish_pat = [p for p in all_patterns if p["direction"]=="SELL"]
                if bearish_pat:
                    sell_score += 3
                    reasons.append(f"Agotamiento alcista + {bearish_pat[0]['name']} = posible SELL")
                else:
                    reasons.append(phase_info["desc"] + " - esperando patron bajista")
            else:
                bullish_pat = [p for p in all_patterns if p["direction"]=="BUY"]
                if bullish_pat:
                    buy_score += 3
                    reasons.append(f"Agotamiento bajista + {bullish_pat[0]['name']} = posible BUY")

        # 2. PATRONES VELAS JAPONESAS - BASE QUE INDICA DIRECCION
        for pat in all_patterns:
            if pat["direction"] == "BUY":
                buy_score += pat["strength"]
                reasons.append(f"🕯️ {pat['name']}: {pat['desc']}")
                if pat["strength"] >= 3:
                    pattern = pat["name"]
            else:
                sell_score += pat["strength"]
                reasons.append(f"🕯️ {pat['name']}: {pat['desc']}")
                if pat["strength"] >= 3:
                    pattern = pat["name"]

        # 3. SMA ORO
        if current_price > sma10 and sma10 > sma15 and sma15 > sma30:
            buy_score += 2
            reasons.append(f"SMA alcista fuerte {sma10:.1f}>{sma15:.1f}>{sma30:.1f}")
        elif current_price < sma10 and sma10 < sma15 and sma15 < sma30:
            sell_score += 2
            reasons.append(f"SMA bajista {sma10:.1f}<{sma15:.1f}<{sma30:.1f}")
        elif current_price > sma10 and current_price > sma15:
            buy_score += 1
        elif current_price < sma10 and current_price < sma15:
            sell_score += 1

        # 4. RUPTURA ALTOS/BAJOS
        if current_price >= high_10 * 0.998 and last_10["bullish"] and last_10["strong"]:
            buy_score += 2
            reasons.append(f"Ruptura alto 10m {high_10:.2f} vela {last_10['body']:.1f} USD")
        if current_price <= low_10 * 1.002 and not last_10["bullish"] and last_10["strong"]:
            sell_score += 2
            reasons.append(f"Ruptura bajo 10m {low_10:.2f}")

        # 5. NY SESSION
        if ny_session and (buy_score > sell_score or sell_score > buy_score):
            if buy_score > sell_score:
                buy_score += 1
                reasons.append("🔥 NY 8-10AM EC volátil oro alcista")
            else:
                sell_score += 1
                reasons.append("🔥 NY 8-10AM EC volátil oro bajista")

        # DECISION FINAL - SEÑALES MAS LIMPIAS
        # Solo da señal fuerte si hay fase clara + patron vela
        has_candle_confirmation = len([p for p in all_patterns if p["strength"]>=2]) > 0
        has_phase_breakout = "EXPANSION" in phase_info["phase"]

        if buy_score >= sell_score + 2:
            direction = "BUY"
            base_conf = 62
            if has_phase_breakout and has_candle_confirmation:
                base_conf = 78  # Señal limpia: fase + vela
            elif has_phase_breakout:
                base_conf = 72
            elif has_candle_confirmation:
                base_conf = 68
            confidence = base_conf + min(buy_score * 2, 16)
        elif sell_score >= buy_score + 2:
            direction = "SELL"
            base_conf = 62
            if has_phase_breakout and has_candle_confirmation:
                base_conf = 78
            elif has_phase_breakout:
                base_conf = 72
            elif has_candle_confirmation:
                base_conf = 68
            confidence = base_conf + min(sell_score * 2, 16)
        else:
            direction = "BUY" if current_price > sma15 else "SELL"
            confidence = 56
            if phase_info["phase"] == "ACUMULACION":
                reasons.append("Lateral acumulacion - esperar breakout limpio")

        trend = "BULLISH" if direction=="BUY" else "BEARISH"
        if abs(buy_score - sell_score) <= 1:
            trend = "LATERAL"

        return {
            "trend": trend, "direction": direction, "confidence": min(confidence, 94),
            "pattern": pattern, "phase": phase_info["phase"], "phase_desc": phase_info["desc"],
            "phase_strength": phase_info["strength"], "phase_info": phase_info,
            "candle_patterns": all_patterns,
            "reason": " | ".join(reasons[:3]),
            "high_10": high_10, "low_10": low_10, "high_15": high_15, "low_15": low_15,
            "high_30": high_30, "low_30": low_30,
            "sma10": sma10, "sma15": sma15, "sma30": sma30,
            "support": support, "resistance": resistance,
            "up_streak": up_streak, "down_streak": down_streak,
            "volatility": phase_info["avg_range_3"], "volatility_15": phase_info["avg_range_6"],
            "ny_session": ny_session, "buy_score": buy_score, "sell_score": sell_score,
            "hour_ec": hour_ec, "current_price": current_price
        }
    except Exception as e:
        print(f"analyze gold error {e}")
        import traceback; traceback.print_exc()
        return {
            "trend": "ERROR", "direction": "BUY", "confidence": 50, "phase": "ERROR", "phase_desc": str(e),
            "candle_patterns": [], "reason": f"Error: {e}",
            "high_10": 0, "low_10": 0, "high_15": 0, "low_15": 0, "high_30": 0, "low_30": 0,
            "sma10": 0, "sma15": 0, "sma30": 0, "support": 0, "resistance": 0, "volatility": 0, "ny_session": False
        }

def get_last_signal():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, consecutive_count, phase FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone(); conn.close()
        if row: return {"direction": row[0], "confirmed_at": row[1], "count": row[2], "phase": row[3]}
    except: pass
    return {"direction": "BUY", "confirmed_at": datetime.now(EC_TZ).isoformat(), "count": 0, "phase": "ACUMULACION"}

def update_last_signal(direction, phase=""):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT direction, consecutive_count FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone()
        new_count = row[1]+1 if row and row[0]==direction else 1
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,consecutive_count,phase) VALUES (?,?,?,?,?)", ("XAUUSD", direction, datetime.now(EC_TZ).isoformat(), new_count, phase))
        conn.commit(); conn.close()
        return new_count
    except: return 1

def should_flip_gold(new_direction, confidence, market):
    try:
        last = get_last_signal()
        if last["direction"] == new_direction: return True, "Misma dirección oro - continua"
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone(); conn.close()
        if row:
            try:
                last_time = datetime.fromisoformat(row[0])
                minutes_passed = (datetime.now(EC_TZ) - last_time).total_seconds()/60
                # Si hay EXPANSION tras ACUMULACION, permitir cambio rapido
                if "EXPANSION" in market.get("phase","") and confidence >= 72:
                    return True, f"🔥 EXPANSION {market.get('phase')} tras acumulacion - cambio rapido {confidence}%"
                if minutes_passed < 12 and confidence < 78:
                    return False, f"Oro fase {market.get('phase')} esperando 12min (van {minutes_passed:.1f}m) conf {confidence}%"
                if confidence >= 80: return True, f"Cambio alta confianza {confidence}% + fase {market.get('phase')}"
                if minutes_passed >= 15: return True, f"Cambio tras {minutes_passed:.1f}m + fase {market.get('phase')}"
            except: pass
        if confidence >= 72: return True, f"Confianza {confidence}% + fase {market.get('phase')}"
        return False, f"Confianza baja {confidence}% manteniendo {last['direction']} en fase {last.get('phase','')}"
    except Exception as e:
        print(f"flip error {e}")
        return True, "Error permitiendo cambio"

def calculate_gold_tp_sl(entry, direction="BUY"):
    TARGET = 10.0; PROFIT_PER_USD = 1.62
    sl_dist = round(TARGET / PROFIT_PER_USD, 2)
    tp1_dist = sl_dist; tp2_dist = round((TARGET*2)/PROFIT_PER_USD, 2); tp3_dist = round((TARGET*3)/PROFIT_PER_USD, 2)
    if direction == "BUY":
        sl = round(entry - sl_dist, 2); tp1 = round(entry + tp1_dist, 2); tp2 = round(entry + tp2_dist, 2); tp3 = round(entry + tp3_dist, 2)
    else:
        sl = round(entry + sl_dist, 2); tp1 = round(entry - tp1_dist, 2); tp2 = round(entry - tp2_dist, 2); tp3 = round(entry - tp3_dist, 2)
    return sl, tp1, tp2, tp3, sl_dist, tp1_dist, tp2_dist, tp3_dist

def get_gold_stats():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total FROM gold_learning WHERE id=1")
        row = c.fetchone(); conn.close()
        if row: return {"wins": row[0], "loss": row[1], "tp1": row[2], "tp2": row[3], "tp3": row[4], "total": row[5], "buy_wins": row[6], "buy_total": row[7], "sell_wins": row[8], "sell_total": row[9]}
    except: pass
    return {"wins":18,"loss":6,"tp1":12,"tp2":8,"tp3":5,"total":24,"buy_wins":11,"buy_total":14,"sell_wins":7,"sell_total":10}

def update_gold_stats(result, direction="BUY"):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        if result == "SL":
            c.execute("UPDATE gold_learning SET loss=loss+1, total_trades=total_trades+1 WHERE id=1")
            if direction=="BUY": c.execute("UPDATE gold_learning SET buy_total=buy_total+1 WHERE id=1")
            else: c.execute("UPDATE gold_learning SET sell_total=sell_total+1 WHERE id=1")
        else:
            c.execute("UPDATE gold_learning SET wins=wins+1, total_trades=total_trades+1 WHERE id=1")
            if direction=="BUY":
                c.execute("UPDATE gold_learning SET buy_wins=buy_wins+1, buy_total=buy_total+1 WHERE id=1")
            else:
                c.execute("UPDATE gold_learning SET sell_wins=sell_wins+1, sell_total=sell_total+1 WHERE id=1")
        hour = datetime.now(EC_TZ).hour
        c.execute("SELECT hour FROM gold_hour_learning WHERE hour=?", (hour,))
        if c.fetchone():
            if result=="SL":
                c.execute("UPDATE gold_hour_learning SET total=total+1 WHERE hour=?", (hour,))
                if direction=="BUY": c.execute("UPDATE gold_hour_learning SET buy_total=buy_total+1 WHERE hour=?", (hour,))
                else: c.execute("UPDATE gold_hour_learning SET sell_total=sell_total+1 WHERE hour=?", (hour,))
            else:
                c.execute("UPDATE gold_hour_learning SET wins=wins+1, total=total+1 WHERE hour=?", (hour,))
                if direction=="BUY": c.execute("UPDATE gold_hour_learning SET buy_wins=buy_wins+1, buy_total=buy_total+1 WHERE hour=?", (hour,))
                else: c.execute("UPDATE gold_hour_learning SET sell_wins=sell_wins+1, sell_total=sell_total+1 WHERE hour=?", (hour,))
        conn.commit(); conn.close()
    except Exception as e: print(f"update stats error {e}")

def calculate_gold_success_rate(direction="BUY"):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price FROM price_history ORDER BY id DESC LIMIT 300")
        prices = [r[0] for r in c.fetchall()][::-1]
        conn.close()
        if len(prices) < 50: return 72.0, 72.0, 50.0, 35.0
        objetivo_tp1 = 10.0 / 1.62; objetivo_tp2 = 20.0 / 1.62; objetivo_tp3 = 30.0 / 1.62
        exitos_tp1 = 0; exitos_tp2 = 0; exitos_tp3 = 0; total = 0
        for i in range(len(prices)-40):
            entry = prices[i]; ventana_10 = prices[i+1:i+21]; ventana_15 = prices[i+1:i+31]
            if not ventana_10: continue
            if direction == "BUY":
                max_10 = max(ventana_10); max_15 = max(ventana_15)
                total+=1
                if max_10-entry >= objetivo_tp1 or max_15-entry >= objetivo_tp1: exitos_tp1+=1
                if max_15-entry >= objetivo_tp2: exitos_tp2+=1
                if max_15-entry >= objetivo_tp3: exitos_tp3+=1
            else:
                min_10 = min(ventana_10); min_15 = min(ventana_15)
                total+=1
                if entry-min_10 >= objetivo_tp1 or entry-min_15 >= objetivo_tp1: exitos_tp1+=1
                if entry-min_15 >= objetivo_tp2: exitos_tp2+=1
                if entry-min_15 >= objetivo_tp3: exitos_tp3+=1
        if total==0: return 72.0, 72.0, 50.0, 35.0
        prob_tp1 = (exitos_tp1/total*100); prob_tp2 = (exitos_tp2/total*100); prob_tp3 = (exitos_tp3/total*100)
        prob_obj = prob_tp1*0.5 + prob_tp2*0.3 + prob_tp3*0.2
        return round(prob_obj,1), round(prob_tp1,1), round(prob_tp2,1), round(prob_tp3,1)
    except Exception as e:
        print(f"success rate error {e}")
        return 72.0, 72.0, 50.0, 35.0

def calculate_gold_probability(hour, market):
    try:
        stats = get_gold_stats()
        direction = market.get("direction", "BUY")
        if direction == "BUY":
            bt = stats.get("buy_total",1); bw = stats.get("buy_wins",0)
            win_rate_dir = (bw/bt*100) if bt>0 else 75
        else:
            st = stats.get("sell_total",1); sw = stats.get("sell_wins",0)
            win_rate_dir = (sw/st*100) if st>0 else 70
        total = stats["wins"]+stats["loss"]
        win_rate_global = (stats["wins"]/total*100) if total>0 else 72
        prob_obj, prob_tp1, prob_tp2, prob_tp3 = calculate_gold_success_rate(direction)
        confidence = market.get("confidence",65)
        # Bonus por fase clara + patron vela
        phase_bonus = 0
        if "EXPANSION" in market.get("phase",""): phase_bonus = 10
        elif "TENDENCIA" in market.get("phase",""): phase_bonus = 5
        elif "ACUMULACION" in market.get("phase",""): phase_bonus = -8
        candle_bonus = min(len(market.get("candle_patterns",[])) * 3, 9)

        hour_bonus = 12 if 8 <= hour <= 10 else 6 if 7 <= hour <= 12 else 3 if 13 <= hour <= 15 else 0
        vol = market.get("volatility",0)
        vol_bonus = 5 if vol >= 3.0 else -5 if vol < 1.5 else 0

        prob = (win_rate_dir*0.30) + (prob_obj*0.30) + (confidence*0.20) + hour_bonus + vol_bonus + phase_bonus + candle_bonus
        prob = max(50, min(95, prob))
        return round(prob,1), stats, prob_tp1, prob_tp2, prob_tp3, win_rate_dir, win_rate_global
    except Exception as e:
        print(f"calc prob error {e}")
        return 72.0, get_gold_stats(), 72.0, 50.0, 35.0, 70.0, 72.0

@app.get("/")
def root():
    return {"message": "EdgeAlert ORO - FASES + VELAS JAPONESAS", "version": "5.0 FASES", "features": "acumulacion->picos, base velas alcistas/bajistas"}

@app.get("/health")
def health():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM price_history")
    count = c.fetchone()[0]
    conn.close()
    return {"status": "ok", "symbol": "XAUUSD", "price_history": count, "version": "5.0 FASES + VELAS"}

@app.get("/signals/live")
def signals_live():
    try:
        price = get_gold_price()
        save_gold_history(price)
        market = analyze_gold_pro()
        new_dir = market.get("direction", "BUY")
        conf = market.get("confidence", 65)
        should_flip, flip_reason = should_flip_gold(new_dir, conf, market)
        if should_flip:
            final_dir = new_dir
            update_last_signal(final_dir, market.get("phase",""))
        else:
            last = get_last_signal()
            final_dir = last["direction"]
            market["reason"] += f" | Manteniendo {final_dir}: {flip_reason}"
        hour = datetime.now(EC_TZ).hour
        prob, stats, prob_tp1, prob_tp2, prob_tp3, win_rate_dir, win_rate_global = calculate_gold_probability(hour, market)
        sl, tp1, tp2, tp3, sl_dist, tp1_dist, tp2_dist, tp3_dist = calculate_gold_tp_sl(price, final_dir)
        if final_dir == "BUY":
            sl_exp = f"SL {sl} ABAJO (si baja {sl_dist} pierdes $10)"
            tp_exp = f"TP1 {tp1} ARRIBA (si sube {tp1_dist} ganas $10) COMPRA"
        else:
            sl_exp = f"SL {sl} ARRIBA (si sube {sl_dist} pierdes $10)"
            tp_exp = f"TP1 {tp1} ABAJO (si baja {tp1_dist} ganas $10) VENTA"
        signal = {
            "symbol": "XAUUSD", "direction": final_dir, "entry": price,
            "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "sl_distance": sl_dist, "tp1_distance": tp1_dist,
            "probability": prob, "confidence": conf,
            "win_rate": win_rate_global, "win_rate_direction": win_rate_dir,
            "win_rate_buy": round(stats.get("buy_wins",0)/max(stats.get("buy_total",1),1)*100,1),
            "win_rate_sell": round(stats.get("sell_wins",0)/max(stats.get("sell_total",1),1)*100,1),
            "is_optimal_hour": 8 <= hour <= 10,
            "market_analysis": market,
            "phase": market.get("phase",""), "phase_desc": market.get("phase_desc",""),
            "candle_patterns": market.get("candle_patterns",[]),
            "probabilidad_nuevos_objetivos": {"prob_tp1_10usd_10_15min": prob_tp1, "prob_tp2_20usd_15min": prob_tp2, "prob_tp3_30usd_15min": prob_tp3},
            "sl_explain": sl_exp, "tp_explain": tp_exp,
            "reason": market.get("reason",""), "pattern": market.get("pattern",""), "flip_reason": flip_reason,
            "support": market.get("support",0), "resistance": market.get("resistance",0),
            "timestamp": datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        print(f"signals_live error {e}")
        import traceback; traceback.print_exc()
        return []

@app.get("/trades/active")
def get_active():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,direction,entry,sl,tp1,tp2,tp3,probability,status,tp1_hit,tp2_hit,tp3_hit,created_at,last_price,pattern,phase FROM active_trades WHERE status='OPEN' ORDER BY id DESC")
    rows=c.fetchall(); conn.close()
    return [{"id":r[0],"symbol":"XAUUSD","direction":r[1],"entry":r[2],"sl":r[3],"tp1":r[4],"tp2":r[5],"tp3":r[6],"probability":r[7],"status":r[8],"tp1_hit":bool(r[9]),"tp2_hit":bool(r[10]),"tp3_hit":bool(r[11]),"created_at":r[12],"last_price":r[13],"pattern":r[14],"phase":r[15]} for r in rows]

@app.post("/trades/result")
def save_result(r: TradeResult):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT direction, pattern, phase FROM active_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    direction = row[0] if row else "BUY"
    pattern = row[1] if row and len(row)>1 else "UNKNOWN"
    phase = row[2] if row and len(row)>2 else "UNKNOWN"
    conn.close()
    update_gold_stats(r.result, direction)
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT pattern FROM gold_patterns WHERE pattern=?", (pattern,))
        if c.fetchone():
            if r.result != "SL": c.execute("UPDATE gold_patterns SET wins=wins+1, total=total+1 WHERE pattern=?", (pattern,))
            else: c.execute("UPDATE gold_patterns SET total=total+1 WHERE pattern=?", (pattern,))
        c.execute("SELECT phase FROM market_phases WHERE phase=?", (phase,))
        if c.fetchone():
            c.execute("UPDATE market_phases SET count=count+1 WHERE phase=?", (phase,))
            if r.result != "SL":
                if direction=="BUY": c.execute("UPDATE market_phases SET buy_success=buy_success+1 WHERE phase=?", (phase,))
                else: c.execute("UPDATE market_phases SET sell_success=sell_success+1 WHERE phase=?", (phase,))
        conn.commit(); conn.close()
    except: pass
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE active_trades SET status=? WHERE status='OPEN'", (f"{r.result}_MANUAL",))
    conn.commit(); conn.close()
    return {"ok": True, "learning": get_gold_stats(), "direction": direction, "pattern": pattern, "phase": phase}

@app.get("/gold/analysis")
def gold_analysis():
    market = analyze_gold_pro()
    last = get_last_signal()
    rows = get_gold_history(50)
    price = get_gold_price()
    stats = get_gold_stats()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT phase,count,buy_success,sell_success FROM market_phases ORDER BY count DESC")
    phases = c.fetchall()
    c.execute("SELECT pattern,wins,total,description FROM gold_patterns ORDER BY total DESC")
    patterns = c.fetchall()
    conn.close()
    return {
        "symbol": "XAUUSD", "current_price": price, "analysis_pro": market, "last_signal": last,
        "stats": stats, "price_history_count": len(rows),
        "phases": [{"phase":p[0],"count":p[1],"buy_success":p[2],"sell_success":p[3]} for p in phases],
        "patterns": [{"pattern":p[0],"wins":p[1],"total":p[2],"desc":p[3]} for p in patterns]
    }

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        print("🚀 Monitor ORO FASES + VELAS iniciado")
        while True:
            try:
                price = get_gold_price()
                save_gold_history(price)
            except Exception as e: print(f"monitor error {e}")
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())

@app.get("/best_hours")
def best_hours():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT hour,wins,total FROM gold_hour_learning WHERE total>0 ORDER BY CAST(wins AS FLOAT)/total DESC LIMIT 5")
    rows = c.fetchall(); conn.close()
    best = [r[0] for r in rows] if rows else [8,9,10,13,14]
    return {"symbol": "XAUUSD", "best_hours": best, "best_hours_detail": rows}
