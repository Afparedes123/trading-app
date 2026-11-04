import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - QUANT IMPULSO & RETROCESO v13.0")
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
        phase TEXT,
        entry_price REAL DEFAULT 0
    )""")
    conn.commit()
    conn.close()

init_db()

class TradeResult(BaseModel):
    result: str
    symbol: Optional[str] = "XAUUSD"

def get_gold_price():
    """Obtiene el precio Spot real del Oro (XAU/USD) con feed Swissquote + respaldos"""
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
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code == 200 and r.json().get("price"):
            p = float(r.json()["price"])
            if p > 1000: return round(p, 2)
    except:
        pass
    try:
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=3)
        if r.status_code == 200:
            for it in r.json().get("items", []):
                if it.get("curr") == "XAU" and it.get("xauPrice", 0) > 0:
                    return round(float(it["xauPrice"]), 2)
    except:
        pass
    return 3945.00

def seed_history_if_empty():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM price_history")
        if c.fetchone()[0] < 120:
            base = get_gold_price()
            now = datetime.now(EC_TZ)
            for i in range(240):
                variation = math.sin(i / 10.0) * 2.2 + math.cos(i / 4.0) * 1.0
                p = round(base + variation, 2)
                ts = (now - timedelta(seconds=(240 - i) * 15)).isoformat()
                c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)",
                          (p, ts, 0.0, p + 0.3, p - 0.3))
            conn.commit()
        conn.close()
    except:
        pass

def save_gold_history(price):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT price, timestamp FROM price_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        now = datetime.now(EC_TZ)
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

def build_candles(rows, ticks_per_candle=12):
    """Velas diseñadas para M5 (12 ticks por vela) asegurando actualización en vivo"""
    if len(rows) < ticks_per_candle:
        return []
    candles = []
    total = len(rows)
    rem = total % ticks_per_candle
    start_idx = rem if rem > 0 else 0
    for i in range(start_idx, total, ticks_per_candle):
        chunk = rows[i:i + ticks_per_candle]
        if not chunk: continue
        prices = [r[0] for r in chunk]
        o, cl = prices[0], prices[-1]
        hi, lo = max(prices), min(prices)
        body = abs(cl - o)
        rng = max(hi - lo, 0.05)
        bullish = cl >= o
        ratio = body / rng
        candles.append({
            "open": o, "close": cl, "high": hi, "low": lo,
            "range": rng, "body": body, "body_ratio": ratio,
            "bullish": bullish, "strong": ratio > 0.55 and body > 0.5
        })
    return candles

def calc_ema(values, period):
    if not values: return 0.0
    if len(values) < period: return sum(values) / len(values)
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v * k) + (ema * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def calc_atr(candles, period=14):
    if len(candles) < 2: return 2.0
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1]["close"]
        tr = max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
        trs.append(tr)
    recent = trs[-period:] if len(trs) >= period else trs
    return max(sum(recent) / len(recent), 1.0)

def analyze_market_structure(candles, live_price, ema9, ema21):
    """Detecta simultáneamente impulsos de continuación y retrocesos limpios"""
    if len(candles) < 10:
        return {"phase": "INICIO", "action": "ESPERA", "support": live_price - 4, "resistance": live_price + 4}
    
    recent = candles[-12:]
    sh = max(c["high"] for c in recent)
    sl = min(c["low"] for c in recent)
    rng = sh - sl
    last_c = candles[-1]
    prev_c = candles[-2]

    # Detección de Impulso Fuerte (Velas con cuerpo grande a favor de la EMA)
    is_impulse_up = last_c["bullish"] and last_c["strong"] and live_price > ema9
    is_impulse_down = not last_c["bullish"] and last_c["strong"] and live_price < ema9

    # Detección de Retroceso (Velas pequeñas o mechas contrarias tras un impulso)
    mid_point = (sh + sl) / 2
    is_pullback_to_buy = not last_c["bullish"] and live_price >= sl and live_price <= mid_point and ema9 >= ema21
    is_pullback_to_sell = last_c["bullish"] and live_price <= sh and live_price >= mid_point and ema9 <= ema21

    if is_impulse_up:
        phase = "IMPULSO ALCISTA ACTIVO"
        action = "COMPRAR CONTINUACIÓN (MOMENTUM)"
    elif is_impulse_down:
        phase = "IMPULSO BAJISTA ACTIVO"
        action = "VENDER CONTINUACIÓN (MOMENTUM)"
    elif is_pullback_to_buy:
        phase = "RETROCESO EN ZONA DE SOPORTE"
        action = "PREPARAR COMPRA EN REBOTE"
    elif is_pullback_to_sell:
        phase = "RETROCESO EN ZONA DE RESISTENCIA"
        action = "PREPARAR VENTA EN RECHAZO"
    else:
        phase = "ACUMULACIÓN / RANGO"
        action = "ESPERAR QUIEBRE DE RANGO"

    return {
        "phase": phase, "action": action,
        "support": round(sl, 2), "resistance": round(sh, 2),
        "is_impulse_up": is_impulse_up, "is_impulse_down": is_impulse_down,
        "is_pullback_to_buy": is_pullback_to_buy, "is_pullback_to_sell": is_pullback_to_sell
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

def analyze_gold_quant_v13(live_price):
    rows = get_gold_history(1200)
    if len(rows) < 50:
        return {
            "direction": "ESPERA", "confidence": 50, "alert": "⏳ CALIBRANDO MOTOR M5...",
            "alert_type": "WAIT", "alert_desc": "Analizando impulsos y retrocesos en vivo.",
            "points_detail": [], "live_price": live_price, "buy_score": 0, "sell_score": 0,
            "rsi": 50.0, "atr": 2.5, "support": live_price - 4, "resistance": live_price + 4,
            "room_up": 4.0, "room_down": 4.0, "struct": None, "flip_reason": "Iniciando"
        }

    rows[-1] = (live_price, rows[-1][1], rows[-1][2], max(rows[-1][3], live_price), min(rows[-1][4], live_price))
    candles = build_candles(rows, ticks_per_candle=12)
    closes = [c["close"] for c in candles]
    last_c = candles[-1]

    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    rsi = calc_rsi(closes, 14)
    atr = calc_atr(candles, 14)
    struct = analyze_market_structure(candles, live_price, ema9, ema21)

    support = struct["support"]
    resistance = struct["resistance"]
    room_up = round(max(0.0, resistance - live_price), 2)
    room_down = round(max(0.0, live_price - support), 2)

    buy_score = 0
    sell_score = 0
    points_detail = []

    # 1. MOTOR DE IMPULSOS (Continuación de tendencia)
    if struct["is_impulse_up"] and rsi < 70:
        buy_score += 6
        points_detail.append({"side": "COMPRA", "points": 6, "name": "🚀 IMPULSO ALCISTA VIVO", "reason": "Vela de fuerza compradora rompiendo al alza a favor de EMA9."})
    elif struct["is_impulse_down"] and rsi > 30:
        sell_score += 6
        points_detail.append({"side": "VENTA", "points": 6, "name": "📉 IMPULSO BAJISTA VIVO", "reason": "Vela de fuerza vendedora rompiendo a la baja a favor de EMA9."})

    # 2. MOTOR DE RETROCESOS (Rebotes limpios)
    if struct["is_pullback_to_buy"] and rsi >= 38:
        buy_score += 5
        points_detail.append({"side": "COMPRA", "points": 5, "name": "🎯 RETROCESO A SOPORTE", "reason": "Precio retrocedió ordenadamente hacia la zona de demanda previa."})
    elif struct["is_pullback_to_sell"] and rsi <= 62:
        sell_score += 5
        points_detail.append({"side": "VENTA", "points": 5, "name": "🎯 RETROCESO A RESISTENCIA", "reason": "Precio retrocedió ordenadamente hacia la zona de oferta previa."})

    # 3. FILTRO ANTI-LÁTIGO / VELOCIDAD (Tick a Tick)
    if len(rows) >= 6:
        tick_diff = live_price - rows[-6][0]
        if tick_diff > 0.9:
            buy_score += 4
            points_detail.append({"side": "COMPRA", "points": 4, "name": "⚡ ACELERACIÓN COMPRADORA", "reason": f"Salto de +${tick_diff:.2f} USD en los últimos segundos."})
        elif tick_diff < -0.9:
            sell_score += 4
            points_detail.append({"side": "VENTA", "points": 4, "name": "⚡ ACELERACIÓN VENDEDORA", "reason": f"Caída de -${abs(tick_diff):.2f} USD en los últimos segundos."})

    # 4. GESTIÓN DE POSICIÓN ACTIVA Y SALIDAS
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price

    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        if pnl >= 2.00 and (rsi >= 72 or struct["is_impulse_down"] or not last_c["bullish"]):
            update_last_signal("ESPERA", "TP_COMPRA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 90,
                "alert": f"💰 ASEGURA GANANCIA COMPRA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"Impulso alcista completado desde {entry_p:.2f} a {live_price:.2f}. Cierra y asegura.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "struct": struct, "flip_reason": "Take Profit alcanzado"
            }
        if pnl <= -2.00 or struct["is_impulse_down"]:
            update_last_signal("ESPERA", "EXIT_COMPRA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 85,
                "alert": f"🔴 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "La estructura cambió a impulso bajista. Cierra tu compra para proteger el capital.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "struct": struct, "flip_reason": "Salida de protección"
            }

    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        if pnl >= 2.00 and (rsi <= 28 or struct["is_impulse_up"] or last_c["bullish"]):
            update_last_signal("ESPERA", "TP_VENTA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 90,
                "alert": f"💰 ASEGURA GANANCIA VENTA (+${pnl:.2f} USD)",
                "alert_type": "TAKE_PROFIT",
                "alert_desc": f"Impulso bajista completado desde {entry_p:.2f} a {live_price:.2f}. Cierra y asegura.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "struct": struct, "flip_reason": "Take Profit alcanzado"
            }
        if pnl <= -2.00 or struct["is_impulse_up"]:
            update_last_signal("ESPERA", "EXIT_VENTA", 0.0)
            return {
                "direction": "ESPERA", "confidence": 85,
                "alert": f"🔴 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                "alert_type": "EXIT",
                "alert_desc": "La estructura cambió a impulso alcista. Cierra tu venta para proteger el capital.",
                "points_detail": points_detail, "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score,
                "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
                "room_up": room_up, "room_down": room_down, "struct": struct, "flip_reason": "Salida de protección"
            }

    # 5. TOMA DE DECISIÓN DE NUEVA ENTRADA
    if buy_score >= 5 and buy_score >= sell_score + 3:
        direction = "COMPRA"
        confidence = min(75 + (buy_score * 3), 96)
        alert = "✅ ENTRA COMPRA (IMPULSO / REBOTE)"
        alert_type = "ENTER"
        alert_desc = f"Señal limpia en zona de confluencia M5. Espacio libre al techo: +${room_up:.2f} USD."
        if active_dir != "COMPRA":
            update_last_signal("COMPRA", "ACTIVA", live_price)
            flip_reason = f"Entrada COMPRA en {live_price:.2f}"
        else:
            flip_reason = f"Manteniendo COMPRA ({live_price - entry_p:+.2f} USD)"

    elif sell_score >= 5 and sell_score >= buy_score + 3:
        direction = "VENTA"
        confidence = min(75 + (sell_score * 3), 96)
        alert = "✅ ENTRA VENTA (IMPULSO / RECHAZO)"
        alert_type = "ENTER"
        alert_desc = f"Señal limpia en zona de confluencia M5. Espacio libre al suelo: -${room_down:.2f} USD."
        if active_dir != "VENTA":
            update_last_signal("VENTA", "ACTIVA", live_price)
            flip_reason = f"Entrada VENTA en {live_price:.2f}"
        else:
            flip_reason = f"Manteniendo VENTA ({entry_p - live_price:+.2f} USD)"

    else:
        if active_dir in ["COMPRA", "VENTA"]:
            pnl = round(live_price - entry_p, 2) if active_dir == "COMPRA" else round(entry_p - live_price, 2)
            direction = active_dir
            confidence = 72
            alert = f"⏳ MANTENER {active_dir} ({pnl:+.2f} USD)"
            alert_type = "ENTER"
            alert_desc = f"Posición abierta en {entry_p:.2f}. Monitoreando impulso M5."
            flip_reason = f"Posición en curso ({pnl:+.2f} USD)"
        else:
            direction = "ESPERA"
            confidence = 50
            alert = "⏸ ESPERA - BUSCANDO IMPULSO LIMPIO"
            alert_type = "WAIT"
            alert_desc = "El mercado está transicionando. Espera la siguiente vela de impulso o retroceso."
            flip_reason = "Sin confluencia suficiente"

    return {
        "direction": direction, "confidence": confidence,
        "alert": alert, "alert_type": alert_type, "alert_desc": alert_desc,
        "points_detail": points_detail, "live_price": live_price,
        "buy_score": buy_score, "sell_score": sell_score,
        "rsi": rsi, "atr": round(atr, 2), "support": support, "resistance": resistance,
        "room_up": room_up, "room_down": room_down,
        "struct": struct, "flip_reason": flip_reason
    }

def calc_tp_sl_m5(price, direction, atr):
    sl_dist = round(max(2.0, min(atr * 1.1, 3.2)), 2)
    tp_dist = round(max(2.5, min(atr * 1.4, 3.8)), 2)
    if direction == "COMPRA":
        return round(price - sl_dist, 2), round(price + tp_dist, 2), sl_dist, tp_dist
    elif direction == "VENTA":
        return round(price + sl_dist, 2), round(price - tp_dist, 2), sl_dist, tp_dist
    return 0.0, 0.0, 0.0, 0.0

@app.get("/")
def root(): return {"message": "ORO QUANT M5 v13.0", "version": "13.0"}

@app.get("/health")
def health(): return {"status": "ok", "symbol": "XAUUSD", "version": "13.0"}

@app.get("/signals/live")
def signals_live():
    try:
        price = get_gold_price()
        save_gold_history(price)
        market = analyze_gold_quant_v13(price)
        final_dir = market["direction"]
        sl, tp1, sl_dist, tp_dist = calc_tp_sl_m5(price, final_dir, market["atr"])
        signal = {
            "symbol": "XAUUSD", "direction": final_dir, "entry": price,
            "sl": sl, "tp1": tp1, "dist": sl_dist, "tp_dist": tp_dist,
            "live_price": price, "confidence": market["confidence"],
            "market_analysis": market, "alert": market["alert"],
            "alert_type": market["alert_type"], "alert_desc": market["alert_desc"],
            "points_detail": market["points_detail"], "flip_reason": market["flip_reason"],
            "support": market["support"], "resistance": market["resistance"],
            "timestamp": datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        p = get_gold_price()
        return [{
            "symbol": "XAUUSD", "direction": "ESPERA", "entry": p, "sl": 0, "tp1": 0, "dist": 0, "tp_dist": 0,
            "live_price": p, "confidence": 50, "market_analysis": {}, "alert": "⏸ ESPERA - ERROR",
            "alert_type": "WAIT", "alert_desc": str(e), "points_detail": [], "flip_reason": "Error",
            "support": p - 4, "resistance": p + 4, "timestamp": datetime.now(EC_TZ).isoformat()
        }]

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        while True:
            try: save_gold_history(get_gold_price())
            except: pass
            await asyncio.sleep(8)
    asyncio.create_task(monitor_loop())
