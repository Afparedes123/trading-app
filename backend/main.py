import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - SCALPER DINÁMICO SMC")
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
        pats.append({"name":"ENVOLVENTE ALCISTA","dir":"BUY","strength":3,"desc":"Envolvente alcista - compra fuerte"})
    if prev["bullish"] and not last["bullish"] and last["open"]>prev["close"] and last["close"]<prev["open"] and last["body"]>prev["body"]*1.2:
        pats.append({"name":"ENVOLVENTE BAJISTA","dir":"SELL","strength":3,"desc":"Envolvente bajista - venta fuerte"})
    if last["lower_wick"]>last["body"]*2 and last["upper_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"MARTILLO","dir":"BUY","strength":2,"desc":"Martillo alcista - rechazo bajos"})
    if last["upper_wick"]>last["body"]*2 and last["lower_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"ESTRELLA FUGAZ","dir":"SELL","strength":2,"desc":"Estrella fugaz - rechazo altos"})
    if last["bullish"] and last["body_ratio"]>0.8:
        pats.append({"name":"MARUBOZU ALCISTA","dir":"BUY","strength":2,"desc":"Marubozu alcista - fuerza compra"})
    if not last["bullish"] and last["body_ratio"]>0.8:
        pats.append({"name":"MARUBOZU BAJISTA","dir":"SELL","strength":2,"desc":"Marubozu bajista - fuerza venta"})
    return pats

# --- MOTOR ANTIGRAVITY & SMART MONEY ---
def calc_antigravity_bands(prices, period=20, dev=2.5):
    if len(prices) < period: return None
    recent = prices[-period:]
    mean = sum(recent) / period
    variance = sum((p - mean) ** 2 for p in recent) / period
    std_dev = math.sqrt(variance)
    return {
        "upper": mean + (dev * std_dev),
        "lower": mean - (dev * std_dev),
        "mean": mean,
        "std": std_dev
    }

def detect_smart_money(candles):
    if len(candles) < 3: return []
    smc_signals = []
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    
    if c1["high"] < c3["low"] and c2["bullish"] and c2["strong"]:
        smc_signals.append({"name": "FVG ALCISTA", "dir": "BUY", "strength": 3, "desc": f"Vacío liquidez (SMC) entre {c1['high']:.2f} y {c3['low']:.2f}"})
    if c1["low"] > c3["high"] and not c2["bullish"] and c2["strong"]:
        smc_signals.append({"name": "FVG BAJISTA", "dir": "SELL", "strength": 3, "desc": f"Vacío liquidez (SMC) entre {c3['high']:.2f} y {c1['low']:.2f}"})

    if c2["strong"] and c2["bullish"] and not c1["bullish"]:
        smc_signals.append({"name": "ORDER BLOCK ALCISTA", "dir": "BUY", "strength": 2, "desc": f"Bloque de órdenes en {c1['low']:.2f}"})
    if c2["strong"] and not c2["bullish"] and c1["bullish"]:
        smc_signals.append({"name": "ORDER BLOCK BAJISTA", "dir": "SELL", "strength": 2, "desc": f"Bloque de órdenes en {c1['high']:.2f}"})

    return smc_signals
# ----------------------------------------------------

def get_long_sr(rows, lookback_hours=4):
    try:
        lookback = lookback_hours * 120
        prices = [r[0] for r in rows[-lookback:]] if len(rows)>=lookback else [r[0] for r in rows]
        if len(prices)<60: return None
        pivot_highs, pivot_lows = [], []
        for i in range(5, len(prices)-5):
            is_high, is_low = True, True
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
            result = [(sum(c)/len(c), len(c)) for c in clusters]
            result.sort(key=lambda x: x[1], reverse=True)
            return result
        high_clusters = cluster_levels(pivot_highs, 1.5)
        low_clusters = cluster_levels(pivot_lows, 1.5)
        recent_high = max(prices)
        recent_low = min(prices)
        band_long = recent_high - recent_low
        current = prices[-1]
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
        recent_low = min(prices[-100:])
        recent_high = max(prices[-100:])
        low_idx = len(prices) - 1 - prices[::-1].index(recent_low) if recent_low in prices else 0
        high_idx = len(prices) - 1 - prices[::-1].index(recent_high) if recent_high in prices else 0
        if high_idx > low_idx and (recent_high - recent_low) > 8.0:
            impulse_dir, impulse_low, impulse_high, impulse_range = "ALCISTA", recent_low, recent_high, recent_high - recent_low
        elif low_idx > high_idx and (recent_high - recent_low) > 8.0:
            impulse_dir, impulse_low, impulse_high, impulse_range = "BAJISTA", recent_low, recent_high, recent_high - recent_low
        else: return None
        current = prices[-1]
        fib_levels = {
            "0": impulse_high if impulse_dir=="ALCISTA" else impulse_low,
            "0.236": impulse_high - impulse_range*0.236 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.236,
            "0.382": impulse_high - impulse_range*0.382 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.382,
            "0.5": impulse_high - impulse_range*0.5 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.5,
            "0.618": impulse_high - impulse_range*0.618 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.618,
            "0.786": impulse_high - impulse_range*0.786 if impulse_dir=="ALCISTA" else impulse_low + impulse_range*0.786,
            "1": impulse_low if impulse_dir=="ALCISTA" else impulse_high,
        }
        near_fib = None; min_dist = 999
        for level, price_fib in fib_levels.items():
            dist = abs(current - price_fib)
            if dist < min_dist and dist < 1.8: min_dist, near_fib = dist, level
        return {
            "dir": impulse_dir, "low": impulse_low, "high": impulse_high, "range": impulse_range,
            "current": current, "levels": fib_levels, "near": near_fib, "dist": min_dist if near_fib else None,
            "desc": f"Impulso {impulse_dir} {impulse_low:.2f} -> {impulse_high:.2f} ({impulse_range:.1f} USD)"
        }
    except: return None

def detect_phase(candles_10, candles_15, rows):
    if len(candles_10)<4:
        return {"phase":"INICIO","desc":"Iniciando análisis oro","band":0,"avg6":0,"avg3":0,"up":0,"down":0,"slope":0,"is_acc":False,"is_exp":False,"high_4h":0,"low_4h":0,"sma30_slope":0}
    last6=candles_10[-6:] if len(candles_10)>=6 else candles_10
    last3=candles_10[-3:]
    ranges6=[c["range"] for c in last6]; avg6=sum(ranges6)/len(ranges6) if ranges6 else 2
    avg3=sum([c["range"] for c in last3])/len(last3) if last3 else 2
    prices6=[c["close"] for c in last6]; band=max(prices6)-min(prices6) if prices6 else 2
    avg_body=sum([c["body"] for c in last6])/len(last6) if last6 else 1
    all_prices = [r[0] for r in rows] if rows else prices6
    current_price = all_prices[-1] if all_prices else prices6[-1]
    prices_4h = all_prices[-480:] if len(all_prices)>=480 else all_prices
    high_4h = max(prices_4h) if prices_4h else current_price+10
    low_4h = min(prices_4h) if prices_4h else current_price-10
    sma10_p = sum(all_prices[-10:])/10 if len(all_prices)>=10 else current_price
    sma30_p = sum(all_prices[-30:])/30 if len(all_prices)>=30 else current_price
    sma60_p = sum(all_prices[-60:])/60 if len(all_prices)>=60 else sma30_p
    sma30_prev = sum(all_prices[-40:-10])/30 if len(all_prices)>=40 else sma30_p
    sma30_slope = sma30_p - sma30_prev
    recent_prices = all_prices[-61:-1] if len(all_prices)>=61 else all_prices[:-1]
    high_recent = max(recent_prices) if recent_prices else current_price+3
    low_recent = min(recent_prices) if recent_prices else current_price-3
    is_acc=band<4.0 and avg6<2.0 and avg_body<1.2
    up=down=0
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
    slope=sma10-sma10_prev
    last=candles_10[-1]
    is_real_break_high = current_price > high_recent + 1.0 and last["bullish"] and last["strong"]
    is_real_break_low = current_price < low_recent - 1.0 and not last["bullish"] and last["strong"]
    if current_price < low_recent and sma30_slope < -0.3 and current_price < sma30_p:
        return {"phase":"EXPANSION_BAJISTA","desc":f"EXPANSIÓN BAJISTA - RUPTURA ABAJO","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down if down>0 else 3,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price > high_recent and sma30_slope > 0.3 and current_price > sma30_p:
        return {"phase":"EXPANSION_ALCISTA","desc":f"EXPANSIÓN ALCISTA - RUPTURA ARRIBA","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 3,"down":0,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price < sma30_p and sma30_p < sma60_p and sma30_slope < -0.15:
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - SMA30 pendiente {sma30_slope:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down if down>0 else 2,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if current_price > sma30_p and sma30_p > sma60_p and sma30_slope > 0.15:
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - SMA30 pendiente {sma30_slope:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 2,"down":0,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if is_real_break_high:
        return {"phase":"EXPANSION_ALCISTA","desc":f"EXPANSIÓN ALCISTA - PICO COMPRA","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 3,"down":0,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if is_real_break_low:
        return {"phase":"EXPANSION_BAJISTA","desc":f"EXPANSIÓN BAJISTA - PICO VENTA","band":band,"avg6":avg6,"avg3":avg3,"up":0,"down":down if down>0 else 3,"slope":slope,"is_acc":False,"is_exp":True,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    if is_acc:
        return {"phase":"ACUMULACION","desc":f"ACUMULACIÓN - rango {band:.1f} USD estrecho","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}
    return {"phase":"TRANSICION","desc":f"TRANSICIÓN - SMA30 plano {sma30_slope:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":sma30_slope,"is_acc":False,"is_exp":False,"high_4h":high_4h,"low_4h":low_4h,"sma30_slope":sma30_slope}

def analyze_gold_pro():
    try:
        rows=get_gold_history(600)
        price_fallback=get_gold_price()
        if len(rows)<20:
            return {"trend":"INICIO","direction":"BUY","confidence":55,"phase":"INICIO","phase_desc":"Iniciando","alert":"ESPERA - INICIANDO","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"smc_pats":[],"ag_bands":None,"high_10":price_fallback,"low_10":price_fallback,"high_15":price_fallback,"low_15":price_fallback,"high_30":price_fallback,"low_30":price_fallback,"sma10":price_fallback,"sma15":price_fallback,"sma30":price_fallback,"support":price_fallback,"resistance":price_fallback,"support_long":price_fallback,"resistance_long":price_fallback,"high_long":price_fallback,"low_long":price_fallback,"band_long":14,"volatility":3,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":price_fallback,"fib":None,"high_clusters":[],"low_clusters":[]}
        
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
        high_10 = max([c["high"] for c in candles_10[-3:]]) if len(candles_10)>=3 else high_recent
        low_10 = min([c["low"] for c in candles_10[-3:]]) if len(candles_10)>=3 else low_recent
        high_15 = max([c["high"] for c in candles_15[-2:]]) if len(candles_15)>=2 else high_recent+1.5
        low_15 = min([c["low"] for c in candles_15[-2:]]) if len(candles_15)>=2 else low_recent-1.5
        high_30 = max([c["high"] for c in candles_30[-2:]]) if len(candles_30)>=2 else high_15+1
        low_30 = min([c["low"] for c in candles_30[-2:]]) if len(candles_30)>=2 else low_15-1
        support=low_15; resistance=high_15
        phase_info=detect_phase(candles_10,candles_15,rows)
        candle_pats=detect_candle_patterns(candles_10)+detect_candle_patterns(candles_15)
        hour_ec=datetime.now(EC_TZ).hour
        ny_session=8<=hour_ec<=11
        buy_score=0; sell_score=0; points_detail=[]
        
        support_long = low_15; resistance_long = high_15
        support_far = low_15; resistance_far = high_15
        long_sr = None; fib = None; fib_detail = []
        
        try:
            long_sr = get_long_sr(rows, 4)
            if long_sr and long_sr.get("support",0)>1000:
                support_long = long_sr["support"]
                resistance_long = long_sr["resistance"]
                support_far = long_sr.get("support_far", support_long)
                resistance_far = long_sr.get("resistance_far", resistance_long)
        except: pass

        try:
            fib = calc_fibonacci_impulse(rows)
            if fib and fib.get("near") in ["0.618","0.5","0.382"]:
                if fib["dir"]=="ALCISTA" and fib["near"] in ["0.618","0.5"]:
                    buy_score+=2
                    fib_detail.append({"side":"BUY","points":2,"name":f"FIB {fib['near']} RETROCESO ALCISTA","reason":f"Impulso alcista - zona compra"})
                elif fib["dir"]=="BAJISTA" and fib["near"] in ["0.618","0.5"]:
                    sell_score+=2
                    fib_detail.append({"side":"SELL","points":2,"name":f"FIB {fib['near']} RETROCESO BAJISTA","reason":f"Impulso bajista - zona venta"})
        except: fib = None
        for f in fib_detail: points_detail.append(f)

        if support_long and support_long>1000: support = support_long
        if resistance_long and resistance_long>1000: resistance = resistance_long
        
        is_break_high = current_price > high_recent + 1.0
        is_break_low = current_price < low_recent - 1.0
        last_10 = candles_10[-1] if candles_10 else {"bullish":True,"strong":False,"body":1,"body_ratio":0.5,"range":2}
        
        # --- PUNTUACIÓN ANTIGRAVITY ---
        if ag_bands:
            if current_price >= ag_bands["upper"]:
                sell_score += 4
                points_detail.append({"side": "SELL", "points": 4, "name": "ANTIGRAVITY SELL", "reason": f"Precio rompió banda superior (+2.5 SD)."})
            elif current_price <= ag_bands["lower"]:
                buy_score += 4
                points_detail.append({"side": "BUY", "points": 4, "name": "ANTIGRAVITY BUY", "reason": f"Precio rompió banda inferior (-2.5 SD)."})

        # --- PUNTUACIÓN SMART MONEY (FVG/OB) ---
        for pat in smc_pats:
            if pat["dir"] == "BUY":
                buy_score += pat["strength"]
                points_detail.append({"side": "BUY", "points": pat["strength"], "name": pat["name"], "reason": pat["desc"]})
            else:
                sell_score += pat["strength"]
                points_detail.append({"side": "SELL", "points": pat["strength"], "name": pat["name"], "reason": pat["desc"]})

        # --- SMA Retail Score ---
        if current_price>sma10 and sma10>sma15 and sma15>sma30:
            buy_score+=3; points_detail.append({"side":"BUY","points":3,"name":"SMA ALCISTA FUERTE","reason":f"Precio > SMA10 > SMA15 > SMA30"})
        elif current_price<sma10 and sma10<sma15 and sma15<sma30:
            sell_score+=3; points_detail.append({"side":"SELL","points":3,"name":"SMA BAJISTA FUERTE","reason":f"Precio < SMA10 < SMA15 < SMA30"})
        
        if is_break_high and last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            buy_score+=pts; points_detail.append({"side":"BUY","points":pts,"name":"RUPTURA ALTA","reason":f"Ruptura alto real"})
        if is_break_low and not last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            sell_score+=pts; points_detail.append({"side":"SELL","points":pts,"name":"RUPTURA BAJA","reason":f"Ruptura bajo real"})
        
        if abs(current_price-high_15) < 2.5:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"CERCA RESISTENCIA 15m","reason":f"Cerca resistencia"})
        if abs(current_price-low_15) < 2.5:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"CERCA SOPORTE 15m","reason":f"Cerca soporte"})
        
        up_streak=phase_info["up"]; down_streak=phase_info["down"]
        if up_streak>=3: buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":f"RACHA VELAS ALCISTAS","reason":f"Racha alcista"})
        if down_streak>=3: sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":f"RACHA VELAS BAJISTAS","reason":f"Racha bajista"})
        
        if last_10["strong"]:
            if last_10["bullish"]: buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"VELA FUERTE ALCISTA","reason":f"Vela alcista fuerte"})
            else: sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"VELA FUERTE BAJISTA","reason":f"Vela bajista fuerte"})
        
        if ny_session:
            if last_10["bullish"]: buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SESIÓN NY","reason":"NY OPEN compra"})
            else: sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SESIÓN NY","reason":"NY OPEN venta"})
            
        for pat in candle_pats:
            if pat["dir"]=="BUY":
                buy_score+=pat["strength"]
                points_detail.append({"side":"BUY","points":pat["strength"],"name":pat["name"],"reason":pat["desc"]})
            else:
                sell_score+=pat["strength"]
                points_detail.append({"side":"SELL","points":pat["strength"],"name":pat["name"],"reason":pat["desc"]})
                
        if "EXPANSION_ALCISTA" in phase_info["phase"]:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"FASE EXPANSIÓN ALCISTA","reason":phase_info["desc"]})
        elif "EXPANSION_BAJISTA" in phase_info["phase"]:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"FASE EXPANSIÓN BAJISTA","reason":phase_info["desc"]})
            
        sma30_slope_val = phase_info.get("sma30_slope",0)
        if sma30_slope_val < -0.2:
            for p in points_detail:
                if p["side"]=="BUY" and p["points"]<=1 and "DÉBIL" in p["name"]: p["points"]=0
            points_detail = [p for p in points_detail if p["points"]>0]
            
        real_buy = sum(p['points'] for p in points_detail if p['side']=='BUY')
        real_sell = sum(p['points'] for p in points_detail if p['side']=='SELL')
        buy_score = real_buy; sell_score = real_sell
        
        if "BAJISTA" in phase_info["phase"] and sma30_slope_val < -0.2:
            sell_score += 1; points_detail.append({"side":"SELL","points":1,"name":"TENDENCIA MAYOR BAJISTA","reason":f"SMA30 cayendo"})
        if "ALCISTA" in phase_info["phase"] and sma30_slope_val > 0.2:
            buy_score += 1; points_detail.append({"side":"BUY","points":1,"name":"TENDENCIA MAYOR ALCISTA","reason":f"SMA30 subiendo"})
            
        if buy_score==0 and sell_score>=2:
            direction="SELL"; base_conf=68
            if "EXPANSION" in phase_info["phase"] or "BAJISTA" in phase_info["phase"]: base_conf=76
            confidence=base_conf+min(sell_score*2,12)
        elif sell_score==0 and buy_score>=2:
            direction="BUY"; base_conf=68
            if "EXPANSION" in phase_info["phase"] or "ALCISTA" in phase_info["phase"]: base_conf=76
            confidence=base_conf+min(buy_score*2,12)
        elif buy_score>=sell_score+2:
            direction="BUY"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            confidence=base_conf+min(buy_score*2,16)
        elif sell_score>=buy_score+2:
            direction="SELL"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            confidence=base_conf+min(sell_score*2,16)
        else:
            sma30_s = phase_info.get("sma30_slope",0)
            if sma30_s < -0.2: direction="SELL"; confidence=58
            elif sma30_s > 0.2: direction="BUY"; confidence=58
            else: direction="BUY" if current_price>sma15 else "SELL"; confidence=56
            
        long_is_acc = long_sr["is_acc_long"] if long_sr else False
        long_band = long_sr["band_long"] if long_sr else phase_info["band"]
        support_real = long_sr["support"] if long_sr and long_sr.get("support",0)>1000 else support
        resistance_real = long_sr["resistance"] if long_sr and long_sr.get("resistance",0)>1000 else resistance
        
        if long_is_acc and long_band < 7.0:
            alert="ESPERA - ACUMULACIÓN ESTRECHA - NO OPERAR"; alert_type="WAIT"; alert_desc="Acumulación estrecha - esperar ruptura"
            confidence = 52
        elif long_is_acc and long_band >= 10.0:
            if abs(current_price - support_real) < 1.8:
                buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"CORTE SOPORTE EN ACUMULACIÓN","reason":f"Cerca soporte"})
                if confidence < 70: confidence = 70
            if abs(current_price - resistance_real) < 1.8:
                sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"CORTE RESISTENCIA EN ACUMULACIÓN","reason":f"Cerca resistencia"})
                if confidence < 70: confidence = 70
            if "ACUMULACION" in phase_info["phase"]:
                phase_info["phase"]="RANGO AMPLIO"
                phase_info["desc"]=f"RANGO AMPLIO {long_band:.1f} USD"
                
        if "ACUMULACION" in phase_info["phase"] and long_band>=10: pass
        elif "ACUMULACION" in phase_info["phase"] and not "EXPANSION" in phase_info["phase"] and long_band<7:
            alert="ESPERA - NO ENTRES - FASE ACUMULACIÓN"; alert_type="WAIT"; alert_desc="Esperar pico"
        elif "EXPANSION" in phase_info["phase"] and confidence>=70:
            alert=f"ENTRA - PICO TRAS ACUMULACIÓN - {direction}"; alert_type="ENTER"; alert_desc=f"{phase_info['phase']} - conf {confidence}%"
        elif fib and fib.get('near') in ['0.618','0.5'] and confidence>=65:
            alert=f"ENTRA - {direction} EN FIB {fib['near']}"; alert_type="ENTER"; alert_desc=f"Fibonacci {fib['near']} - Score {buy_score}B/{sell_score}S"
        elif confidence>=72 and abs(buy_score-sell_score)>=2:
            alert=f"ENTRA - {direction} CONFIRMADO"; alert_type="ENTER"; alert_desc=f"Score {buy_score} vs {sell_score}"
        elif confidence>=62 and abs(buy_score-sell_score)>=1:
            alert=f"ENTRA CON PRECAUCIÓN - {direction}"; alert_type="CAUTION"; alert_desc=f"Espera confirmación de volumen"
        else:
            alert="ESPERA - SEÑAL DÉBIL - RANGO"; alert_type="WAIT"; alert_desc=f"Score {buy_score}B/{sell_score}S"
            
        trend="ALCISTA" if direction=="BUY" else "BAJISTA"
        if abs(buy_score-sell_score)<=1: trend="LATERAL"
        
        return {
            "trend":trend,"direction":direction,"confidence":min(confidence,95),
            "pattern":phase_info["phase"],"phase":phase_info["phase"],"phase_desc":phase_info["desc"],
            "phase_info":phase_info,"alert":alert,"alert_type":alert_type,"alert_desc":alert_desc,
            "candle_patterns":candle_pats,"points_detail":points_detail,
            "ag_bands": ag_bands, "smc_pats": smc_pats, 
            "analysis_price":analysis_price,"live_price":real_current_price,
            "reason":" | ".join([p["name"] for p in points_detail[:3]]),
            "high_10":high_10,"low_10":low_10,"high_15":high_15,"low_15":low_15,"high_30":high_30,"low_30":low_30,
            "high_long":long_sr["high_long"] if long_sr else high_15,
            "low_long":long_sr["low_long"] if long_sr else low_15,
            "band_long":long_band,"fib":fib,
            "support_long":support_long if support_long>1000 else low_15,
            "resistance_long":resistance_long if resistance_long>1000 else high_15,
            "support_far":support_far,"resistance_far":resistance_far,
            "high_clusters":long_sr.get("high_clusters",[]) if long_sr else [],
            "low_clusters":long_sr.get("low_clusters",[]) if long_sr else [],
            "sma10":sma10,"sma15":sma15,"sma30":sma30,"support":support,"resistance":resistance,
            "up_streak":up_streak,"down_streak":down_streak,"volatility":phase_info["avg3"],"volatility_15":phase_info["avg6"],
            "ny_session":ny_session,"buy_score":buy_score,"sell_score":sell_score,
            "hour_ec":hour_ec,"current_price":current_price
        }
    except Exception as e:
        print(f"analyze error {e}")
        return {"trend":"ERROR","direction":"BUY","confidence":50,"phase":"ERROR","alert":"ESPERA - ERROR","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"smc_pats":[],"ag_bands":None,"high_10":0,"low_10":0,"high_15":0,"low_15":0,"sma10":0,"sma15":0,"sma30":0,"support":4052,"resistance":4073,"band_long":21,"fib":None,"volatility":0,"buy_score":0,"sell_score":0}

def get_last_signal():
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT direction,confirmed_at,phase FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row: return {"direction":row[0],"confirmed_at":row[1],"phase":row[2]}
    except: pass
    return {"direction":"BUY","confirmed_at":datetime.now(EC_TZ).isoformat(),"phase":"INICIO"}

def update_last_signal(direction, phase):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,phase) VALUES (?,?,?,?)", ("XAUUSD",direction,datetime.now(EC_TZ).isoformat(),phase))
        conn.commit(); conn.close()
    except: pass

def should_flip(new_dir, conf, market):
    try:
        last=get_last_signal()
        if last["direction"]==new_dir: return True, f"Misma dirección {new_dir} - estable"
        buy_score=market.get("buy_score",0); sell_score=market.get("sell_score",0); diff=abs(buy_score-sell_score)
        sma30_slope = market.get("phase_info",{}).get("sma30_slope",0) if market.get("phase_info") else market.get("sma30_slope",0)
        phase = market.get("phase","")
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        mins_passed = 999
        if row and row[0]:
            try:
                last_time=datetime.fromisoformat(row[0])
                mins_passed=(datetime.now(EC_TZ)-last_time).total_
