import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - SCALPER ALTA PRECISIÓN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS gold_learning (id INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, loss INTEGER DEFAULT 0, tp1 INTEGER DEFAULT 0, tp2 INTEGER DEFAULT 0, tp3 INTEGER DEFAULT 0, total_trades INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS gold_hour_learning (hour INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, total INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0, avg_range REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, price REAL, timestamp TEXT, change REAL DEFAULT 0, high REAL DEFAULT 0, low REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS last_signal (symbol TEXT PRIMARY KEY, direction TEXT, confirmed_at TEXT, consecutive_count INTEGER DEFAULT 0, phase TEXT)")
    c.execute("INSERT OR IGNORE INTO gold_learning (id,wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total) VALUES (1,18,6,12,8,5,24,11,14,7,10)")
    for h in range(24):
        c.execute("INSERT OR IGNORE INTO gold_hour_learning (hour,wins,total,buy_wins,buy_total,sell_wins,sell_total,avg_range) VALUES (?,?,?,?,?,?,?,?)", (h, 5 if 8 <= h <= 11 else 2, 7 if 8 <= h <= 11 else 4, 3, 4, 2, 3, 6.5))
    conn.commit(); conn.close()

init_db()

class TradeResult(BaseModel):
    result: str
    symbol: Optional[str] = "XAUUSD"

def get_gold_price():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=6)
        if r.status_code==200:
            p = r.json().get("price")
            if p and float(p)>1000: return float(p)
    except: pass
    try:
        r = requests.get("https://data-asg.goldprice.org/dbXRates/USD", timeout=8)
        if r.status_code==200:
            for it in r.json().get("items",[]):
                if it.get("curr")=="XAU" and it.get("xauPrice",0)>0: return float(it["xauPrice"])
    except: pass
    return 4052.70 + (datetime.now().hour-12)*1.5

def seed_history_if_empty():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM price_history")
        if c.fetchone()[0] < 100:
            base = get_gold_price()
            now = datetime.now(EC_TZ)
            for i in range(300):
                variation = math.sin(i/10)*2 + math.cos(i/7)*1.5 + (i%20-10)*0.1
                p = base + variation
                ts = (now - timedelta(seconds=(300-i)*30)).isoformat()
                c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)", (p, ts, variation*0.1, p+0.5, p-0.5))
            conn.commit()
        conn.close()
    except Exception as e: print(e)

def save_gold_history(price):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT price FROM price_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        change = price-last[0] if last else 0
        c.execute("INSERT INTO price_history (price,timestamp,change,high,low) VALUES (?,?,?,?,?)", (price, datetime.now(EC_TZ).isoformat(), change, price, price))
        c.execute("DELETE FROM price_history WHERE id NOT IN (SELECT id FROM price_history ORDER BY id DESC LIMIT 1000)")
        conn.commit(); conn.close()
    except: pass

def get_gold_history(limit=600):
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
        is_forming = len(chunk) < points
        if len(chunk)<points*0.6: continue
        prices=[r[0] for r in chunk]
        if not prices: continue
        o=prices[0]; cl=prices[-1]; hi=max(prices); lo=min(prices)
        body=abs(cl-o); rng=hi-lo if hi!=lo else 0.1
        bullish=cl>o; ratio=body/rng if rng>0 else 0
        upper=hi-max(o,cl); lower=min(o,cl)-lo
        candles.append({"open":o,"close":cl,"high":hi,"low":lo,"range":rng,"body":body,"body_ratio":ratio,"upper_wick":upper,"lower_wick":lower,"bullish":bullish,"strong":ratio>0.6,"small":ratio<0.3,"doji":ratio<0.1,"forming":is_forming,"points":len(chunk)})
    return candles

def get_closed_candles(candles):
    if not candles: return [], None
    if candles[-1].get("forming"):
        closed = candles[:-1]
        forming = candles[-1]
    else:
        closed = candles
        forming = None
    return closed, forming

def detect_candle_patterns(candles):
    if len(candles)<2: return []
    pats=[]; last=candles[-1]; prev=candles[-2]
    if not prev["bullish"] and last["bullish"] and last["open"]<prev["close"] and last["close"]>prev["open"] and last["body"]>prev["body"]*1.2:
        pats.append({"name":"ENVOLVENTE ALCISTA","dir":"COMPRA","strength":3,"desc":"Envolvente alcista fuerte"})
    if prev["bullish"] and not last["bullish"] and last["open"]>prev["close"] and last["close"]<prev["open"] and last["body"]>prev["body"]*1.2:
        pats.append({"name":"ENVOLVENTE BAJISTA","dir":"VENTA","strength":3,"desc":"Envolvente bajista fuerte"})
    if last["lower_wick"]>last["body"]*2 and last["upper_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"MARTILLO","dir":"COMPRA","strength":2,"desc":"Rechazo en bajos"})
    if last["upper_wick"]>last["body"]*2 and last["lower_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"ESTRELLA FUGAZ","dir":"VENTA","strength":2,"desc":"Rechazo en altos"})
    if last["bullish"] and last["body_ratio"]>0.8:
        pats.append({"name":"MARUBOZU ALCISTA","dir":"COMPRA","strength":2,"desc":"Fuerza compradora"})
    if not last["bullish"] and last["body_ratio"]>0.8:
        pats.append({"name":"MARUBOZU BAJISTA","dir":"VENTA","strength":2,"desc":"Fuerza vendedora"})
    return pats

def calc_antigravity_bands(prices, period=20, dev=2.5):
    if len(prices) < period: return None
    recent = prices[-period:]
    mean = sum(recent) / period
    variance = sum((p - mean) ** 2 for p in recent) / period
    std_dev = math.sqrt(variance)
    return { "upper": mean + (dev * std_dev), "lower": mean - (dev * std_dev), "mean": mean, "std": std_dev }

def detect_smart_money(candles):
    if len(candles) < 3: return []
    smc_signals = []
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    if c1["high"] < c3["low"] and c2["bullish"] and c2["strong"]:
        smc_signals.append({"name": "FVG ALCISTA", "dir": "COMPRA", "strength": 4, "desc": f"Vacío de liquidez confirmado"})
    if c1["low"] > c3["high"] and not c2["bullish"] and c2["strong"]:
        smc_signals.append({"name": "FVG BAJISTA", "dir": "VENTA", "strength": 4, "desc": f"Vacío de liquidez confirmado"})
    if c2["strong"] and c2["bullish"] and not c1["bullish"]:
        smc_signals.append({"name": "ORDER BLOCK ALCISTA", "dir": "COMPRA", "strength": 3, "desc": f"Bloque de órdenes {c1['low']:.2f}"})
    if c2["strong"] and not c2["bullish"] and c1["bullish"]:
        smc_signals.append({"name": "ORDER BLOCK BAJISTA", "dir": "VENTA", "strength": 3, "desc": f"Bloque de órdenes {c1['high']:.2f}"})
    return smc_signals

def get_long_sr(rows, lookback_hours=4):
    try:
        lookback = lookback_hours * 120
        prices = [r[0] for r in rows[-lookback:]] if len(rows)>=lookback else [r[0] for r in rows]
        if len(prices)<60: return None
        pivot_highs = []
        pivot_lows = []
        for i in range(5, len(prices)-5):
            is_high = True; is_low = True
            for j in range(1,4):
                if prices[i] <= prices[i-j] or prices[i] <= prices[i+j]: is_high = False
                if prices[i] >= prices[i-j] or prices[i] >= prices[i+j]: is_low = False
            if is_high: pivot_highs.append(prices[i])
            if is_low: pivot_lows.append(prices[i])
        if not pivot_highs: pivot_highs = [max(prices)]
        if not pivot_lows: pivot_lows = [min(prices)]
        def cluster_levels(levels, tolerance=1.5):
            if not levels: return []
            levels_sorted = sorted(levels)
            clusters = [[levels_sorted[0]]]
            for l in levels_sorted[1:]:
                if abs(l - sum(clusters[-1])/len(clusters[-1])) < tolerance: clusters[-1].append(l)
                else: clusters.append([l])
            result = []
            for c in clusters: result.append((sum(c)/len(c), len(c)))
            result.sort(key=lambda x: x[1], reverse=True)
            return result
        high_clusters = cluster_levels(pivot_highs, 1.5)
        low_clusters = cluster_levels(pivot_lows, 1.5)
        recent_high = max(prices); recent_low = min(prices)
        band_long = recent_high - recent_low; current = prices[-1]
        resistance = min(high_clusters, key=lambda x: abs(x[0]-current))[0] if high_clusters else recent_high
        support = min(low_clusters, key=lambda x: abs(x[0]-current))[0] if low_clusters else recent_low
        return {
            "high_long": recent_high, "low_long": recent_low, "resistance": resistance, "support": support,
            "resistance_far": recent_high, "support_far": recent_low, "high_clusters": high_clusters[:3],
            "low_clusters": low_clusters[:3], "band_long": band_long, "is_acc_long": band_long < 12.0, "lookback": lookback
        }
    except Exception: return None

def calc_fibonacci_impulse(rows):
    try:
        prices = [r[0] for r in rows[-200:]]
        if len(prices)<50: return None
        recent_low = min(prices[-100:]); recent_high = max(prices[-100:])
        low_idx = len(prices) - 1 - prices[::-1].index(recent_low) if recent_low in prices else 0
        high_idx = len(prices) - 1 - prices[::-1].index(recent_high) if recent_high in prices else 0
        if high_idx > low_idx and (recent_high - recent_low) > 8.0:
            impulse_dir, impulse_low, impulse_high, impulse_range = "ALCISTA", recent_low, recent_high, recent_high - recent_low
        elif low_idx > high_idx and (recent_high - recent_low) > 8.0:
            impulse_dir, impulse_low, impulse_high, impulse_range = "BAJISTA", recent_low, recent_high, recent_high - recent_low
        else: return None
        current = prices[-1]
        fib_levels = {
            "0.382": impulse_high - impulse_range*0.382 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.382,
            "0.5": impulse_high - impulse_range*0.5 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.5,
            "0.618": impulse_high - impulse_range*0.618 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.618,
        }
        near_fib = None; min_dist = 999
        for level, price_fib in fib_levels.items():
            dist = abs(current - price_fib)
            if dist < min_dist and dist < 1.5: min_dist, near_fib = dist, level
        return {
            "dir": impulse_dir, "low": impulse_low, "high": impulse_high, "range": impulse_range,
            "current": current, "levels": fib_levels, "near": near_fib, "dist": min_dist if near_fib else None,
            "desc": f"Impulso {impulse_dir} {impulse_low:.2f} -> {impulse_high:.2f}"
        }
    except: return None

def detect_phase(candles_10, candles_15, rows):
    if len(candles_10)<4:
        return {"phase":"INICIO","desc":"Iniciando análisis oro","band":0,"avg6":0,"avg3":0,"up":0,"down":0,"slope":0,"is_acc":False,"is_exp":False,"high_4h":0,"low_4h":0,"sma30_slope":0}
    last6=candles_10[-6:] if len(candles_10)>=6 else candles_10; last3=candles_10[-3:]
    ranges6=[c["range"] for c in last6]; avg6=sum(ranges6)/len(ranges6) if ranges6 else 2
    avg3=sum([c["range"] for c in last3])/len(last3) if last3 else 2
    prices6=[c["close"] for c in last6]; band=max(prices6)-min(prices6) if prices6 else 2
    avg_body=sum([c["body"] for c in last6])/len(last6) if last6 else 1
    all_prices = [r[0] for r in rows] if rows else prices6
    current_price = all_prices[-1] if all_prices else prices6[-1]
    prices_4h = all_prices[-480:] if len(all_prices)>=480 else all_prices
    high_4h = max(prices_4h) if prices_4h else current_price+10; low_4h = min(prices_4h) if prices_4h else current_price-10
    sma10_p = sum(all_prices[-10:])/10 if len(all_prices)>=10 else current_price
    sma30_p = sum(all_prices[-30:])/30 if len(all_prices)>=30 else current_price
    sma60_p = sum(all_prices[-60:])/60 if len(all_prices)>=60 else sma30_p
    sma30_prev = sum(all_prices[-40:-10])/30 if len(all_prices)>=40 else sma30_p
    sma30_slope = sma30_p - sma30_prev
    recent_prices = all_prices[-61:-1] if len(all_prices)>=61 else all_prices[:-1]
    high_recent = max(recent_prices) if recent_prices else current_price+3; low_recent = min(recent_prices) if recent_prices else current_price-3
    is_acc=band<4.0 and avg6<2.0 and avg_body<1.2; up=down=0
    for c in reversed(candles_10):
        if c["bullish"]:
            if down==0: up+=1
            else: break
        else:
            if up==0: down+=1
            else: break
    closes5=[c["close"] for c in candles_10[-5:]]
    sma10=sum(closes5)/len(closes5) if closes5 else current_price
    sma10_prev=sum([c["close"] for c in candles_10[-6:-1]])/5 if len(candles_10)>=6 else sma10
    slope=sma10-sma10_prev; last=candles_10[-1]
    is_real_break_high = current_price > high_recent + 1.0 and last["bullish"] and last["strong"]
    is_real_break_low = current_price < low_recent - 1.0 and not last["bullish"] and last["strong"]
    
    if is_acc: return {"phase":"ACUMULACION","desc":"ACUMULACIÓN (Lateral)","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price < low_recent and sma30_slope < -0.3 and current_price < sma30_p: return {"phase":"EXPANSION_BAJISTA","desc":"EXPANSIÓN BAJISTA","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down if down>0 else 3,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price > high_recent and sma30_slope > 0.3 and current_price > sma30_p: return {"phase":"EXPANSION_ALCISTA","desc":"EXPANSIÓN ALCISTA","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 3,"down":0,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price < sma30_p and sma30_slope < -0.15: return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down if down>0 else 2,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price > sma30_p and sma30_slope > 0.15: return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 2,"down":0,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    return {"phase":"TRANSICION","desc":"TRANSICIÓN (Mercado en Duda)","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}

def analyze_gold_pro():
    try:
        rows=get_gold_history(600)
        price_fallback=get_gold_price()
        if len(rows)<20:
            return {"trend":"INICIO","direction":"COMPRA","confidence":55,"phase":"INICIO","phase_desc":"Iniciando","alert":"ESPERA - INICIANDO","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"smc_pats":[],"ag_bands":None,"high_10":price_fallback,"low_10":price_fallback,"high_15":price_fallback,"low_15":price_fallback,"high_30":price_fallback,"low_30":price_fallback,"sma10":price_fallback,"sma15":price_fallback,"sma30":price_fallback,"support":price_fallback,"resistance":price_fallback,"support_long":price_fallback,"resistance_long":price_fallback,"high_long":price_fallback,"low_long":price_fallback,"band_long":14,"volatility":3,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":price_fallback,"fib":None,"high_clusters":[],"low_clusters":[]}
        
        candles_10=build_candles(rows,20); candles_15=build_candles(rows,30); candles_30=build_candles(rows,60)
        live_price=rows[-1][0]
        prices = [r[0] for r in rows]
        
        closed_10, forming_10 = get_closed_candles(candles_10)
        closed_15, forming_15 = get_closed_candles(candles_15)
        
        if closed_15 and len(closed_15)>=1: analysis_price = closed_15[-1]["close"]
        elif closed_10 and len(closed_10)>=1: analysis_price = closed_10[-1]["close"]
        else: analysis_price = live_price
        
        current_price = analysis_price
        real_current_price = live_price
        
        sma10 = sum(prices[-10:])/10 if len(prices)>=10 else current_price
        sma15 = sum(prices[-15:])/15 if len(prices)>=15 else current_price
        sma30 = sum(prices[-30:])/30 if len(prices)>=30 else current_price
        
        ag_bands = calc_antigravity_bands(prices, period=20, dev=2.5)
        smc_pats = detect_smart_money(candles_15) + detect_smart_money(candles_10)

        recent_prices = prices[-31:-1] if len(prices)>=31 else prices[:-1]
        high_recent = max(recent_prices) if recent_prices else current_price+3
        low_recent = min(recent_prices) if recent_prices else current_price-3
        high_15 = max([c["high"] for c in candles_15[-2:]]) if len(candles_15)>=2 else high_recent+1.5
        low_15 = min([c["low"] for c in candles_15[-2:]]) if len(candles_15)>=2 else low_recent-1.5
        
        support=low_15; resistance=high_15
        phase_info=detect_phase(candles_10,candles_15,rows)
        candle_pats=detect_candle_patterns(candles_10)+detect_candle_patterns(candles_15)
        hour_ec=datetime.now(EC_TZ).hour
        ny_session=8<=hour_ec<=11
        buy_score=0; sell_score=0; points_detail=[]
        
        long_sr = None; fib = None; fib_detail = []
        
        try:
            long_sr = get_long_sr(rows, 4)
            if long_sr and long_sr.get("support",0)>1000:
                support = long_sr["support"]
                resistance = long_sr["resistance"]
        except: pass

        try:
            fib = calc_fibonacci_impulse(rows)
            if fib and fib.get("near"):
                if fib["dir"]=="ALCISTA":
                    buy_score+=3; fib_detail.append({"side":"COMPRA","points":3,"name":f"FIB {fib['near']} RETROCESO","reason":f"Soporte dorado Fibonacci"})
                elif fib["dir"]=="BAJISTA":
                    sell_score+=3; fib_detail.append({"side":"VENTA","points":3,"name":f"FIB {fib['near']} RETROCESO","reason":f"Rechazo bajista Fibonacci"})
        except: fib = None
        for f in fib_detail: points_detail.append(f)
        
        last_10 = candles_10[-1] if candles_10 else {"bullish":True,"strong":False,"body":1,"body_ratio":0.5,"range":2}
        
        if ag_bands:
            if current_price >= ag_bands["upper"]:
                sell_score += 5; points_detail.append({"side": "VENTA", "points": 5, "name": "AGOTAMIENTO TECHO", "reason": f"El precio rompió el techo matemático (+2.5 SD)."})
            elif current_price <= ag_bands["lower"]:
                buy_score += 5; points_detail.append({"side": "COMPRA", "points": 5, "name": "AGOTAMIENTO SUELO", "reason": f"El precio rompió el suelo matemático (-2.5 SD)."})

        for pat in smc_pats:
            if pat["dir"] == "COMPRA":
                buy_score += pat["strength"]; points_detail.append({"side": "COMPRA", "points": pat["strength"], "name": pat["name"], "reason": pat["desc"]})
            else:
                sell_score += pat["strength"]; points_detail.append({"side": "VENTA", "points": pat["strength"], "name": pat["name"], "reason": pat["desc"]})

        if current_price>sma10 and sma10>sma15 and sma15>sma30:
            buy_score+=2; points_detail.append({"side":"COMPRA","points":2,"name":"TENDENCIA MICRO ALCISTA","reason":f"El precio lidera las medias"})
        elif current_price<sma10 and sma10<sma15 and sma15<sma30:
            sell_score+=2; points_detail.append({"side":"VENTA","points":2,"name":"TENDENCIA MICRO BAJISTA","reason":f"El precio presiona las medias"})
        
        if abs(current_price-resistance) < 2.0:
            sell_score+=3; points_detail.append({"side":"VENTA","points":3,"name":"GOLPEA RESISTENCIA","reason":f"Zona de oferta fuerte"})
        if abs(current_price-support) < 2.0:
            buy_score+=3; points_detail.append({"side":"COMPRA","points":3,"name":"GOLPEA SOPORTE","reason":f"Zona de demanda fuerte"})
        
        for pat in candle_pats:
            if pat["dir"]=="COMPRA":
                buy_score+=pat["strength"]; points_detail.append({"side":"COMPRA","points":pat["strength"],"name":pat["name"],"reason":pat["desc"]})
            else:
                sell_score+=pat["strength"]; points_detail.append({"side":"VENTA","points":pat["strength"],"name":pat["name"],"reason":pat["desc"]})
                
        real_buy = sum(p['points'] for p in points_detail if p['side']=='COMPRA')
        real_sell = sum(p['points'] for p in points_detail if p['side']=='VENTA')
        
        # --- FILTRO ANTI-LAG ENDURECIDO (1.5 USD) ---
        live_diff = real_current_price - analysis_price
        
        if live_diff > 1.5: 
            points_detail = [p for p in points_detail if p["side"] != "VENTA"]
            points_detail.append({"side": "COMPRA", "points": 6, "name": "🚨 IMPULSO VIVO", "reason": f"El precio acaba de subir +${live_diff:.2f} rompiendo el análisis previo."})
            real_buy += 6; real_sell = 0
            
        elif live_diff < -1.5: 
            points_detail = [p for p in points_detail if p["side"] != "COMPRA"]
            points_detail.append({"side": "VENTA", "points": 6, "name": "🚨 CAÍDA VIVA", "reason": f"El precio acaba de caer -${abs(live_diff):.2f} rompiendo el análisis previo."})
            real_sell += 6; real_buy = 0
        # -------------------------------------------------------------
        
        buy_score = real_buy; sell_score = real_sell

        if buy_score==0 and sell_score>=4:
            direction="VENTA"; confidence=75 + min(sell_score*2, 20)
        elif sell_score==0 and buy_score>=4:
            direction="COMPRA"; confidence=75 + min(buy_score*2, 20)
        elif buy_score>=sell_score+3:
            direction="COMPRA"; confidence=65 + min(buy_score*2, 20)
        elif sell_score>=buy_score+3:
            direction="VENTA"; confidence=65 + min(sell_score*2, 20)
        else:
            direction="ESPERA"; confidence=50
            
        # Si el mercado está en acumulación lateral estrecha, forzamos espera a menos que la señal sea perfecta
        if "ACUMULACION" in phase_info["phase"] and phase_info["band"] < 6.0 and confidence < 80:
            alert="ESPERA - MERCADO LATERAL CONGELADO"; alert_type="WAIT"; alert_desc="El precio no se mueve. Peligro de trampas."
            confidence = 50; direction = "ESPERA"
        elif confidence>=75:
            alert=f"✅ ENTRA AHORA - {direction} CONFIRMADA"; alert_type="ENTER"; alert_desc=f"Condiciones óptimas. Score {buy_score} vs {sell_score}"
        else:
            alert="⏳ ESPERA - SEÑALES EN CONFLICTO"; alert_type="WAIT"; alert_desc=f"No hay una dirección clara (Score {buy_score}C / {sell_score}V)"
            direction = "ESPERA"
            
        trend="ALCISTA" if direction=="COMPRA" else "BAJISTA" if direction=="VENTA" else "LATERAL"
        
        return {
            "trend":trend,"direction":direction,"confidence":min(confidence,98),
            "pattern":phase_info["phase"],"phase":phase_info["phase"],"phase_desc":phase_info["desc"],
            "phase_info":phase_info,"alert":alert,"alert_type":alert_type,"alert_desc":alert_desc,
            "candle_patterns":candle_pats,"points_detail":points_detail,
            "ag_bands": ag_bands, "smc_pats": smc_pats, 
            "analysis_price":analysis_price,"live_price":real_current_price,
            "support":support,"resistance":resistance,
            "volatility":phase_info["avg3"],"buy_score":buy_score,"sell_score":sell_score,
            "hour_ec":hour_ec,"current_price":current_price
        }
    except Exception as e:
        print(f"analyze error {e}")
        return {"trend":"ERROR","direction":"ESPERA","confidence":50,"phase":"ERROR","alert":"ESPERA - ERROR","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"smc_pats":[],"ag_bands":None,"support":4052,"resistance":4073,"fib":None,"volatility":0,"buy_score":0,"sell_score":0}

def get_last_signal():
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT direction,confirmed_at,phase FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row: return {"direction":row[0],"confirmed_at":row[1],"phase":row[2]}
    except: pass
    return {"direction":"ESPERA","confirmed_at":datetime.now(EC_TZ).isoformat(),"phase":"INICIO"}

def update_last_signal(direction, phase):
    try:
        if direction == "ESPERA": return
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,phase) VALUES (?,?,?,?)", ("XAUUSD",direction,datetime.now(EC_TZ).isoformat(),phase))
        conn.commit(); conn.close()
    except: pass

def should_flip(new_dir, conf, market):
    try:
        last=get_last_signal()
        if new_dir == "ESPERA": return False, "El sistema pide esperar"
        if last["direction"]==new_dir: return True, f"Misma dirección {new_dir} - estable"
        
        buy_score=market.get("buy_score",0); sell_score=market.get("sell_score",0)
        
        # Filtro Anti-Lag para forzar el giro inmediato en scalping
        if (new_dir=="COMPRA" and buy_score >= 6 and sell_score == 0) or (new_dir=="VENTA" and sell_score >= 6 and buy_score == 0):
            return True, f"CAMBIO URGENTE: Impulso violento en contra detectado."
            
        if conf>=75: return True, f"Nueva señal validada con {conf}%"
        return False, f"Confianza {conf}% muy baja para invertir dirección."
    except Exception as e: return True, f"Error {e} - permite cambio"

def calc_tp_sl(price, direction, volatility=4.0):
    d = max(3.5, min(volatility * 1.2, 5.0))
    if direction == "COMPRA": return price - d, price + d, d
    elif direction == "VENTA": return price + d, price - d, d
    return 0, 0, 0

@app.get("/")
def root(): return {"message":"ORO SCALPER ALTA PRECISIÓN","version":"9.0"}

@app.get("/health")
def health(): return {"status":"ok","symbol":"XAUUSD","version":"9.0"}

@app.get("/signals/live")
def signals_live():
    try:
        price=get_gold_price(); save_gold_history(price)
        market=analyze_gold_pro()
        new_dir=market.get("direction","ESPERA"); conf=market.get("confidence",50)
        
        should, flip_reason=should_flip(new_dir, conf, market)
        if should:
            final_dir=new_dir; update_last_signal(final_dir, market.get("phase",""))
        else:
            last=get_last_signal()
            # Si estábamos en COMPRA o VENTA y el sistema pasa a ESPERA, generamos la alerta de salida
            if last["direction"] != "ESPERA" and new_dir == "ESPERA":
                final_dir = "ESPERA"
            else:
                final_dir=last["direction"]
            
        hour=datetime.now(EC_TZ).hour
        
        display_prob = conf
        live_for_entry = market.get("live_price", price)
        analysis_for_dir = market.get("analysis_price", price)
        
        vol = market.get("volatility", 4.0)
        sl, tp1, dist = calc_tp_sl(live_for_entry, final_dir, vol)
        
        market['direction'] = final_dir
        
        if final_dir == "ESPERA":
            market['alert'] = f"🔴 SALIR Y ESPERAR: SEÑALES NULAS"
            market['alert_type'] = "EXIT"
            market['alert_desc'] = f"El mercado perdió fuerza o se invirtió. Cierra tus posiciones."
        elif final_dir != new_dir and new_dir != "ESPERA":
            market['alert'] = f"🔴 PELIGRO: POSIBLE GIRO A {new_dir}"
            market['alert_type'] = "EXIT"
            market['alert_desc'] = f"Prepara tu salida, el mercado está intentando girarse."
        
        signal={
            "symbol":"XAUUSD","direction":final_dir,"entry":live_for_entry,"sl":sl,"tp1":tp1,"dist":dist,"analysis_price":analysis_for_dir,"live_price":live_for_entry,
            "confidence":conf,"market_analysis":market,"phase":market.get("phase",""),"phase_desc":market.get("phase_desc",""),
            "alert":market.get("alert",""),"alert_type":market.get("alert_type",""),"alert_desc":market.get("alert_desc",""),
            "points_detail":market.get("points_detail",[]),
            "flip_reason":flip_reason,"support":market.get("support",4052),"resistance":market.get("resistance",4073),"timestamp":datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        return [{"symbol":"XAUUSD","direction":"ESPERA","entry":get_gold_price(),"sl":0,"tp1":0,"dist":0,"confidence":50,"market_analysis":{"phase":"ERROR","alert":"ESPERA - ERROR","alert_type":"WAIT","points_detail":[]},"phase":"ERROR","alert":"ESPERA - ERROR","alert_type":"WAIT","points_detail":[],"flip_reason":str(e),"timestamp":datetime.now(EC_TZ).isoformat()}]

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        print("Monitor ORO SCALPER PRECISIÓN v9.0 iniciado")
        while True:
            try: save_gold_history(get_gold_price())
            except: pass
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())
