import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - QUANT INSTITUCIONAL v12.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price REAL,
        timestamp TEXT,
        change REAL DEFAULT 0,
        high REAL DEFAULT 0,
        low REAL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (
        symbol TEXT PRIMARY KEY,
        direction TEXT,
        confirmed_at TEXT,
        consecutive_count INTEGER DEFAULT 0,
        phase TEXT
    )""")
    # Migrar columna entry_price si no existe para rastrear ganancia en vivo
    try:
        c.execute("ALTER TABLE last_signal ADD COLUMN entry_price REAL DEFAULT 0")
    except:
        pass
    conn.commit()
    conn.close()

init_db()

class TradeResult(BaseModel):
    result: str
    symbol: Optional[str] = "XAUUSD"

def get_gold_price():
    """Obtiene el precio Spot real del Oro (XAU/USD) sin caché usando feed bancario Swissquote + respaldos"""
    # 1. Fuente Primaria: Swissquote Bank Live Spot XAU/USD (Bid/Ask real al milisegundo)
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
                        return round((bid + ask) / 2.0, 2)
    except:
        pass
    # 2. Respaldo: Gold-API
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code == 200 and r.json().get("price"):
            p = float(r.json()["price"])
            if p > 1000:
                return round(p, 2)
    except:
        pass
    # 3. Respaldo: GoldPrice.org
    try:
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=3)
        if r.status_code == 200:
            for it in r.json().get("items", []):
                if it.get("curr") == "XAU" and it.get("xauPrice", 0) > 0:
                    return round(float(it["xauPrice"]), 2)
    except:
        pass
    return 3948.00

def seed_history_if_empty():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM price_history")
        if c.fetchone()[0] < 120:
            base = get_gold_price()
            now = datetime.now(EC_TZ)
            for i in range(240):
                variation = math.sin(i / 12.0) * 2.5 + math.cos(i / 5.0) * 1.2
                p = round(base + variation, 2)
                ts = (now - timedelta(seconds=(240 - i) * 15)).isoformat()
                c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)",
                          (p, ts, 0.0, p + 0.4, p - 0.4))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Seed error: {e}")

def save_gold_history(price):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT price, timestamp FROM price_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        now = datetime.now(EC_TZ)
        # Evitar guardar duplicados si han pasado menos de 8 segundos
        if last and last[1]:
            try:
                last_dt = datetime.fromisoformat(last[1])
                if (now - last_dt).total_seconds() < 8 and abs(price - last[0]) < 0.05:
                    conn.close()
                    return
            except:
                pass
        change = round(price - last[0], 2) if last else 0.0
        c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)",
                  (price, now.isoformat(), change, price, price))
        c.execute("DELETE FROM price_history WHERE id NOT IN (SELECT id FROM price_history ORDER BY id DESC LIMIT 1800)")
        conn.commit()
        conn.close()
    except:
        pass

def get_gold_history(limit=1200):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT price,timestamp,change,high,low FROM price_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows[::-1]
    except:
        return []

def build_candles(rows, ticks_per_candle=20):
    """Construye velas reales asegurando que la última vela incluya siempre el tick más reciente"""
    if len(rows) < ticks_per_candle:
        return []
    candles = []
    # Alineamos desde el final hacia atrás para que la última vela esté siempre actualizada al segundo
    total = len(rows)
    rem = total % ticks_per_candle
    start_idx = rem if rem > 0 else 0
    for i in range(start_idx, total, ticks_per_candle):
        chunk = rows[i:i + ticks_per_candle]
        if not chunk:
            continue
        prices = [r[0] for r in chunk]
        o, cl = prices[0], prices[-1]
        hi, lo = max(prices), min(prices)
        body = abs(cl - o)
        rng = max(hi - lo, 0.05)
        bullish = cl >= o
        ratio = body / rng
        upper_wick = hi - max(o, cl)
        lower_wick = min(o, cl) - lo
        candles.append({
            "open": o, "close": cl, "high": hi, "low": lo,
            "range": rng, "body": body, "body_ratio": ratio,
            "upper_wick": upper_wick, "lower_wick": lower_wick,
            "bullish": bullish, "strong": ratio > 0.58 and body > 0.6
        })
    return candles

def calc_ema(values, period):
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v * k) + (ema * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calc_atr(candles, period=14):
    if len(candles) < 2:
        return 2.5
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1]["close"]
        tr = max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
        trs.append(tr)
    recent_trs = trs[-period:] if len(trs) >= period else trs
    return max(sum(recent_trs) / len(recent_trs), 1.2)

def calc_antigravity_bands(closes, period=20, dev=2.2):
    if len(closes) < period:
        return None
    recent = closes[-period:]
    mean = sum(recent) / period
    std_dev = math.sqrt(sum((p - mean) ** 2 for p in recent) / period)
    upper = mean + (dev * std_dev)
    lower = mean - (dev * std_dev)
    rng = max(upper - lower, 0.5)
    current = closes[-1]
    percent_b = (current - lower) / rng  # 0.0 = suelo, 1.0 = techo
    return {
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "mean": round(mean, 2),
        "std": round(std_dev, 2),
        "percent_b": round(percent_b, 2)
    }

def detect_smc_zones(candles, live_price):
    """Detecta Order Blocks y FVG que aún NO han sido rotos y evalúa si el precio está reaccionando en ellos"""
    if len(candles) < 6:
        return []
    signals = []
    # Analizamos las últimas 6 velas cerradas buscando huellas institucionales vigentes
    for i in range(len(candles) - 5, len(candles) - 1):
        c1, c2, c3 = candles[i - 1], candles[i], candles[i + 1]
        # Order Block Alcista + Rechazo
        if not c1["bullish"] and c2["bullish"] and c2["strong"] and c2["close"] > c1["high"]:
            ob_top, ob_bottom = c1["high"], c1["low"]
            if ob_bottom - 0.8 <= live_price <= ob_top + 1.2:
                signals.append({"name": "ORDER BLOCK ALCISTA", "dir": "COMPRA", "points": 4, "level": round((ob_top + ob_bottom) / 2, 2), "reason": f"Demanda institucional activa en {ob_bottom:.2f}-{ob_top:.2f}"})
        # Order Block Bajista + Rechazo
        if c1["bullish"] and not c2["bullish"] and c2["strong"] and c2["close"] < c1["low"]:
            ob_top, ob_bottom = c1["high"], c1["low"]
            if ob_bottom - 1.2 <= live_price <= ob_top + 0.8:
                signals.append({"name": "ORDER BLOCK BAJISTA", "dir": "VENTA", "points": 4, "level": round((ob_top + ob_bottom) / 2, 2), "reason": f"Oferta institucional activa en {ob_bottom:.2f}-{ob_top:.2f}"})
        # FVG Alcista
        if c1["high"] < c3["low"] and c2["bullish"]:
            if c1["high"] - 0.5 <= live_price <= c3["low"] + 1.0:
                signals.append({"name": "FVG ALCISTA (IMBALANCE)", "dir": "COMPRA", "points": 3, "level": round(c1["high"], 2), "reason": f"Rellenando vacío de liquidez alcista ({c1['high']:.2f})"})
        # FVG Bajista
        if c1["low"] > c3["high"] and not c2["bullish"]:
            if c3["high"] - 1.0 <= live_price <= c1["low"] + 0.5:
                signals.append({"name": "FVG BAJISTA (IMBALANCE)", "dir": "VENTA", "points": 3, "level": round(c1["low"], 2), "reason": f"Rellenando vacío de liquidez bajista ({c1['low']:.2f})"})
    # Evitar duplicados del mismo tipo
    unique = {}
    for s in signals:
        unique[s["name"]] = s
    return list(unique.values())

def analyze_structure_and_fib(candles, live_price, ema21, ema50):
    """Analiza el Swing High y Swing Low real para detectar Impulso, Retroceso OTE (0.5-0.618) y BOS"""
    if len(candles) < 12:
        return None
    lookback = candles[-16:-1]  # Excluimos la vela actual para medir la estructura previa real
    swing_high = max(c["high"] for c in lookback)
    swing_low = min(c["low"] for c in lookback)
    rng = swing_high - swing_low
    if rng < 3.0:
        return {
            "dir": "LATERAL", "range": round(rng, 2), "state": "RANGO ESTRECHO",
            "action": "NO OPERAR (CONSOLIDACIÓN)", "swing_high": round(swing_high, 2), "swing_low": round(swing_low, 2),
            "levels": {"0": round(swing_high, 2), "0.5": round((swing_high + swing_low) / 2, 2), "0.618": round(swing_low + rng * 0.382, 2), "1": round(swing_low, 2)}
        }

    # Determinar cuál extremo ocurrió primero
    high_idx = max(i for i, c in enumerate(lookback) if c["high"] == swing_high)
    low_idx = max(i for i, c in enumerate(lookback) if c["low"] == swing_low)
    is_bullish = (high_idx > low_idx) and (ema21 >= ema50 - 0.5)

    if is_bullish:
        # Impulso Alcista: 1.0 es el suelo (inicio), 0.0 es el techo (fin del impulso)
        fibs = {
            "0": round(swing_high, 2),
            "0.382": round(swing_high - rng * 0.382, 2),
            "0.5": round(swing_high - rng * 0.500, 2),
            "0.618": round(swing_high - rng * 0.618, 2),
            "0.786": round(swing_high - rng * 0.786, 2),
            "1": round(swing_low, 2)
        }
        if live_price <= fibs["0.382"] and live_price >= fibs["0.786"]:
            state = "RETROCESO A ZONA DORADA (COMPRA)"
            action = "BUSCAR REBOTE ALCISTA EN FIB 0.5 / 0.618"
        elif live_price > swing_high:
            state = "RUPTURA ALCISTA (BOS)"
            action = "CONTINUACIÓN ALCISTA (CUIDAR TECHO)"
        elif live_price < swing_low:
            state = "CAMBIO DE CARÁCTER BAJISTA (CHoCH)"
            action = "ESTRUCTURA ALCISTA ROTA -> VENTA"
        else:
            state = "IMPULSO ALCISTA ACTIVO"
            action = "MANTENER COMPRA HASTA RESISTENCIA"
        dir_str = "ALCISTA"
    else:
        # Impulso Bajista: 1.0 es el techo (inicio), 0.0 es el suelo (fin del impulso)
        fibs = {
            "0": round(swing_low, 2),
            "0.382": round(swing_low + rng * 0.382, 2),
            "0.5": round(swing_low + rng * 0.500, 2),
            "0.618": round(swing_low + rng * 0.618, 2),
            "0.786": round(swing_low + rng * 0.786, 2),
            "1": round(swing_high, 2)
        }
        if live_price >= fibs["0.382"] and live_price <= fibs["0.786"]:
            state = "RETROCESO A ZONA DORADA (VENTA)"
            action = "BUSCAR RECHAZO BAJISTA EN FIB 0.5 / 0.618"
        elif live_price < swing_low:
            state = "RUPTURA BAJISTA (BOS)"
            action = "CONTINUACIÓN BAJISTA (CUIDAR SUELO)"
        elif live_price > swing_high:
            state = "CAMBIO DE CARÁCTER ALCISTA (CHoCH)"
            action = "ESTRUCTURA BAJISTA ROTA -> COMPRA"
        else:
            state = "IMPULSO BAJISTA ACTIVO"
            action = "MANTENER VENTA HASTA SOPORTE"
        dir_str = "BAJISTA"

    return {
        "dir": dir_str, "range": round(rng, 2), "state": state, "action": action,
        "swing_high": round(swing_high, 2), "swing_low": round(swing_low, 2), "levels": fibs
    }

def get_last_signal():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, phase, entry_price FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone()
        conn.close()
        if row:
            return {"direction": row[0], "confirmed_at": row[1], "phase": row[2], "entry_price": float(row[3] or 0)}
    except:
        pass
    return {"direction": "ESPERA", "confirmed_at": datetime.now(EC_TZ).isoformat(), "phase": "INICIO", "entry_price": 0.0}

def update_last_signal(direction, phase, entry_price=0.0):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,phase,entry_price) VALUES (?,?,?,?,?)",
                  ("XAUUSD", direction, datetime.now(EC_TZ).isoformat(), phase, entry_price))
        conn.commit()
        conn.close()
    except:
        pass

def analyze_gold_quant(live_price):
    rows = get_gold_history(1200)
    if len(rows) < 60:
        return {
            "direction": "ESPERA", "confidence": 50, "alert": "⏳ CALIBRANDO HISTORIAL...",
            "alert_type": "WAIT", "alert_desc": "Recolectando datos del mercado en vivo.",
            "points_detail": [], "live_price": live_price, "buy_score": 0, "sell_score": 0,
            "rsi": 50.0, "atr": 3.0, "support": live_price - 5, "resistance": live_price + 5,
            "room_up": 5.0, "room_down": 5.0, "ag_bands": None, "expert_fib": None, "flip_reason": "Iniciando"
        }

    # Asegurar que el último registro tenga el precio vivo actual
    rows[-1] = (live_price, rows[-1][1], rows[-1][2], max(rows[-1][3], live_price), min(rows[-1][4], live_price))
    candles = build_candles(rows, ticks_per_candle=16)  # Velas dinámicas de alta precisión
    closes = [c["close"] for c in candles]
    last_c = candles[-1]
    prev_c = candles[-2] if len(candles) >= 2 else last_c

    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 40)
    rsi = calc_rsi(closes, 14)
    atr = calc_atr(candles, 14)
    ag_bands = calc_antigravity_bands(closes, period=20, dev=2.2)
    smc_zones = detect_smc_zones(candles, live_price)
    fib_info = analyze_structure_and_fib(candles, live_price, ema21, ema50)

    support = fib_info["swing_low"] if fib_info else round(live_price - 5.0, 2)
    resistance = fib_info["swing_high"] if fib_info else round(live_price + 5.0, 2)
    if ag_bands:
        support = min(support, ag_bands["lower"])
        resistance = max(resistance, ag_bands["upper"])

    room_up = round(max(0.0, resistance - live_price), 2)
    room_down = round(max(0.0, live_price - support), 2)

    buy_score = 0
    sell_score = 0
    points_detail = []

    # 1. PUNTUACIÓN POR ESTRUCTURA Y FIBONACCI (OTE 0.5 - 0.618)
    if fib_info and fib_info["dir"] != "LATERAL":
        st = fib_info["state"]
        if st == "RETROCESO A ZONA DORADA (COMPRA)":
            # Confirmar que la vela actual está frenando la caída o rebotando
            if last_c["bullish"] or last_c["lower_wick"] > last_c["body"]:
                buy_score += 5
                points_detail.append({"side": "COMPRA", "points": 5, "name": "REBOTE EN FIBONACCI (OTE)", "reason": f"Retroceso alcista confirmado en zona dorada ({fib_info['levels']['0.5']} - {fib_info['levels']['0.618']})"})
        elif st == "RETROCESO A ZONA DORADA (VENTA)":
            if not last_c["bullish"] or last_c["upper_wick"] > last_c["body"]:
                sell_score += 5
                points_detail.append({"side": "VENTA", "points": 5, "name": "RECHAZO EN FIBONACCI (OTE)", "reason": f"Retroceso bajista rechazado en zona dorada ({fib_info['levels']['0.5']} - {fib_info['levels']['0.618']})"})
        elif st == "CAMBIO DE CARÁCTER ALCISTA (CHoCH)":
            buy_score += 4
            points_detail.append({"side": "COMPRA", "points": 4, "name": "QUIEBRE ALCISTA (CHoCH)", "reason": f"Superó el máximo estructural previo ({fib_info['swing_high']})"})
        elif st == "CAMBIO DE CARÁCTER BAJISTA (CHoCH)":
            sell_score += 4
            points_detail.append({"side": "VENTA", "points": 4, "name": "QUIEBRE BAJISTA (CHoCH)", "reason": f"Rompió el soporte estructural previo ({fib_info['swing_low']})"})

    # 2. PUNTUACIÓN ANTIGRAVITY (REVERSIÓN EN EXTREMOS)
    if ag_bands:
        pb = ag_bands["percent_b"]
        if pb <= 0.08 and (last_c["bullish"] or last_c["lower_wick"] > last_c["body"]):
            buy_score += 5
            points_detail.append({"side": "COMPRA", "points": 5, "name": "SUELO ANTIGRAVITY (-2.2 SD)", "reason": f"Agotamiento vendedor extremo en {ag_bands['lower']} con rechazo alcista."})
        elif pb >= 0.92 and (not last_c["bullish"] or last_c["upper_wick"] > last_c["body"]):
            sell_score += 5
            points_detail.append({"side": "VENTA", "points": 5, "name": "TECHO ANTIGRAVITY (+2.2 SD)", "reason": f"Agotamiento comprador extremo en {ag_bands['upper']} con rechazo bajista."})

    # 3. PUNTUACIÓN SMART MONEY (ORDER BLOCKS / FVG)
    for z in smc_zones:
        if z["dir"] == "COMPRA" and (last_c["bullish"] or last_c["lower_wick"] >= last_c["body"]):
            buy_score += z["points"]
            points_detail.append({"side": "COMPRA", "points": z["points"], "name": z["name"], "reason": z["reason"]})
        elif z["dir"] == "VENTA" and (not last_c["bullish"] or last_c["upper_wick"] >= last_c["body"]):
            sell_score += z["points"]
            points_detail.append({"side": "VENTA", "points": z["points"], "name": z["name"], "reason": z["reason"]})

    # 4. ALINEACIÓN DE FLUJO INSTITUCIONAL (EMAs + Acción del Precio)
    if ema9 > ema21 > ema50 and live_price > ema9 and last_c["bullish"]:
        buy_score += 3
        points_detail.append({"side": "COMPRA", "points": 3, "name": "FLUJO EMA ALCISTA", "reason": f"Alineación EMA9 ({ema9:.1f}) > EMA21 ({ema21:.1f}) > EMA50 ({ema50:.1f})"})
    elif ema9 < ema21 < ema50 and live_price < ema9 and not last_c["bullish"]:
        sell_score += 3
        points_detail.append({"side": "VENTA", "points": 3, "name": "FLUJO EMA BAJISTA", "reason": f"Alineación EMA9 ({ema9:.1f}) < EMA21 ({ema21:.1f}) < EMA50 ({ema50:.1f})"})

    # 5. REGLA DE ORO: BLOQUEO DE COMPRAS EN EL TECHO Y VENTAS EN EL SUELO (VETO DE RIESGO)
    pb_val = ag_bands["percent_b"] if ag_bands else 0.5
    if buy_score > 0:
        if rsi >= 68 or (pb_val >= 0.78 and room_up < 2.8):
            buy_score = 0
            points_detail = [p for p in points_detail if p["side"] != "COMPRA"]
            points_detail.append({"side": "INFO", "points": 0, "name": "⛔ COMPRA BLOQUEADA EN TECHO", "reason": f"Protección activada: Precio muy cerca de la resistencia ({resistance:.2f}) o RSI sobrecomprado ({rsi}). Prohibido comprar arriba."})

    if sell_score > 0:
        if rsi <= 32 or (pb_val <= 0.22 and room_down < 2.8):
            sell_score = 0
            points_detail = [p for p in points_detail if p["side"] != "VENTA"]
            points_detail.append({"side": "INFO", "points": 0, "name": "⛔ VENTA BLOQUEADA EN SUELO", "reason": f"Protección activada: Precio muy cerca del soporte ({support:.2f}) o RSI sobrevendido ({rsi}). Prohibido vender abajo."})

    # 6. GESTIÓN DE POSICIÓN ACTIVA (CICLO: ENTRADA -> TOMAR GANANCIA / SALIR)
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price

    # Evaluar si tenemos una operación en curso
    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        # Caso A: Llevamos ganancia (>= $2.20) y llegamos al techo / RSI alto / Fib objetivo
        if pnl >= 2.20 and (pb_val >= 0.80 or rsi >= 67 or not last_c["bullish"]):
            update_last_signal("ESPERA", "TP_COMPRA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 92,
                "alert": f"💰 ASEGURA GANANCIA COMPRA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"Subió de {entry_p:.2f} a {live_price:.2f} y llegó a zona de resistencia. Cierra en ganancia ahora.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "ag_bands": ag_bands, "expert_fib": fib_info,
                "flip_reason": f"Take Profit alcanzado (+${pnl:.2f})"
            }
        # Caso B: El mercado se giró en contra con fuerza -> SALIR sin abrir venta en el suelo
        if pnl <= -2.20 or (live_price < ema21 and not last_c["bullish"] and sell_score >= 4):
            update_last_signal("ESPERA", "EXIT_COMPRA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 85,
                "alert": f"🔴 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "El impulso alcista perdió fuerza bajo la EMA21. Cierra la compra para proteger tu cuenta y espera.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "ag_bands": ag_bands, "expert_fib": fib_info,
                "flip_reason": "Salida de protección ejecutada"
            }

    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        # Caso A: Llevamos ganancia en VENTA (>= $2.20) y tocamos suelo / soporte
        if pnl >= 2.20 and (pb_val <= 0.20 or rsi <= 33 or last_c["bullish"]):
            update_last_signal("ESPERA", "TP_VENTA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 92,
                "alert": f"💰 ASEGURA GANANCIA VENTA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"Cayó de {entry_p:.2f} a {live_price:.2f} y tocó zona de soporte. Cierra en ganancia ahora.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "ag_bands": ag_bands, "expert_fib": fib_info,
                "flip_reason": f"Take Profit alcanzado (+${pnl:.2f})"
            }
        # Caso B: El mercado rebotó al alza en contra de nuestra venta -> SALIR de inmediato
        if pnl <= -2.20 or (live_price > ema21 and last_c["bullish"] and buy_score >= 4):
            update_last_signal("ESPERA", "EXIT_VENTA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 85,
                "alert": f"🔴 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "El precio superó la EMA21 con rechazo alcista. Cierra la venta de inmediato y espera nueva estructura.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "ag_bands": ag_bands, "expert_fib": fib_info,
                "flip_reason": "Salida de protección ejecutada"
            }

    # 7. DECISIÓN DE NUEVA ENTRADA DE ALTA PROBABILIDAD
    if buy_score >= 6 and buy_score >= sell_score + 4 and room_up >= 2.8:
        direction = "COMPRA"
        confidence = min(74 + (buy_score * 2), 96)
        alert = "✅ ENTRA COMPRA CONFIRMADA"
        alert_type = "ENTER"
        alert_desc = f"Confluencia institucional alcista con ${room_up:.2f} USD de espacio libre hacia la resistencia."
        if active_dir != "COMPRA":
            update_last_signal("COMPRA", "ACTIVA", live_price)
            flip_reason = f"Nueva entrada COMPRA en {live_price:.2f}"
        else:
            flip_reason = f"Manteniendo COMPRA desde {entry_p:.2f} ({live_price - entry_p:+.2f} USD)"

    elif sell_score >= 6 and sell_score >= buy_score + 4 and room_down >= 2.8:
        direction = "VENTA"
        confidence = min(74 + (sell_score * 2), 96)
        alert = "✅ ENTRA VENTA CONFIRMADA"
        alert_type = "ENTER"
        alert_desc = f"Confluencia institucional bajista con ${room_down:.2f} USD de espacio libre hacia el soporte."
        if active_dir != "VENTA":
            update_last_signal("VENTA", "ACTIVA", live_price)
            flip_reason = f"Nueva entrada VENTA en {live_price:.2f}"
        else:
            flip_reason = f"Manteniendo VENTA desde {entry_p:.2f} ({entry_p - live_price:+.2f} USD)"

    else:
        # Si ya teníamos una operación abierta y sigue en rango normal sin invalidarse, la mantenemos vigilada
        if active_dir in ["COMPRA", "VENTA"]:
            pnl = round(live_price - entry_p, 2) if active_dir == "COMPRA" else round(entry_p - live_price, 2)
            direction = active_dir
            confidence = 72
            alert = f"⏳ MANTENER {active_dir} EN CURSO ({pnl:+.2f} USD)"
            alert_type = "ENTER"
            alert_desc = f"Operación abierta en {entry_p:.2f}. Esperando objetivo o señal de salida."
            flip_reason = f"Vigilando posición abierta ({pnl:+.2f} USD)"
        else:
            direction = "ESPERA"
            confidence = 50
            alert = "⏸ ESPERA - BUSCANDO ZONA SEGURA"
            alert_type = "WAIT"
            alert_desc = "El precio está a mitad de rango o sin confirmación clara. Protege tu capital, no entres aún."
            flip_reason = "Sin confluencia institucional suficiente"

    return {
        "direction": direction, "confidence": confidence,
        "alert": alert, "alert_type": alert_type, "alert_desc": alert_desc,
        "points_detail": points_detail, "live_price": live_price,
        "buy_score": buy_score, "sell_score": sell_score,
        "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
        "room_up": room_up, "room_down": room_down,
        "ag_bands": ag_bands, "expert_fib": fib_info, "flip_reason": flip_reason
    }

def calc_tp_sl_smart(price, direction, atr, support, resistance):
    """Calcula SL y TP basados en la estructura real para cuenta de $50 (0.01 lotes)"""
    sl_dist = round(max(2.5, min(atr * 1.3, 3.8)), 2)
    tp_dist = round(max(2.8, min(atr * 1.6, 4.5)), 2)
    if direction == "COMPRA":
        # El TP nunca se coloca por encima de la resistencia estructural
        tp_price = min(price + tp_dist, resistance - 0.3) if (resistance - price) > 2.2 else price + tp_dist
        sl_price = price - sl_dist
        return round(sl_price, 2), round(tp_price, 2), sl_dist, round(tp_price - price, 2)
    elif direction == "VENTA":
        tp_price = max(price - tp_dist, support + 0.3) if (price - support) > 2.2 else price - tp_dist
        sl_price = price + sl_dist
        return round(sl_price, 2), round(tp_price, 2), sl_dist, round(price - tp_price, 2)
    return 0.0, 0.0, 0.0, 0.0

@app.get("/")
def root():
    return {"message": "ORO QUANT INSTITUCIONAL v12.0", "version": "12.0"}

@app.get("/health")
def health():
    return {"status": "ok", "symbol": "XAUUSD", "version": "12.0"}

@app.get("/signals/live")
def signals_live():
    try:
        price = get_gold_price()
        save_gold_history(price)
        market = analyze_gold_quant(price)
        final_dir = market["direction"]
        sl, tp1, sl_dist, tp_dist = calc_tp_sl_smart(
            price, final_dir, market["atr"], market["support"], market["resistance"]
        )
        signal = {
            "symbol": "XAUUSD",
            "direction": final_dir,
            "entry": price,
            "sl": sl,
            "tp1": tp1,
            "dist": sl_dist,
            "tp_dist": tp_dist,
            "live_price": price,
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
        }
        return [signal]
    except Exception as e:
        p = get_gold_price()
        return [{
            "symbol": "XAUUSD", "direction": "ESPERA", "entry": p, "sl": 0, "tp1": 0, "dist": 0, "tp_dist": 0,
            "live_price": p, "confidence": 50, "market_analysis": {}, "alert": "⏸ ESPERA - RECALIBRANDO",
            "alert_type": "WAIT", "alert_desc": str(e), "points_detail": [], "flip_reason": "Recalibrando",
            "support": p - 5, "resistance": p + 5, "timestamp": datetime.now(EC_TZ).isoformat()
        }]

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        while True:
            try:
                save_gold_history(get_gold_price())
            except:
                pass
            await asyncio.sleep(10)
    asyncio.create_task(monitor_loop())
