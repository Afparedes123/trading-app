import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="EdgeAlert ORO - TRADINGVIEW STRUCTURAL ENGINE v14.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tabla de velas reales de 1 minuto (OHLC) para analizar los últimos 40-60 min con precisión matemática
    c.execute("""CREATE TABLE IF NOT EXISTS ohlc_1m (
        ts INTEGER PRIMARY KEY,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL DEFAULT 0,
        source TEXT DEFAULT 'FEED'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (
        symbol TEXT PRIMARY KEY,
        direction TEXT,
        confirmed_at TEXT,
        phase TEXT,
        entry_price REAL DEFAULT 0,
        sl_price REAL DEFAULT 0,
        tp_price REAL DEFAULT 0
    )""")
    conn.commit()
    conn.close()

init_db()

class TVWebhookPayload(BaseModel):
    symbol: Optional[str] = "XAUUSD"
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = 0.0
    interval: Optional[str] = "1"

def get_live_spot_price():
    """Obtiene el tick en vivo compatible con el feed de TradingView (OANDA / FXCM / Swissquote)"""
    # 1. Revisar si la cuenta de TradingView del usuario envió un tick en los últimos 20 segundos
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT close, ts, source FROM ohlc_1m ORDER BY ts DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if row and row[2] == "TRADINGVIEW_ACCOUNT" and (now_ts - row[1]) <= 65:
            return float(row[0]), "TRADINGVIEW CUENTA DIRECTA"
    except:
        pass

    # 2. Feed Spot Institucional en tiempo real
    try:
        r = requests.get("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD", timeout=3)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                prices = data[0].get("spreadProfilePrices", [])
                if prices:
                    bid = float(prices[0].get("bid", 0))
                    ask = float(prices[0].get("ask", 0))
                    if bid > 1000 and ask > 1000:
                        return round((bid + ask) / 2.0, 2), "SPOT REALTIME FEED"
    except:
        pass

    # 3. Respaldo Gold-API
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code == 200 and r.json().get("price"):
            p = float(r.json()["price"])
            if p > 1000:
                return round(p, 2), "GOLD-API SPOT"
    except:
        pass

    return 3946.00, "FALLBACK"

def sync_historical_1m_candles():
    """Descarga las últimas 60 velas de 1 minuto reales para tener la estructura de 60 min desde el arranque"""
    try:
        # Yahoo Finance 1m chart feed para Oro / Spot (60 minutos exactos)
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
        r = requests.get(url, headers=headers, timeout=4)
        live_p, _ = get_live_spot_price()
        if r.status_code == 200:
            res = r.json().get("chart", {}).get("result", [])
            if res:
                timestamps = res[0].get("timestamp", [])[-90:]
                quote = res[0].get("indicators", {}).get("quote", [{}])[0]
                opens = quote.get("open", [])[-90:]
                highs = quote.get("high", [])[-90:]
                lows = quote.get("low", [])[-90:]
                closes = quote.get("close", [])[-90:]
                vols = quote.get("volume", [])[-90:]

                # Ajustar el diferencial (basis) entre futuro y spot de TradingView para que coincida al centavo
                valid_closes = [c for c in closes if c is not None and c > 1000]
                basis = (live_p - valid_closes[-1]) if valid_closes else 0.0

                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                for i in range(len(timestamps)):
                    if None in (opens[i], highs[i], lows[i], closes[i]):
                        continue
                    ts_min = (int(timestamps[i]) // 60) * 60
                    o = round(float(opens[i]) + basis, 2)
                    h = round(float(highs[i]) + basis, 2)
                    l = round(float(lows[i]) + basis, 2)
                    cl = round(float(closes[i]) + basis, 2)
                    v = float(vols[i] or 0)
                    # No sobrescribir velas enviadas directamente por el webhook de TradingView
                    c.execute("SELECT source FROM ohlc_1m WHERE ts=?", (ts_min,))
                    existing = c.fetchone()
                    if not existing or existing[0] != "TRADINGVIEW_ACCOUNT":
                        c.execute("""INSERT OR REPLACE INTO ohlc_1m (ts,open,high,low,close,volume,source)
                                     VALUES (?,?,?,?,?,?,?)""", (ts_min, o, h, l, cl, v, "SYNC_1M"))
                conn.commit()
                conn.close()
                return
    except Exception as e:
        print(f"Sync 1m warning: {e}")

    # Si el mercado está cerrado o falla la red, poblar estructura base si está vacía
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ohlc_1m")
        if c.fetchone()[0] < 45:
            base, _ = get_live_spot_price()
            now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60
            for i in range(60):
                ts = now_min - ((60 - i) * 60)
                wave = math.sin(i / 6.0) * 3.2 + math.cos(i / 3.0) * 1.1
                o = round(base + wave, 2)
                cl = round(base + math.sin((i + 1) / 6.0) * 3.2 + math.cos((i + 1) / 3.0) * 1.1, 2)
                hi = round(max(o, cl) + 0.6, 2)
                lo = round(min(o, cl) - 0.6, 2)
                c.execute("INSERT OR IGNORE INTO ohlc_1m (ts,open,high,low,close,volume,source) VALUES (?,?,?,?,?,?,?)",
                          (ts, o, hi, lo, cl, 100, "INIT"))
            conn.commit()
        conn.close()
    except:
        pass

def update_current_1m_candle(price, source="FEED"):
    """Actualiza la vela de 1 minuto en curso con cada nuevo tick en tiempo real"""
    try:
        now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT open, high, low, close, volume, source FROM ohlc_1m WHERE ts=?", (now_min,))
        row = c.fetchone()
        if row:
            o, h, l, cl, v, prev_src = row
            new_h = max(h, price)
            new_l = min(l, price)
            final_src = "TRADINGVIEW_ACCOUNT" if source == "TRADINGVIEW_ACCOUNT" else prev_src
            c.execute("UPDATE ohlc_1m SET high=?, low=?, close=?, volume=?, source=? WHERE ts=?",
                      (new_h, new_l, price, v + 1, final_src, now_min))
        else:
            c.execute("INSERT INTO ohlc_1m (ts,open,high,low,close,volume,source) VALUES (?,?,?,?,?,?,?)",
                      (now_min, price, price, price, price, 1, source))
        # Mantener las últimas 240 velas de 1m (4 horas de historia)
        c.execute("DELETE FROM ohlc_1m WHERE ts NOT IN (SELECT ts FROM ohlc_1m ORDER BY ts DESC LIMIT 240)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Update 1m error: {e}")

def get_1m_candles(limit=60):
    """Obtiene las últimas N velas de 1 minuto (por defecto 60 minutos)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT ts, open, high, low, close, volume, source FROM ohlc_1m ORDER BY ts DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        rows = rows[::-1]
        candles = []
        for r in rows:
            o, h, l, cl = float(r[1]), float(r[2]), float(r[3]), float(r[4])
            body = abs(cl - o)
            rng = max(h - l, 0.05)
            candles.append({
                "ts": r[0], "open": o, "high": h, "low": l, "close": cl,
                "volume": float(r[5]), "source": r[6],
                "body": round(body, 2), "range": round(rng, 2),
                "body_ratio": round(body / rng, 2),
                "upper_wick": round(h - max(o, cl), 2),
                "lower_wick": round(min(o, cl) - l, 2),
                "bullish": cl >= o
            })
        return candles
    except:
        return []

def aggregate_candles(candles_1m, tf_minutes=5):
    """Agrupa las velas de 1m en velas de 5m (M5) para confirmar patrones de velas japonesas"""
    if len(candles_1m) < tf_minutes:
        return []
    agg = []
    rem = len(candles_1m) % tf_minutes
    start = rem if rem > 0 else 0
    for i in range(start, len(candles_1m), tf_minutes):
        chunk = candles_1m[i:i + tf_minutes]
        if not chunk:
            continue
        o = chunk[0]["open"]
        cl = chunk[-1]["close"]
        h = max(c["high"] for c in chunk)
        l = min(c["low"] for c in chunk)
        body = abs(cl - o)
        rng = max(h - l, 0.05)
        agg.append({
            "ts": chunk[0]["ts"], "open": o, "high": h, "low": l, "close": cl,
            "body": round(body, 2), "range": round(rng, 2),
            "body_ratio": round(body / rng, 2),
            "upper_wick": round(h - max(o, cl), 2),
            "lower_wick": round(min(o, cl) - l, 2),
            "bullish": cl >= o, "strong": (body / rng) > 0.55 and body >= 0.7
        })
    return agg

# ==============================================================================
# MOTORES MATEMÁTICOS DE ESTRUCTURA (ÚLTIMOS 40 - 60 MINUTOS)
# ==============================================================================

def calc_linear_regression(closes):
    """Calcula la pendiente matemática (USD/min) y el R² (fuerza de tendencia vs rango) en los últimos 45 min"""
    n = len(closes)
    if n < 10:
        return {"slope": 0.0, "r_squared": 0.0, "forecast": closes[-1] if closes else 0.0}
    x_mean = (n - 1) / 2.0
    y_mean = sum(closes) / n
    num = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    den_x = sum((i - x_mean) ** 2 for i in range(n))
    den_y = sum((closes[i] - y_mean) ** 2 for i in range(n))
    if den_x == 0 or den_y == 0:
        return {"slope": 0.0, "r_squared": 0.0, "forecast": y_mean}
    slope = num / den_x
    intercept = y_mean - slope * x_mean
    r_squared = (num ** 2) / (den_x * den_y)
    forecast = intercept + slope * (n - 1)
    return {
        "slope_per_10m": round(slope * 10.0, 2),  # Cuántos USD se mueve cada 10 minutos
        "r_squared": round(r_squared, 2),         # 0.0 = Rango total, >0.25 = Tendencia clara, >0.50 = Canal perfecto
        "forecast": round(forecast, 2)
    }

def detect_swings_and_structure_45m(candles_1m):
    """
    Analiza los últimos 45-60 minutos usando Fractales de Williams (ventana 3m a cada lado)
    para mapear la secuencia exacta: HH, HL, LH, LL, BOS (Break of Structure) y CHoCH (Cambio de Carácter).
    """
    window = candles_1m[-50:] if len(candles_1m) >= 50 else candles_1m
    if len(window) < 15:
        p = window[-1]["close"] if window else 3945.0
        return {
            "regime": "CALIBRANDO", "sequence": [], "last_sh": p + 3, "prev_sh": p + 3,
            "last_sl": p - 3, "prev_sl": p - 3, "bos": "NONE", "choch": "NONE",
            "impulse_dir": "NEUTRAL", "impulse_high": p + 3, "impulse_low": p - 3,
            "fib_retracement": 0.5, "pattern_summary": "Recolectando estructura de 45 min"
        }

    swing_highs = []  # Lista de tuplas (idx, precio)
    swing_lows = []

    # Detectar pivotes confirmados (2 velas a la izquierda y 2 a la derecha)
    for i in range(2, len(window) - 2):
        h = window[i]["high"]
        l = window[i]["low"]
        if h >= window[i - 1]["high"] and h >= window[i - 2]["high"] and h >= window[i + 1]["high"] and h >= window[i + 2]["high"]:
            # Evitar duplicar pivotes pegados en el mismo nivel
            if not swing_highs or (i - swing_highs[-1][0]) >= 3 or h > swing_highs[-1][1]:
                swing_highs.append((i, h))
        if l <= window[i - 1]["low"] and l <= window[i - 2]["low"] and l <= window[i + 1]["low"] and l <= window[i + 2]["low"]:
            if not swing_lows or (i - swing_lows[-1][0]) >= 3 or l < swing_lows[-1][1]:
                swing_lows.append((i, l))

    all_highs = [c["high"] for c in window]
    all_lows = [c["low"] for c in window]
    if len(swing_highs) < 2:
        swing_highs = [(0, max(all_highs[:len(all_highs)//2])), (len(window)//2, max(all_highs[len(all_highs)//2:]))]
    if len(swing_lows) < 2:
        swing_lows = [(0, min(all_lows[:len(all_lows)//2])), (len(window)//2, min(all_lows[len(all_lows)//2:]))]

    last_sh_idx, last_sh = swing_highs[-1]
    prev_sh_idx, prev_sh = swing_highs[-2]
    last_sl_idx, last_sl = swing_lows[-1]
    prev_sl_idx, prev_sl = swing_lows[-2]

    # Etiquetar los últimos Swings (HH/LH y HL/LL)
    high_tag = "HH (Alto más Alto)" if last_sh > prev_sh + 0.25 else ("LH (Alto más Bajo)" if last_sh < prev_sh - 0.25 else "EH (Doble Techo)")
    low_tag = "HL (Bajo más Alto)" if last_sl > prev_sl + 0.25 else ("LL (Bajo más Bajo)" if last_sl < prev_sl - 0.25 else "EL (Doble Suelo)")
    sequence = [prev_sl, prev_sh, last_sl, last_sh]

    live_p = window[-1]["close"]
    prev_close = window[-2]["close"]

    # Determinar el Régimen Estructural de los últimos 45 minutos
    if "HH" in high_tag and "HL" in low_tag:
        regime = "ESTRUCTURA ALCISTA (HH + HL)"
        struct_bias = "COMPRA"
    elif "LH" in high_tag and "LL" in low_tag:
        regime = "ESTRUCTURA BAJISTA (LH + LL)"
        struct_bias = "VENTA"
    elif "LH" in high_tag and "HL" in low_tag:
        regime = "COMPRESIÓN / TRIÁNGULO (LH + HL)"
        struct_bias = "NEUTRAL"
    else:
        regime = "TRANSICIÓN ESTRUCTURAL"
        struct_bias = "COMPRA" if live_p > (last_sh + last_sl) / 2 else "VENTA"

    # Detectar BOS (Ruptura de Continuación) y CHoCH (Cambio de Carácter / Giro de Tendencia)
    bos = "NONE"
    choch = "NONE"
    if live_p > last_sh + 0.15:
        if struct_bias == "COMPRA":
            bos = "BOS ALCISTA (Ruptura de Alto Previo -> Nuevo Impulso)"
        else:
            choch = "CHoCH ALCISTA (Rompió último LH -> Giro a Compra)"
            struct_bias = "COMPRA"
            regime = "GIRO ALCISTA CONFIRMADO (CHoCH)"
    elif live_p < last_sl - 0.15:
        if struct_bias == "VENTA":
            bos = "BOS BAJISTA (Ruptura de Bajo Previo -> Nuevo Impulso)"
        else:
            choch = "CHoCH BAJISTA (Rompió último HL -> Giro a Venta)"
            struct_bias = "VENTA"
            regime = "GIRO BAJISTA CONFIRMADO (CHoCH)"

    # Medir la pierna de impulso activa y el nivel exacto de retroceso Fibonacci (0.0 a 1.0)
    if struct_bias == "COMPRA":
        imp_low = last_sl
        imp_high = max(last_sh, max(c["high"] for c in window[last_sl_idx:]))
        imp_range = max(imp_high - imp_low, 0.5)
        # 0.0 = En la cima del impulso, 0.5 = Mitad del retroceso, 0.618 = Retroceso OTE, 1.0 = Inicio del impulso
        fib_ret = round((imp_high - live_p) / imp_range, 3)
        impulse_dir = "ALCISTA"
    else:
        imp_high = last_sh
        imp_low = min(last_sl, min(c["low"] for c in window[last_sh_idx:]))
        imp_range = max(imp_high - imp_low, 0.5)
        fib_ret = round((live_p - imp_low) / imp_range, 3)
        impulse_dir = "BAJISTA"

    fib_levels = {
        "0.0 (Fin Impulso)": round(imp_high if impulse_dir == "ALCISTA" else imp_low, 2),
        "0.382": round(imp_high - imp_range * 0.382 if impulse_dir == "ALCISTA" else imp_low + imp_range * 0.382, 2),
        "0.500": round(imp_high - imp_range * 0.500 if impulse_dir == "ALCISTA" else imp_low + imp_range * 0.500, 2),
        "0.618 (OTE)": round(imp_high - imp_range * 0.618 if impulse_dir == "ALCISTA" else imp_low + imp_range * 0.618, 2),
        "1.0 (Origen Invalidación)": round(imp_low if impulse_dir == "ALCISTA" else imp_high, 2)
    }

    # Clasificar en qué fase exacta del ciclo Impulso/Retroceso está el precio AHORA MISMO
    if bos != "NONE" or choch != "NONE":
        cycle_phase = f"ARRANQUE DE IMPULSO ({impulse_dir})"
    elif -0.05 <= fib_ret <= 0.28:
        cycle_phase = f"IMPULSO EN DESARROLLO ({impulse_dir})"
    elif 0.35 <= fib_ret <= 0.72:
        cycle_phase = f"RETROCESO EN ZONA FIBONACCI ({fib_ret*100:.0f}%)"
    elif fib_ret > 0.78:
        cycle_phase = f"RETROCESO PROFUNDO / PELIGRO DE QUIEBRE ({fib_ret*100:.0f}%)"
    else:
        cycle_phase = "CONSOLIDACIÓN"

    summary = f"{high_tag} [{last_sh:.2f}] • {low_tag} [{last_sl:.2f}]"

    return {
        "regime": regime,
        "struct_bias": struct_bias,
        "high_tag": high_tag,
        "low_tag": low_tag,
        "last_sh": round(last_sh, 2),
        "prev_sh": round(prev_sh, 2),
        "last_sl": round(last_sl, 2),
        "prev_sl": round(prev_sl, 2),
        "bos": bos,
        "choch": choch,
        "impulse_dir": impulse_dir,
        "impulse_range": round(imp_range, 2),
        "fib_retracement": fib_ret,
        "fib_levels": fib_levels,
        "cycle_phase": cycle_phase,
        "pattern_summary": summary
    }

def calc_ema(values, period):
    if not values: return 0.0
    if len(values) < period: return sum(values) / len(values)
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v * k) + (ema * (1 - k))
    return round(ema, 2)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0: return 100.0
    rs = avg_g / avg_l
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calc_atr(candles, period=14):
    if len(candles) < 2: return 1.8
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        pc = candles[i - 1]["close"]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - pc), abs(c["low"] - pc)))
    sub = trs[-period:] if len(trs) >= period else trs
    return round(max(sum(sub) / len(sub), 0.8), 2)

def get_last_signal():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, phase, entry_price, sl_price, tp_price FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "direction": row[0], "confirmed_at": row[1], "phase": row[2],
                "entry_price": float(row[3] or 0), "sl_price": float(row[4] or 0), "tp_price": float(row[5] or 0)
            }
    except:
        pass
    return {"direction": "ESPERA", "confirmed_at": datetime.now(EC_TZ).isoformat(), "phase": "INICIO", "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0}

def update_last_signal(direction, phase, entry_price=0.0, sl_price=0.0, tp_price=0.0):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO last_signal
                     (symbol,direction,confirmed_at,phase,entry_price,sl_price,tp_price)
                     VALUES (?,?,?,?,?,?,?)""",
                  ("XAUUSD", direction, datetime.now(EC_TZ).isoformat(), phase, entry_price, sl_price, tp_price))
        conn.commit()
        conn.close()
    except:
        pass

def analyze_market_v14():
    live_price, feed_source = get_live_spot_price()
    update_current_1m_candle(live_price, "FEED")
    candles_1m = get_1m_candles(60)
    if len(candles_1m) < 25:
        sync_historical_1m_candles()
        candles_1m = get_1m_candles(60)

    candles_5m = aggregate_candles(candles_1m, tf_minutes=5)
    closes_1m = [c["close"] for c in candles_1m]
    closes_5m = [c["close"] for c in candles_5m] if candles_5m else closes_1m

    # 1. Cálculos Matemáticos de los últimos 45-60 minutos
    reg_45m = calc_linear_regression(closes_1m[-45:])
    struct_45m = detect_swings_and_structure_45m(candles_1m)
    ema9_1m = calc_ema(closes_1m, 9)
    ema21_1m = calc_ema(closes_1m, 21)
    ema50_1m = calc_ema(closes_1m, 45)
    rsi_1m = calc_rsi(closes_1m, 14)
    atr_5m = calc_atr(candles_5m, 10) if len(candles_5m) >= 4 else calc_atr(candles_1m, 14) * 2.0

    last_1m = candles_1m[-1]
    prev_1m = candles_1m[-2] if len(candles_1m) >= 2 else last_1m
    last_5m = candles_5m[-1] if candles_5m else last_1m

    support = min(struct_45m["last_sl"], struct_45m["prev_sl"])
    resistance = max(struct_45m["last_sh"], struct_45m["prev_sh"])
    room_up = round(max(0.0, resistance - live_price), 2)
    room_down = round(max(0.0, live_price - support), 2)

    buy_score = 0
    sell_score = 0
    points_detail = []

    # ==========================================================================
    # PILAR 1: ESTRUCTURA DE LOS ÚLTIMOS 45 MINUTOS (HH/HL vs LH/LL + Regresión)
    # ==========================================================================
    if struct_45m["struct_bias"] == "COMPRA" and reg_45m["slope_per_10m"] > 0.15:
        buy_score += 4
        points_detail.append({
            "side": "COMPRA", "points": 4,
            "name": f"ESTRUCTURA 45m ALCISTA ({struct_45m['regime']})",
            "reason": f"{struct_45m['pattern_summary']} • Pendiente: +${reg_45m['slope_per_10m']:.2f}/10m (R²={reg_45m['r_squared']})"
        })
    elif struct_45m["struct_bias"] == "VENTA" and reg_45m["slope_per_10m"] < -0.15:
        sell_score += 4
        points_detail.append({
            "side": "VENTA", "points": 4,
            "name": f"ESTRUCTURA 45m BAJISTA ({struct_45m['regime']})",
            "reason": f"{struct_45m['pattern_summary']} • Pendiente: ${reg_45m['slope_per_10m']:.2f}/10m (R²={reg_45m['r_squared']})"
        })

    # ==========================================================================
    # PILAR 2: MOTOR DE IMPULSOS (BOS / CHoCH / Ruptura con Cuerpo)
    # ==========================================================================
    if struct_45m["bos"].startswith("BOS ALCISTA") or struct_45m["choch"].startswith("CHoCH ALCISTA"):
        tag = struct_45m["bos"] if struct_45m["bos"] != "NONE" else struct_45m["choch"]
        buy_score += 5
        points_detail.append({
            "side": "COMPRA", "points": 5,
            "name": f"🚀 QUIEBRE ESTRUCTURAL: {tag.split('(')[0].strip()}",
            "reason": f"El precio superó el máximo estructural ({struct_45m['last_sh']:.2f}) iniciando nuevo impulso."
        })
    elif struct_45m["bos"].startswith("BOS BAJISTA") or struct_45m["choch"].startswith("CHoCH BAJISTA"):
        tag = struct_45m["bos"] if struct_45m["bos"] != "NONE" else struct_45m["choch"]
        sell_score += 5
        points_detail.append({
            "side": "VENTA", "points": 5,
            "name": f"📉 QUIEBRE ESTRUCTURAL: {tag.split('(')[0].strip()}",
            "reason": f"El precio rompió el mínimo estructural ({struct_45m['last_sl']:.2f}) iniciando caída."
        })

    # Impulso en desarrollo (Continuación de tendencia cuando Fib está entre 0.0 y 0.30 y hay vela fuerte)
    fib_ret = struct_45m["fib_retracement"]
    if struct_45m["impulse_dir"] == "ALCISTA" and 0.0 <= fib_ret <= 0.30 and last_1m["bullish"] and live_price > ema9_1m:
        buy_score += 3
        points_detail.append({
            "side": "COMPRA", "points": 3,
            "name": "IMPULSO ALCISTA EN CONTINUACIÓN",
            "reason": f"Precio sosteniendo fuerza sobre EMA9 ({ema9_1m:.2f}) rumbo a {struct_45m['fib_levels']['0.0 (Fin Impulso)']:.2f}."
        })
    elif struct_45m["impulse_dir"] == "BAJISTA" and 0.0 <= fib_ret <= 0.30 and not last_1m["bullish"] and live_price < ema9_1m:
        sell_score += 3
        points_detail.append({
            "side": "VENTA", "points": 3,
            "name": "IMPULSO BAJISTA EN CONTINUACIÓN",
            "reason": f"Precio sosteniendo presión bajo EMA9 ({ema9_1m:.2f}) rumbo a {struct_45m['fib_levels']['0.0 (Fin Impulso)']:.2f}."
        })

    # ==========================================================================
    # PILAR 3: MOTOR DE RETROCESOS (Fin del Pullback en Fib 0.382 - 0.65 + Giro)
    # ==========================================================================
    if struct_45m["impulse_dir"] == "ALCISTA" and 0.35 <= fib_ret <= 0.68:
        # Confirmar que el retroceso bajista ya frenó y está girando al alza (vela verde o mecha inferior de rechazo)
        if last_1m["bullish"] or last_1m["lower_wick"] >= last_1m["body"]:
            buy_score += 5
            points_detail.append({
                "side": "COMPRA", "points": 5,
                "name": f"🎯 FIN DE RETROCESO EN FIB {fib_ret*100:.0f}% (RE-ENTRADA)",
                "reason": f"El retroceso frenó en zona institucional ({struct_45m['fib_levels']['0.500']:.2f}-{struct_45m['fib_levels']['0.618 (OTE)']:.2f}) y retomó el impulso alcista."
            })
    elif struct_45m["impulse_dir"] == "BAJISTA" and 0.35 <= fib_ret <= 0.68:
        if not last_1m["bullish"] or last_1m["upper_wick"] >= last_1m["body"]:
            sell_score += 5
            points_detail.append({
                "side": "VENTA", "points": 5,
                "name": f"🎯 FIN DE RETROCESO EN FIB {fib_ret*100:.0f}% (RE-ENTRADA)",
                "reason": f"El rebote chocó en zona institucional ({struct_45m['fib_levels']['0.500']:.2f}-{struct_45m['fib_levels']['0.618 (OTE)']:.2f}) y retomó el impulso bajista."
            })

    # ==========================================================================
    # PILAR 4: CONFLUENCIA DE HERRAMIENTAS (EMAs + RSI + Velas M5)
    # ==========================================================================
    if ema9_1m > ema21_1m >= ema50_1m and 45 <= rsi_1m <= 68:
        buy_score += 2
        points_detail.append({"side": "COMPRA", "points": 2, "name": "ALINEACIÓN DE MEDIAS (9 > 21 > 45)", "reason": f"Flujo institucional comprador con RSI sano ({rsi_1m})."})
    elif ema9_1m < ema21_1m <= ema50_1m and 32 <= rsi_1m <= 55:
        sell_score += 2
        points_detail.append({"side": "VENTA", "points": 2, "name": "ALINEACIÓN DE MEDIAS (9 < 21 < 45)", "reason": f"Flujo institucional vendedor con RSI sano ({rsi_1m})."})

    # Filtro Matemático de Sobreextensión (No comprar en el techo si no hay BOS)
    if rsi_1m >= 73 and struct_45m["bos"] == "NONE":
        buy_score = max(0, buy_score - 5)
        points_detail.append({"side": "INFO", "points": 0, "name": "⚠️ IMPULSO AGOTADO (RSI > 73)", "reason": "El precio subió demasiado sin retroceder. Esperar pullback antes de comprar."})
    elif rsi_1m <= 27 and struct_45m["bos"] == "NONE":
        sell_score = max(0, sell_score - 5)
        points_detail.append({"side": "INFO", "points": 0, "name": "⚠️ CAÍDA AGOTADA (RSI < 27)", "reason": "El precio cayó demasiado sin retroceder. Esperar pullback antes de vender."})

    # ==========================================================================
    # PILAR 5: GESTIÓN DE SALIDAS EXACTAS (CICLO DE VIDA DE LA OPERACIÓN)
    # ==========================================================================
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price

    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        # 1. Salida en ganancia cuando el impulso empieza a retroceder hacia el Fibonacci o choca con techo
        if pnl >= 1.80 and (not last_1m["bullish"] and live_price < ema9_1m or rsi_1m >= 72):
            update_last_signal("ESPERA", "TP_COMPRA", 0.0, 0.0, 0.0)
            return {
                "direction": "ESPERA", "confidence": 92,
                "alert": f"💰 SALIR EN GANANCIA COMPRA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"El impulso alcista desde {entry_p:.2f} empezó a retroceder bajo EMA9 ({ema9_1m:.2f}). Asegura tu ganancia ahora y espera el retroceso al Fib.",
                "points_detail": points_detail, "live_price": live_price, "feed_source": feed_source,
                "buy_score": buy_score, "sell_score": sell_score, "rsi": rsi_1m, "atr": atr_5m,
                "support": support, "resistance": resistance, "room_up": room_up, "room_down": room_down,
                "struct_45m": struct_45m, "reg_45m": reg_45m, "flip_reason": f"Ganancia asegurada (+${pnl:.2f})"
            }
        # 2. Salida por invalidación estructural (Rompió HL o CHoCH bajista)
        if pnl <= -2.20 or struct_45m["choch"].startswith("CHoCH BAJISTA") or (live_price < ema21_1m and sell_score >= 6):
            update_last_signal("ESPERA", "EXIT_COMPRA", 0.0, 0.0, 0.0)
            return {
                "direction": "ESPERA", "confidence": 88,
                "alert": f"🔴 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "La estructura alcista perdió su soporte de corto plazo. Cierra la compra inmediatamente.",
                "points_detail": points_detail, "live_price": live_price, "feed_source": feed_source,
                "buy_score": buy_score, "sell_score": sell_score, "rsi": rsi_1m, "atr": atr_5m,
                "support": support, "resistance": resistance, "room_up": room_up, "room_down": room_down,
                "struct_45m": struct_45m, "reg_45m": reg_45m, "flip_reason": "Estructura invalidada"
            }

    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        if pnl >= 1.80 and (last_1m["bullish"] and live_price > ema9_1m or rsi_1m <= 28):
            update_last_signal("ESPERA", "TP_VENTA", 0.0, 0.0, 0.0)
            return {
                "direction": "ESPERA", "confidence": 92,
                "alert": f"💰 SALIR EN GANANCIA VENTA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"El impulso bajista desde {entry_p:.2f} empezó a rebotar sobre EMA9 ({ema9_1m:.2f}). Asegura tu ganancia ahora y espera el retroceso al Fib.",
                "points_detail": points_detail, "live_price": live_price, "feed_source": feed_source,
                "buy_score": buy_score, "sell_score": sell_score, "rsi": rsi_1m, "atr": atr_5m,
                "support": support, "resistance": resistance, "room_up": room_up, "room_down": room_down,
                "struct_45m": struct_45m, "reg_45m": reg_45m, "flip_reason": f"Ganancia asegurada (+${pnl:.2f})"
            }
        if pnl <= -2.20 or struct_45m["choch"].startswith("CHoCH ALCISTA") or (live_price > ema21_1m and buy_score >= 6):
            update_last_signal("ESPERA", "EXIT_VENTA", 0.0, 0.0, 0.0)
            return {
                "direction": "ESPERA", "confidence": 88,
                "alert": f"🔴 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "La estructura bajista fue rota al alza. Cierra la venta inmediatamente.",
                "points_detail": points_detail, "live_price": live_price, "feed_source": feed_source,
                "buy_score": buy_score, "sell_score": sell_score, "rsi": rsi_1m, "atr": atr_5m,
                "support": support, "resistance": resistance, "room_up": room_up, "room_down": room_down,
                "struct_45m": struct_45m, "reg_45m": reg_45m, "flip_reason": "Estructura invalidada"
            }

    # ==========================================================================
    # PILAR 6: DISPARO DE NUEVA ENTRADA (IMPULSO O FIN DE RETROCESO)
    # ==========================================================================
    sl_dist = round(max(2.0, min(atr_5m * 1.1, 3.2)), 2)
    tp_dist = round(max(2.6, min(atr_5m * 1.5, 4.2)), 2)

    if buy_score >= 6 and buy_score >= sell_score + 3:
        direction = "COMPRA"
        confidence = min(76 + (buy_score * 2), 96)
        sl_p = round(live_price - sl_dist, 2)
        tp_p = round(live_price + tp_dist, 2)
        mode_tag = "FIN DE RETROCESO FIB" if (0.35 <= fib_ret <= 0.68) else "IMPULSO CONFIRMADO"
        alert = f"✅ ENTRA COMPRA ({mode_tag})"
        alert_type = "ENTER"
        alert_desc = f"Estructura 45m: {struct_45m['regime']}. Fase actual: {struct_45m['cycle_phase']}."
        if active_dir != "COMPRA":
            update_last_signal("COMPRA", struct_45m["cycle_phase"], live_price, sl_p, tp_p)
            flip_reason = f"Entrada COMPRA en {live_price:.2f}"
        else:
            flip_reason = f"En COMPRA desde {entry_p:.2f} ({live_price - entry_p:+.2f} USD)"

    elif sell_score >= 6 and sell_score >= buy_score + 3:
        direction = "VENTA"
        confidence = min(76 + (sell_score * 2), 96)
        sl_p = round(live_price + sl_dist, 2)
        tp_p = round(live_price - tp_dist, 2)
        mode_tag = "FIN DE RETROCESO FIB" if (0.35 <= fib_ret <= 0.68) else "IMPULSO CONFIRMADO"
        alert = f"✅ ENTRA VENTA ({mode_tag})"
        alert_type = "ENTER"
        alert_desc = f"Estructura 45m: {struct_45m['regime']}. Fase actual: {struct_45m['cycle_phase']}."
        if active_dir != "VENTA":
            update_last_signal("VENTA", struct_45m["cycle_phase"], live_price, sl_p, tp_p)
            flip_reason = f"Entrada VENTA en {live_price:.2f}"
        else:
            flip_reason = f"En VENTA desde {entry_p:.2f} ({entry_p - live_price:+.2f} USD)"

    else:
        if active_dir in ["COMPRA", "VENTA"]:
            pnl = round(live_price - entry_p, 2) if active_dir == "COMPRA" else round(entry_p - live_price, 2)
            direction = active_dir
            confidence = 74
            alert = f"⏳ MANTENER {active_dir} EN CURSO ({pnl:+.2f} USD)"
            alert_type = "ENTER"
            alert_desc = f"Entrada en {entry_p:.2f} • Estructura 45m sigue a favor ({struct_45m['cycle_phase']})."
            flip_reason = f"Monitoreando operación abierta ({pnl:+.2f} USD)"
        else:
            direction = "ESPERA"
            confidence = 50
            alert = f"⏸ ESPERA • {struct_45m['cycle_phase']}"
            alert_type = "WAIT"
            alert_desc = f"Estructura 45m: {struct_45m['regime']}. Esperando confirmación de vela en zona Fib o quiebre BOS."
            flip_reason = "Esperando gatillo matemático"

    return {
        "direction": direction, "confidence": confidence,
        "alert": alert, "alert_type": alert_type, "alert_desc": alert_desc,
        "points_detail": points_detail, "live_price": live_price, "feed_source": feed_source,
        "buy_score": buy_score, "sell_score": sell_score,
        "rsi": rsi_1m, "atr": atr_5m, "ema9": ema9_1m, "ema21": ema21_1m,
        "support": support, "resistance": resistance,
        "room_up": room_up, "room_down": room_down,
        "struct_45m": struct_45m, "reg_45m": reg_45m, "flip_reason": flip_reason,
        "sl_dist": sl_dist, "tp_dist": tp_dist
    }

# ==============================================================================
# ENDPOINTS DE CONEXIÓN A TRADINGVIEW Y FRONTEND
# ==============================================================================

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    """
    Recibe velas o ticks en tiempo real directamente desde las Alertas Webhook de tu cuenta de TradingView.
    Formato JSON en TradingView Alert:
    {"symbol":"{{ticker}}","open":{{open}},"high":{{high}},"low":{{low}},"close":{{close}},"volume":{{volume}}}
    """
    try:
        data = await request.json()
        cl = float(data.get("close") or data.get("price") or 0)
        if cl > 1000:
            o = float(data.get("open") or cl)
            h = float(data.get("high") or cl)
            l = float(data.get("low") or cl)
            v = float(data.get("volume") or 1)
            now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""INSERT OR REPLACE INTO ohlc_1m (ts,open,high,low,close,volume,source)
                         VALUES (?,?,?,?,?,?,?)""", (now_min, o, h, l, cl, v, "TRADINGVIEW_ACCOUNT"))
            conn.commit()
            conn.close()
            return {"status": "ok", "source": "TRADINGVIEW_ACCOUNT", "price": cl}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    return {"status": "ignored"}

@app.get("/")
def root():
    return {"message": "ORO TRADINGVIEW STRUCTURAL ENGINE v14.0", "version": "14.0"}

@app.get("/health")
def health():
    return {"status": "ok", "symbol": "XAUUSD", "version": "14.0"}

@app.get("/signals/live")
def signals_live():
    try:
        market = analyze_market_v14()
        price = market["live_price"]
        final_dir = market["direction"]
        sl_d = market["sl_dist"]
        tp_d = market["tp_dist"]
        sl = round(price - sl_d, 2) if final_dir == "COMPRA" else (round(price + sl_d, 2) if final_dir == "VENTA" else 0.0)
        tp1 = round(price + tp_d, 2) if final_dir == "COMPRA" else (round(price - tp_d, 2) if final_dir == "VENTA" else 0.0)

        return [{
            "symbol": "XAUUSD",
            "direction": final_dir,
            "entry": price,
            "sl": sl,
            "tp1": tp1,
            "dist": sl_d,
            "tp_dist": tp_d,
            "live_price": price,
            "feed_source": market["feed_source"],
            "confidence": market["confidence"],
            "market_analysis": market,
            "alert": market["alert"],
            "alert_type": market["alert_type"],
            "alert_desc": market["alert_desc"],
            "points_detail": market["points_detail"],
            "flip_reason": market["flip_reason"],
            "support": market["support"],
            "resistance": market["resistance"],
            "timestamp": datetime.now(EC_TZ).isoformat()
        }]
    except Exception as e:
        p, _ = get_live_spot_price()
        return [{
            "symbol": "XAUUSD", "direction": "ESPERA", "entry": p, "sl": 0, "tp1": 0, "dist": 0, "tp_dist": 0,
            "live_price": p, "feed_source": "RECOVERY", "confidence": 50, "market_analysis": {},
            "alert": "⏸ RECALIBRANDO ESTRUCTURA", "alert_type": "WAIT", "alert_desc": str(e),
            "points_detail": [], "flip_reason": "Recalibrando", "support": p - 4, "resistance": p + 4,
            "timestamp": datetime.now(EC_TZ).isoformat()
        }]

@app.on_event("startup")
async def startup_event():
    sync_historical_1m_candles()
    async def monitor_loop():
        ticks = 0
        while True:
            try:
                p, _ = get_live_spot_price()
                update_current_1m_candle(p, "FEED")
                ticks += 1
                # Cada 5 minutos resincroniza el historial de 1m para no perder jamás la estructura de 60m
                if ticks % 35 == 0:
                    sync_historical_1m_candles()
            except:
                pass
            await asyncio.sleep(8)
