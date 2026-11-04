import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - EXPERTO INSTITUCIONAL")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, price REAL, timestamp TEXT, change REAL DEFAULT 0, high REAL DEFAULT 0, low REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS last_signal (symbol TEXT PRIMARY KEY, direction TEXT, confirmed_at TEXT, phase TEXT)")
    conn.commit(); conn.close()
init_db()

class TradeResult(BaseModel): result: str; symbol: Optional[str] = "XAUUSD"

def get_gold_price():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code==200 and r.json().get("price"): return float(r.json()["price"])
    except: pass
    try:
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=3)
        if r.status_code==200:
            for it in r.json().get("items",[]):
                if it.get("curr")=="XAU" and it.get("xauPrice",0)>0: return float(it["xauPrice"])
    except: pass
    return 4052.70 + (datetime.now().hour-12)*1.5

def save_gold_history(price):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price FROM price_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        change = price-last[0] if last else 0
        c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)", (price, datetime.now(EC_TZ).isoformat(), change, price, price))
        c.execute("DELETE FROM price_history WHERE id NOT IN (SELECT id FROM price_history ORDER BY id DESC LIMIT 1500)")
        conn.commit(); conn.close()
    except: pass

def get_gold_history(limit=1000):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price,timestamp,change,high,low FROM price_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall(); conn.close()
        return rows[::-1]
    except: return []

def build_candles(rows, points):
    candles=[]
    if len(rows)<points: return []
    for i in range(0,len(rows),points):
        chunk=rows[i:i+points]
        if len(chunk)<points*0.5: continue
        prices=[r[0] for r in chunk]
        if not prices: continue
        o=prices[0]; cl=prices[-1]; hi=max(prices); lo=min(prices)
        body=abs(cl-o); rng=hi-lo if hi!=lo else 0.1
        bullish=cl>o; ratio=body/rng if rng>0 else 0
        candles.append({"open":o,"close":cl,"high":hi,"low":lo,"range":rng,"body":body,"bullish":bullish,"strong":ratio>0.6})
    return candles

def calc_antigravity_bands(prices, period=40, dev=2.2):
    if len(prices) < period: return None
    recent = prices[-period:]
    mean = sum(recent) / period
    std_dev = math.sqrt(sum((p - mean) ** 2 for p in recent) / period)
    return { "upper": mean + (dev * std_dev), "lower": mean - (dev * std_dev), "mean": mean, "std": std_dev }

def detect_smart_money(candles):
    if len(candles) < 3: return []
    smc = []
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    # FVG (Fair Value Gaps)
    if c1["high"] < c3["low"] and c2["bullish"] and c2["strong"]: smc.append({"name": "FVG ALCISTA", "dir": "COMPRA", "strength": 4, "level": c3["low"]})
    if c1["low"] > c3["high"] and not c2["bullish"] and c2["strong"]: smc.append({"name": "FVG BAJISTA", "dir": "VENTA", "strength": 4, "level": c3["high"]})
    # Order Blocks
    if c2["strong"] and c2["bullish"] and not c1["bullish"]: smc.append({"name": "ORDER BLOCK ALCISTA", "dir": "COMPRA", "strength": 3, "level": c1["low"]})
    if c2["strong"] and not c2["bullish"] and c1["bullish"]: smc.append({"name": "ORDER BLOCK BAJISTA", "dir": "VENTA", "strength": 3, "level": c1["high"]})
    return smc

def calc_fibonacci_expert(prices):
    """Calcula Fib y determina la fase exacta del precio respecto al impulso"""
    if len(prices) < 100: return None
    recent_low = min(prices[-80:]); recent_high = max(prices[-80:])
    range_usd = recent_high - recent_low
    if range_usd < 5.0: return None # Rango muy pequeño, no es impulso operable
    
    current = prices[-1]
    low_idx = prices[::-1].index(recent_low)
    high_idx = prices[::-1].index(recent_high)
    
    # Si el bajo es más antiguo que el alto = Impulso Alcista
    is_bullish_impulse = low_idx > high_idx
    
    if is_bullish_impulse:
        fibs = { "0": recent_high, "0.236": recent_high - range_usd*0.236, "0.5": recent_high - range_usd*0.5, "0.618": recent_high - range_usd*0.618, "1": recent_low }
        dir_impulse = "ALCISTA"
    else:
        fibs = { "0": recent_low, "0.236": recent_low + range_usd*0.236, "0.5": recent_low + range_usd*0.5, "0.618": recent_low + range_usd*0.618, "1": recent_high }
        dir_impulse = "BAJISTA"

    # LÓGICA EXPERTA DE ESTADOS
    state = "RANGO"
    action = "ESPERA"
    
    # 1. EVALUAR RETROCESO (Pullback a la Zona Dorada)
    if is_bullish_impulse and current < fibs["0.236"] and current > fibs["0.618"]:
        state = "RETROCESO BAJISTA"
        if abs(current - fibs["0.5"]) < 1.0 or abs(current - fibs["0.618"]) < 1.0:
            action = "PREPARAR COMPRA (Rebote Fib)"
        else:
            action = "ASEGURA GANANCIA VENTA (Acercándose a Fib)"
            
    elif not is_bullish_impulse and current > fibs["0.236"] and current < fibs["0.618"]:
        state = "RETROCESO ALCISTA"
        if abs(current - fibs["0.5"]) < 1.0 or abs(current - fibs["0.618"]) < 1.0:
            action = "PREPARAR VENTA (Rebote Fib)"
        else:
            action = "ASEGURA GANANCIA COMPRA (Acercándose a Fib)"
            
    # 2. EVALUAR RUPTURA (Continuación de Tendencia / BOS)
    elif is_bullish_impulse and current >= fibs["0"]:
        state = "IMPULSO ALCISTA"
        action = "RE-ENTRADA COMPRA (BOS Roto)"
    elif not is_bullish_impulse and current <= fibs["0"]:
        state = "IMPULSO BAJISTA"
        action = "RE-ENTRADA VENTA (BOS Roto)"

    return { "dir": dir_impulse, "range": range_usd, "levels": fibs, "state": state, "action": action }

def analyze_gold_pro():
    try:
        rows = get_gold_history(1000)
        live_price = get_gold_price()
        if len(rows) < 50: return {"direction":"ESPERA", "confidence":50, "alert":"INICIANDO...", "alert_type":"WAIT", "points":[], "live":live_price, "buy":0, "sell":0}
        
        prices = [r[0] for r in rows]; prices[-1] = live_price 
        candles_15 = build_candles(rows, 30)
        
        ag_bands = calc_antigravity_bands(prices, period=40, dev=2.2)
        smc_pats = detect_smart_money(candles_15)
        expert_fib = calc_fibonacci_expert(prices)
        
        buy_score = 0; sell_score = 0; points_detail = []
        alert = "⏳ ANALIZANDO ESTRUCTURA"; alert_type = "WAIT"; direction = "ESPERA"; confidence = 50

        # --- 1. MÓDULO EXPERTO FIBONACCI (ASEGURAR GANANCIAS Y RE-ENTRADAS) ---
        if expert_fib:
            action = expert_fib["action"]
            if "ASEGURA GANANCIA" in action:
                alert = f"💰 {action}"
                alert_type = "TAKE_PROFIT"
                # Si vas en contra de la tendencia principal, salirse cerca del Fib
                if "VENTA" in action: sell_score += 8; direction = "VENTA"
                if "COMPRA" in action: buy_score += 8; direction = "COMPRA"
                points_detail.append({"side": "INFO", "points": 8, "name": "ZONA DE TOMA DE GANANCIAS", "reason": f"Retroceso llegando al nivel dorado de Fibonacci. Cierra para asegurar."})
            
            elif "RE-ENTRADA" in action:
                alert = f"🚀 {action}"
                alert_type = "RE_ENTRY"
                if "COMPRA" in action: buy_score += 10; direction = "COMPRA"
                if "VENTA" in action: sell_score += 10; direction = "VENTA"
                points_detail.append({"side": direction, "points": 10, "name": "RUPTURA DE ESTRUCTURA (BOS)", "reason": f"El retroceso terminó. El precio rompió el alto/bajo anterior."})

        # --- 2. MÓDULO DE AGOTAMIENTO (ANTIGRAVITY) ---
        if ag_bands:
            if live_price >= ag_bands["upper"]:
                sell_score += 6
                points_detail.append({"side": "VENTA", "points": 6, "name": "AGOTAMIENTO INSTITUCIONAL", "reason": f"Precio tocó el techo extremo (+2.2 SD)."})
            elif live_price <= ag_bands["lower"]:
                buy_score += 6
                points_detail.append({"side": "COMPRA", "points": 6, "name": "AGOTAMIENTO INSTITUCIONAL", "reason": f"Precio tocó el suelo extremo (-2.2 SD)."})

        # --- 3. MÓDULO SMART MONEY (SMC) ---
        for pat in smc_pats:
            dist = abs(live_price - pat["level"])
            if dist < 1.5: # Solo reacciona si el precio está tocando el bloque en VIVO
                if pat["dir"] == "COMPRA":
                    buy_score += pat["strength"]
                    points_detail.append({"side": "COMPRA", "points": pat["strength"], "name": pat['name'], "reason": f"Reacción exacta en bloque de órdenes / FVG."})
                else:
                    sell_score += pat["strength"]
                    points_detail.append({"side": "VENTA", "points": pat["strength"], "name": pat['name'], "reason": f"Rechazo exacto en bloque de órdenes / FVG."})

        # --- 4. FILTRO ANTI-LAG EXTREMO (MATA EL RETRASO) ---
        if len(prices) >= 8:
            micro_diff = live_price - prices[-8] # Diferencia en los últimos ~10-15 segundos
            if micro_diff > 1.0:
                buy_score += 7; sell_score = 0 
                points_detail = [p for p in points_detail if p["side"] != "VENTA"]
                points_detail.append({"side": "COMPRA", "points": 7, "name": "🚨 IMPULSO VIVO ALCISTA", "reason": f"Entrada de volumen repentina (+${micro_diff:.2f}). Ventas anuladas."})
                if alert_type == "WAIT": alert = "🟢 IMPULSO COMPRA DETECTADO"; alert_type = "ENTER"; direction = "COMPRA"
            elif micro_diff < -1.0:
                sell_score += 7; buy_score = 0
                points_detail = [p for p in points_detail if p["side"] != "COMPRA"]
                points_detail.append({"side": "VENTA", "points": 7, "name": "🚨 IMPULSO VIVO BAJISTA", "reason": f"Entrada de volumen repentina (-${abs(micro_diff):.2f}). Compras anuladas."})
                if alert_type == "WAIT": alert = "🔴 IMPULSO VENTA DETECTADO"; alert_type = "ENTER"; direction = "VENTA"

        # --- RESOLUCIÓN DEL EXPERTO ---
        if alert_type == "WAIT": # Si el Fib no forzó una decisión, decide por puntos
            if buy_score == 0 and sell_score >= 6:
                direction = "VENTA"; confidence = 80 + min(sell_score, 15); alert = "✅ ENTRA VENTA"; alert_type = "ENTER"
            elif sell_score == 0 and buy_score >= 6:
                direction = "COMPRA"; confidence = 80 + min(buy_score, 15); alert = "✅ ENTRA COMPRA"; alert_type = "ENTER"
            else:
                direction = "ESPERA"; confidence = 50

        # Bloquear operaciones en zonas muertas
        volatility = max(prices[-20:]) - min(prices[-20:]) if len(prices) >= 20 else 4.0
        if volatility < 1.5 and alert_type == "ENTER":
            direction = "ESPERA"; alert = "⏸ CONSOLIDACIÓN EXTREMA"; alert_type = "WAIT"; confidence = 50

        return {
            "direction": direction, "confidence": min(confidence, 99),
            "alert": alert, "alert_type": alert_type,
            "points_detail": points_detail, "ag_bands": ag_bands, "expert_fib": expert_fib,
            "live_price": live_price, "buy_score": buy_score, "sell_score": sell_score, "volatility": volatility
        }
    except Exception as e:
        return {"direction":"ESPERA", "confidence":50, "alert":"ERROR", "alert_type":"WAIT", "points_detail":[], "live_price":get_gold_price()}

def get_last_signal():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT direction,confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone(); conn.close()
        if row: return {"direction":row[0]}
    except: pass
    return {"direction":"ESPERA"}

def update_last_signal(direction):
    try:
        if direction == "ESPERA": return
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,phase) VALUES (?,?,?,?)", ("XAUUSD",direction,datetime.now(EC_TZ).isoformat(),""))
        conn.commit(); conn.close()
    except: pass

def calc_tp_sl(price, direction, volatility, expert_fib):
    # Gestión de Riesgo Experta: El Stop Loss se adapta a la volatilidad, el TP busca asegurar rápido.
    d = max(2.5, min(volatility * 0.7, 4.0)) 
    
    # Si hay un Fibonacci activo, el TP es inteligentemente colocado cerca de la zona clave.
    if expert_fib and expert_fib["state"] != "RANGO":
        if direction == "COMPRA" and "RETROCESO" in expert_fib["state"]:
            tp = expert_fib["levels"]["0.5"] - 0.5 # Salir un poco antes del rebote
            return price - d, tp, abs(tp - price)
        elif direction == "VENTA" and "RETROCESO" in expert_fib["state"]:
            tp = expert_fib["levels"]["0.5"] + 0.5
            return price + d, tp, abs(tp - price)

    if direction == "COMPRA": return price - d, price + (d*1.2), d
    elif direction == "VENTA": return price + d, price - (d*1.2), d
    return 0, 0, 0

@app.get("/")
def root(): return {"message":"ORO EXPERTO INSTITUCIONAL","version":"11.0"}

@app.get("/signals/live")
def signals_live():
    try:
        price = get_gold_price(); save_gold_history(price)
        market = analyze_gold_pro()
        new_dir = market.get("direction", "ESPERA")
        
        last = get_last_signal()
        final_dir = new_dir
        
        # Filtros de Cambio Lógico Experto
        if last["direction"] != "ESPERA" and market["alert_type"] == "TAKE_PROFIT":
            flip_reason = "Asegurando ganancias cerca de zona clave."
        elif market["alert_type"] == "RE_ENTRY":
            flip_reason = "Ruptura de Estructura. Re-entrando a favor de tendencia."
        elif new_dir != "ESPERA" and last["direction"] != new_dir:
            flip_reason = "Giro de volumen detectado. Cambio de dirección."
        else:
            flip_reason = "Analizando estructura en vivo."
            if new_dir == "ESPERA": final_dir = last["direction"] # Mantiene la posición si hay consolidación breve
            
        update_last_signal(final_dir)
            
        vol = market.get("volatility", 4.0)
        sl, tp1, dist = calc_tp_sl(price, final_dir, vol, market.get("expert_fib"))
        
        signal = {
            "symbol": "XAUUSD", "direction": final_dir, "entry": price, 
            "sl": sl, "tp1": tp1, "dist": dist, "live_price": price,
            "confidence": market.get("confidence", 50),
            "market_analysis": market, 
            "alert": market.get("alert", ""), "alert_type": market.get("alert_type", ""),
            "points_detail": market.get("points_detail", []),
            "flip_reason": flip_reason, "timestamp": datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        return [{"symbol":"XAUUSD","direction":"ESPERA","entry":get_gold_price(),"sl":0,"tp1":0,"dist":0,"confidence":50,"alert":"ERROR","alert_type":"WAIT","points_detail":[],"flip_reason":str(e)}]

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        while True:
            try: save_gold_history(get_gold_price())
            except: pass
            await asyncio.sleep(10) # 10 segundos para cazar los retrocesos perfectos
    asyncio.create_task(monitor_loop())
    
