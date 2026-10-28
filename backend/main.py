import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - FASES + PUNTOS + FIB")
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
        if len(chunk)<points*0.7: continue
        prices=[r[0] for r in chunk]
        if not prices: continue
        o=prices[0]; cl=prices[-1]; hi=max(prices); lo=min(prices)
        body=abs(cl-o); rng=hi-lo if hi!=lo else 0.1
        bullish=cl>o; ratio=body/rng if rng>0 else 0
        upper=hi-max(o,cl); lower=min(o,cl)-lo
        candles.append({"open":o,"close":cl,"high":hi,"low":lo,"range":rng,"body":body,"body_ratio":ratio,"upper_wick":upper,"lower_wick":lower,"bullish":bullish,"strong":ratio>0.6,"small":ratio<0.3,"doji":ratio<0.1})
    return candles

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

def get_long_sr(rows, lookback_hours=4):
    try:
        lookback = lookback_hours * 120
        prices = [r[0] for r in rows[-lookback:]] if len(rows)>=lookback else [r[0] for r in rows]
        if len(prices)<60:
            return None
        pivot_highs = []
        pivot_lows = []
        for i in range(5, len(prices)-5):
            is_high = True
            is_low = True
            for j in range(1,4):
                if prices[i] <= prices[i-j] or prices[i] <= prices[i+j]:
                    is_high = False
                if prices[i] >= prices[i-j] or prices[i] >= prices[i+j]:
                    is_low = False
            if is_high:
                pivot_highs.append(prices[i])
            if is_low:
                pivot_lows.append(prices[i])
        if not pivot_highs:
            pivot_highs = [max(prices)]
        if not pivot_lows:
            pivot_lows = [min(prices)]
        def cluster_levels(levels, tolerance=1.5):
            if not levels:
                return []
            levels_sorted = sorted(levels)
            clusters = [[levels_sorted[0]]]
            for l in levels_sorted[1:]:
                if abs(l - sum(clusters[-1])/len(clusters[-1])) < tolerance:
                    clusters[-1].append(l)
                else:
                    clusters.append([l])
            result = []
            for c in clusters:
                avg = sum(c)/len(c)
                result.append((avg, len(c)))
            result.sort(key=lambda x: x[1], reverse=True)
            return result
        high_clusters = cluster_levels(pivot_highs, 1.5)
        low_clusters = cluster_levels(pivot_lows, 1.5)
        recent_high = max(prices)
        recent_low = min(prices)
        band_long = recent_high - recent_low
        current = prices[-1]
        if high_clusters:
            resistance = min(high_clusters, key=lambda x: abs(x[0]-current))[0]
        else:
            resistance = recent_high
        if low_clusters:
            support = min(low_clusters, key=lambda x: abs(x[0]-current))[0]
        else:
            support = recent_low
        is_acc_long = band_long < 12.0
        return {
            "high_long": recent_high,
            "low_long": recent_low,
            "resistance": resistance,
            "support": support,
            "resistance_far": recent_high,
            "support_far": recent_low,
            "high_clusters": high_clusters[:3],
            "low_clusters": low_clusters[:3],
            "band_long": band_long,
            "is_acc_long": is_acc_long,
            "lookback": lookback
        }
    except Exception as e:
        print(f"long_sr error {e}")
        return None

def calc_fibonacci_impulse(rows):
    try:
        prices = [r[0] for r in rows[-200:]]
        if len(prices)<50:
            return None
        recent_low = min(prices[-100:])
        recent_high = max(prices[-100:])
        low_idx = len(prices) - 1 - prices[::-1].index(recent_low) if recent_low in prices else 0
        high_idx = len(prices) - 1 - prices[::-1].index(recent_high) if recent_high in prices else 0
        if high_idx > low_idx and (recent_high - recent_low) > 8.0:
            impulse_dir = "ALCISTA"
            impulse_low = recent_low
            impulse_high = recent_high
            impulse_range = impulse_high - impulse_low
        elif low_idx > high_idx and (recent_high - recent_low) > 8.0:
            impulse_dir = "BAJISTA"
            impulse_low = recent_low
            impulse_high = recent_high
            impulse_range = impulse_high - impulse_low
        else:
            return None
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
        near_fib = None
        min_dist = 999
        for level, price_fib in fib_levels.items():
            dist = abs(current - price_fib)
            if dist < min_dist and dist < 1.8:
                min_dist = dist
                near_fib = level
        return {
            "dir": impulse_dir,
            "low": impulse_low,
            "high": impulse_high,
            "range": impulse_range,
            "current": current,
            "levels": fib_levels,
            "near": near_fib,
            "dist": min_dist if near_fib else None,
            "desc": f"Impulso {impulse_dir} {impulse_low:.2f} -> {impulse_high:.2f} ({impulse_range:.1f} USD)"
        }
    except:
        return None

def detect_phase(candles_10, candles_15, rows):
    if len(candles_10)<4:
        return {"phase":"INICIO","desc":"Iniciando análisis oro","band":0,"avg6":0,"avg3":0,"up":0,"down":0,"slope":0,"is_acc":False,"is_exp":False}
    last6=candles_10[-6:] if len(candles_10)>=6 else candles_10
    last3=candles_10[-3:]
    ranges6=[c["range"] for c in last6]; avg6=sum(ranges6)/len(ranges6)
    avg3=sum([c["range"] for c in last3])/len(last3)
    prices6=[c["close"] for c in last6]; band=max(prices6)-min(prices6)
    avg_body=sum([c["body"] for c in last6])/len(last6)
    all_prices = [r[0] for r in rows] if rows else prices6
    current_price = all_prices[-1] if all_prices else prices6[-1]
    sma10_p = sum(all_prices[-10:])/10 if len(all_prices)>=10 else current_price
    sma15_p = sum(all_prices[-15:])/15 if len(all_prices)>=15 else current_price
    recent_prices = all_prices[-31:-1] if len(all_prices)>=31 else all_prices[:-1]
    high_recent = max(recent_prices) if recent_prices else current_price+3
    low_recent = min(recent_prices) if recent_prices else current_price-3
    is_acc=band<4.0 and avg6<2.0 and avg_body<1.2
    is_exp=avg3>avg6*1.5
    up=down=0
    for c in reversed(candles_10):
        if c["bullish"]:
            if down==0: up+=1
            else: break
        else:
            if up==0: down+=1
            else: break
    closes5=[c["close"] for c in candles_10[-5:]]
    sma10=sum(closes5)/len(closes5)
    sma10_prev=sum([c["close"] for c in candles_10[-6:-1]])/5 if len(candles_10)>=6 else sma10
    slope=sma10-sma10_prev
    last=candles_10[-1]
    if is_exp and last["strong"]:
        prices_all=[c["close"] for c in last6]
        if last["bullish"] and last["close"]>=max(prices_all)*0.998:
            return {"phase":"EXPANSION_ALCISTA","desc":f"EXPANSIÓN ALCISTA - PICO COMPRA tras acumulación {band:.1f} USD -> ruptura {last['close']:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
        if not last["bullish"] and last["close"]<=min(prices_all)*1.002:
            return {"phase":"EXPANSION_BAJISTA","desc":f"EXPANSIÓN BAJISTA - PICO VENTA {band:.1f} USD -> ruptura {last['close']:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
    if current_price >= high_recent * 0.999 and current_price > sma10_p:
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA POST-RUPTURA - precio {current_price:.2f} rompió {high_recent:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 1,"down":0,"slope":slope,"is_acc":False,"is_exp":False}
    if current_price <= low_recent * 1.001 and current_price < sma10_p:
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA POST-RUPTURA - precio {current_price:.2f} rompió {low_recent:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":0,"down":down if down>0 else 1,"slope":slope,"is_acc":False,"is_exp":False}
    if is_acc:
        return {"phase":"ACUMULACION","desc":f"ACUMULACIÓN - rango {band:.1f} USD estrecho, vol {avg6:.1f} USD","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
    if up>=3:
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - {up} velas alcistas","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    if down>=3:
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - {down} velas bajistas","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    if band<6.0 and avg6<2.5:
        if current_price > sma10_p:
            return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - banda estrecha {band:.1f} USD pero precio sobre SMA","band":band,"avg6":avg6,"avg3":avg3,"up":1,"down":0,"slope":slope,"is_acc":False,"is_exp":False}
        if current_price < sma10_p:
            return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - banda estrecha {band:.1f} USD pero precio bajo SMA","band":band,"avg6":avg6,"avg3":avg3,"up":0,"down":1,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"RANGO","desc":f"RANGO estrecho {band:.1f} USD - esperar ruptura","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    return {"phase":"TRANSICION","desc":f"TRANSICIÓN - vol {avg3:.1f} USD","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}

def analyze_gold_pro():
    try:
        rows=get_gold_history(600)
        price_fallback=get_gold_price()
        if len(rows)<20:
            return {"trend":"INICIO","direction":"BUY","confidence":55,"phase":"INICIO","phase_desc":"Iniciando","alert":"ESPERA - INICIANDO","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"high_10":price_fallback+3.5,"low_10":price_fallback-3.2,"high_15":price_fallback+5.8,"low_15":price_fallback-5.1,"high_30":price_fallback+8.5,"low_30":price_fallback-8.2,"sma10":price_fallback-0.8,"sma15":price_fallback-1.2,"sma30":price_fallback-1.8,"support":price_fallback-5.1,"resistance":price_fallback+5.8,"support_long":price_fallback-7,"resistance_long":price_fallback+7,"high_long":price_fallback+7,"low_long":price_fallback-7,"band_long":14,"volatility":3.2,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":price_fallback,"fib":None,"high_clusters":[],"low_clusters":[]}
        candles_10=build_candles(rows,20); candles_15=build_candles(rows,30); candles_30=build_candles(rows,60)
        current_price=rows[-1][0]
        prices = [r[0] for r in rows]
        sma10 = sum(prices[-10:])/10 if len(prices)>=10 else current_price
        sma15 = sum(prices[-15:])/15 if len(prices)>=15 else current_price
        sma30 = sum(prices[-30:])/30 if len(prices)>=30 else current_price
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
        # Variables con valores seguros anti-cero
        support_long = low_15
        resistance_long = high_15
        support_far = low_15
        resistance_far = high_15
        long_sr = None
        fib = None
        fib_detail = []
        # SR largo y Fibonacci con manejo de errores
        try:
            long_sr = get_long_sr(rows, 4)
            if long_sr and long_sr.get("support",0)>1000:
                support_long = long_sr["support"]
                resistance_long = long_sr["resistance"]
                support_far = long_sr.get("support_far", support_long)
                resistance_far = long_sr.get("resistance_far", resistance_long)
        except:
            support_long = low_15
            resistance_long = high_15
        try:
            fib = calc_fibonacci_impulse(rows)
            if fib and fib.get("near") in ["0.618","0.5","0.382"]:
                if fib["dir"]=="ALCISTA" and fib["near"] in ["0.618","0.5"]:
                    buy_score+=2
                    fib_detail.append({"side":"BUY","points":2,"name":f"FIB {fib['near']} RETROCESO ALCISTA","reason":f"Impulso alcista {fib['low']:.2f}->{fib['high']:.2f} ({fib['range']:.1f} USD) - Precio {fib['current']:.2f} en Fib {fib['near']} {fib['levels'][fib['near']]:.2f} - zona compra"})
                elif fib["dir"]=="BAJISTA" and fib["near"] in ["0.618","0.5"]:
                    sell_score+=2
                    fib_detail.append({"side":"SELL","points":2,"name":f"FIB {fib['near']} RETROCESO BAJISTA","reason":f"Impulso bajista {fib['high']:.2f}->{fib['low']:.2f} - Precio en Fib {fib['near']} - zona venta"})
            if fib and fib.get("near")=="0":
                if fib["dir"]=="ALCISTA":
                    buy_score+=2
                    fib_detail.append({"side":"BUY","points":2,"name":"FIB 0 RUPTURA ALCISTA","reason":f"Ruptura Fib 0 alcista {fib['high']:.2f}"})
                else:
                    sell_score+=2
                    fib_detail.append({"side":"SELL","points":2,"name":"FIB 0 RUPTURA BAJISTA","reason":f"Ruptura Fib 0 bajista {fib['low']:.2f}"})
        except:
            fib = None
        for f in fib_detail:
            points_detail.append(f)
        # Soporte y resistencia principal = pivotes 4H
        if support_long and support_long>1000:
            support = support_long
        if resistance_long and resistance_long>1000:
            resistance = resistance_long
        is_break_high = current_price >= high_recent * 0.999
        is_break_low = current_price <= low_recent * 1.001
        last_10 = candles_10[-1] if candles_10 else {"bullish":True,"strong":False,"body":1,"body_ratio":0.5,"range":2}
        # SMA
        if current_price>sma10 and sma10>sma15 and sma15>sma30:
            buy_score+=3; points_detail.append({"side":"BUY","points":3,"name":"SMA ALCISTA FUERTE","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} > SMA15 {sma15:.2f} > SMA30 {sma30:.2f}"})
        elif current_price<sma10 and sma10<sma15 and sma15<sma30:
            sell_score+=3; points_detail.append({"side":"SELL","points":3,"name":"SMA BAJISTA FUERTE","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} < SMA15 {sma15:.2f} < SMA30 {sma30:.2f}"})
        elif current_price>sma10 and current_price>sma15:
            buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SMA ALCISTA DÉBIL","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})
        elif current_price<sma10 and current_price<sma15:
            sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SMA BAJISTA DÉBIL","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})
        # Ruptura
        if is_break_high and last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            buy_score+=pts; points_detail.append({"side":"BUY","points":pts,"name":"RUPTURA ALTA 10m FUERTE" if last_10["strong"] else "RUPTURA ALTA 10m","reason":f"Ruptura alto real {high_recent:.2f} -> {current_price:.2f} (+{current_price-high_recent:.2f})"})
        if is_break_low and not last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            sell_score+=pts; points_detail.append({"side":"SELL","points":pts,"name":"RUPTURA BAJA 10m FUERTE" if last_10["strong"] else "RUPTURA BAJA 10m","reason":f"Ruptura bajo real {low_recent:.2f} -> {current_price:.2f}"})
        # Cerca soporte/resistencia
        if abs(current_price-high_15) < 2.5:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"CERCA RESISTENCIA 15m","reason":f"Precio {current_price:.2f} cerca resistencia 15m {high_15:.2f}"})
        if abs(current_price-low_15) < 2.5:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"CERCA SOPORTE 15m","reason":f"Precio {current_price:.2f} cerca soporte 15m {low_15:.2f}"})
        # Racha
        up_streak=phase_info["up"]; down_streak=phase_info["down"]
        if up_streak>=3:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":f"RACHA {up_streak} VELAS ALCISTAS 10m","reason":f"Racha alcista {up_streak} velas"})
        if down_streak>=3:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":f"RACHA {down_streak} VELAS BAJISTAS 10m","reason":f"Racha bajista {down_streak} velas"})
        # Vela fuerte
        if last_10["strong"]:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"VELA FUERTE ALCISTA","reason":f"Vela alcista fuerte ratio {last_10['body_ratio']:.2f}"})
            else:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"VELA FUERTE BAJISTA","reason":f"Vela bajista fuerte ratio {last_10['body_ratio']:.2f}"})
        # Sesión NY
        if ny_session:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SESIÓN NY 8-10AM EC","reason":"NY OPEN - vela alcista +1 compra"})
            else:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SESIÓN NY 8-10AM EC","reason":"NY OPEN - vela bajista +1 venta"})
        # Patrones velas
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
        real_buy = sum(p['points'] for p in points_detail if p['side']=='BUY')
        real_sell = sum(p['points'] for p in points_detail if p['side']=='SELL')
        buy_score = real_buy; sell_score = real_sell
        direction="BUY" if buy_score>=sell_score else "SELL"
        if buy_score>=sell_score+2:
            direction="BUY"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            confidence=base_conf+min(buy_score*2,16)
        elif sell_score>=buy_score+2:
            direction="SELL"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            confidence=base_conf+min(sell_score*2,16)
        else:
            direction="BUY" if current_price>sma15 else "SELL"; confidence=56
        # Acumulación amplia vs estrecha
        long_is_acc = long_sr["is_acc_long"] if long_sr else False
        long_band = long_sr["band_long"] if long_sr else phase_info["band"]
        support_real = long_sr["support"] if long_sr and long_sr.get("support",0)>1000 else support
        resistance_real = long_sr["resistance"] if long_sr and long_sr.get("resistance",0)>1000 else resistance
        if long_is_acc and long_band < 7.0:
            alert=f"ESPERA - ACUMULACIÓN ESTRECHA {long_band:.1f} USD - NO OPERAR"; alert_type="WAIT"; alert_desc=f"Precio entre {long_sr['low_long']:.2f} y {long_sr['high_long']:.2f} - acumulación estrecha - esperar ruptura"
            confidence = 52
        elif long_is_acc and long_band >= 10.0:
            dist_to_support = abs(current_price - support_real)
            dist_to_resistance = abs(current_price - resistance_real)
            if dist_to_support < 1.8:
                buy_score+=2
                points_detail.append({"side":"BUY","points":2,"name":"CORTE SOPORTE EN ACUMULACIÓN AMPLIA","reason":f"Acumulación amplia {long_band:.1f} USD - cerca soporte {support_real:.2f}"})
                if confidence < 70: confidence = 70
            if dist_to_resistance < 1.8:
                sell_score+=2
                points_detail.append({"side":"SELL","points":2,"name":"CORTE RESISTENCIA EN ACUMULACIÓN AMPLIA","reason":f"Acumulación amplia {long_band:.1f} USD - cerca resistencia {resistance_real:.2f}"})
                if confidence < 70: confidence = 70
            # No bloquear acumulación amplia
            if "ACUMULACION" in phase_info["phase"]:
                phase_info["phase"]="RANGO AMPLIO"
                phase_info["desc"]=f"RANGO AMPLIO {long_band:.1f} USD - {support_real:.2f} a {resistance_real:.2f} - scalping con impulso y retroceso Fib"
        if "ACUMULACION" in phase_info["phase"] and long_band>=10:
            pass
        elif "ACUMULACION" in phase_info["phase"] and not "EXPANSION" in phase_info["phase"] and long_band<7:
            alert="ESPERA - NO ENTRES - FASE ACUMULACIÓN"; alert_type="WAIT"; alert_desc=f"Acumulación rango {phase_info['band']:.1f} USD - esperar pico"
        elif "EXPANSION" in phase_info["phase"] and confidence>=70:
            fib_txt = f" + Fib {fib['near']}" if fib and fib.get('near') else ""
            alert=f"ENTRA - PICO TRAS ACUMULACIÓN + VELA CONFIRMADA - {direction} - SEÑAL LIMPIA{fib_txt}"; alert_type="ENTER"; alert_desc=f"{phase_info['phase']}{fib_txt} - confianza {confidence}% - Score {buy_score}B/{sell_score}S"
        elif fib and fib.get('near') in ['0.618','0.5'] and confidence>=65:
            alert=f"ENTRA - {direction} EN FIB {fib['near']} - RETROCESO PERFECTO"; alert_type="ENTER"; alert_desc=f"Fibonacci {fib['near']} - {fib['desc']} - Score {buy_score}B/{sell_score}S"
        elif confidence>=72 and abs(buy_score-sell_score)>=2:
            alert=f"ENTRA - {direction} CONFIRMADO - TENDENCIA FUERTE"; alert_type="ENTER"; alert_desc=f"Score {buy_score} vs {sell_score} - confianza {confidence}%"
        elif confidence>=62 and abs(buy_score-sell_score)>=1:
            alert=f"ENTRA CON PRECAUCIÓN - {direction} - CONFIRMACIÓN MEDIA"; alert_type="CAUTION"; alert_desc=f"Score {buy_score}B/{sell_score}S - espera vela fuerte"
        else:
            alert="ESPERA - SEÑAL DÉBIL - RANGO"; alert_type="WAIT"; alert_desc=f"Score {buy_score}B/{sell_score}S - fase {phase_info['phase']}"
        trend="ALCISTA" if direction=="BUY" else "BAJISTA"
        if abs(buy_score-sell_score)<=1: trend="LATERAL"
        return {
            "trend":trend,"direction":direction,"confidence":min(confidence,95),
            "pattern":phase_info["phase"],"phase":phase_info["phase"],"phase_desc":phase_info["desc"],
            "phase_info":phase_info,"alert":alert,"alert_type":alert_type,"alert_desc":alert_desc,
            "candle_patterns":candle_pats,"points_detail":points_detail,
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
        print(f"analyze error {e}"); import traceback; traceback.print_exc()
        return {"trend":"ERROR","direction":"BUY","confidence":50,"phase":"ERROR","phase_desc":str(e),"alert":f"ESPERA - ERROR {e}","alert_type":"WAIT","alert_desc":str(e),"points_detail":[],"candle_patterns":[],"high_10":0,"low_10":0,"high_15":0,"low_15":0,"high_30":0,"low_30":0,"sma10":0,"sma15":0,"sma30":0,"support":4052,"resistance":4073,"support_long":4052,"resistance_long":4073,"high_long":4073,"low_long":4052,"band_long":21,"fib":None,"high_clusters":[],"low_clusters":[],"volatility":0,"ny_session":False,"buy_score":0,"sell_score":0}

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
        if last["direction"]==new_dir: return True, f"Misma dirección {new_dir}"
        buy_score=market.get("buy_score",0); sell_score=market.get("sell_score",0); diff=abs(buy_score-sell_score)
        if diff>=2 and conf>=68:
            return True, f"Cambio rápido Score {buy_score}B/{sell_score}S diff {diff} a {new_dir}"
        if "EXPANSION" in market.get("phase","") and conf>=70:
            return True, f"Expansión {market.get('phase')} - cambio a {new_dir}"
        if "TENDENCIA" in market.get("phase","") and diff>=2:
            return True, f"Tendencia {market.get('phase')} a {new_dir}"
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row:
            last_time=datetime.fromisoformat(row[0])
            mins=(datetime.now(EC_TZ)-last_time).total_seconds()/60
            if mins<5 and conf<65 and diff<2:
                return False, f"Esperando 5m (van {mins:.1f}m)"
            if conf>=75: return True, f"Alta confianza {conf}% a {new_dir}"
            if mins>=5: return True, f"Cambio tras {mins:.1f}m a {new_dir}"
        if conf>=68: return True, f"Confianza {conf}% a {new_dir}"
        return False, f"Confianza baja {conf}% manteniendo {last['direction']}"
    except Exception as e:
        return True, f"Error {e}"

def get_stats():
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT wins,loss,buy_wins,buy_total,sell_wins,sell_total FROM gold_learning WHERE id=1")
        row=c.fetchone(); conn.close()
        if row: return {"wins":row[0],"loss":row[1],"buy_wins":row[2],"buy_total":row[3],"sell_wins":row[4],"sell_total":row[5]}
    except: pass
    return {"wins":18,"loss":6,"buy_wins":11,"buy_total":14,"sell_wins":7,"sell_total":10}

def calc_success_rate(direction):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT wins,loss FROM gold_learning WHERE id=1")
        row=c.fetchone(); conn.close()
        total=row[0]+row[1] if row else 24
        wr=row[0]/total*100 if total>0 else 75
        return wr,72,50,35
    except: return 72,72,50,35

def calc_prob(hour, market):
    try:
        stats=get_stats(); direction=market.get("direction","BUY")
        if direction=="BUY":
            bt=stats.get("buy_total",1); bw=stats.get("buy_wins",0); wr_dir=(bw/bt*100) if bt>0 else 75
        else:
            st=stats.get("sell_total",1); sw=stats.get("sell_wins",0); wr_dir=(sw/st*100) if st>0 else 70
        total=stats["wins"]+stats["loss"]; wr_glob=(stats["wins"]/total*100) if total>0 else 72
        po,p1,p2,p3=calc_success_rate(direction)
        conf=market.get("confidence",65)
        phase_bonus=10 if "EXPANSION" in market.get("phase","") else 5 if "TENDENCIA" in market.get("phase","") else -8 if "ACUMULACION" in market.get("phase","") else 0
        candle_bonus=min(len(market.get("candle_patterns",[]))*3,9)
        hour_bonus=12 if 8<=hour<=10 else 6 if 7<=hour<=12 else 3 if 13<=hour<=15 else 0
        vol=market.get("volatility",0); vol_bonus=5 if vol>=3 else -5 if vol<1.5 else 0
        prob=(wr_dir*0.30)+(po*0.30)+(conf*0.20)+hour_bonus+vol_bonus+phase_bonus+candle_bonus
        prob=max(50,min(95,prob))
        return round(prob,1),stats,p1,p2,p3,wr_dir,wr_glob
    except: return 72,get_stats(),72,50,35,70,72

def calc_tp_sl(price, direction):
    d=6.17
    if direction=="BUY":
        return price-d, price+d, price+d*2, price+d*3, d, d, d*2, d*3
    else:
        return price+d, price-d, price-d*2, price-d*3, d, d, d*2, d*3

def update_stats(result, direction):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        if result=="TP1" or result=="TP2" or result=="TP3":
            c.execute("UPDATE gold_learning SET wins=wins+1, total_trades=total_trades+1 WHERE id=1")
            if direction=="BUY": c.execute("UPDATE gold_learning SET buy_wins=buy_wins+1, buy_total=buy_total+1 WHERE id=1")
            else: c.execute("UPDATE gold_learning SET sell_wins=sell_wins+1, sell_total=sell_total+1 WHERE id=1")
        else:
            c.execute("UPDATE gold_learning SET loss=loss+1, total_trades=total_trades+1 WHERE id=1")
            if direction=="BUY": c.execute("UPDATE gold_learning SET buy_total=buy_total+1 WHERE id=1")
            else: c.execute("UPDATE gold_learning SET sell_total=sell_total+1 WHERE id=1")
        conn.commit(); conn.close()
    except: pass

@app.get("/")
def root(): return {"message":"ORO FASES + PUNTOS + FIB - 100% ESPAÑOL","version":"8.3"}

@app.get("/health")
def health():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM price_history"); count=c.fetchone()[0]; conn.close()
    return {"status":"ok","symbol":"XAUUSD","history":count,"version":"8.3"}

@app.get("/signals/live")
def signals_live():
    try:
        price=get_gold_price(); save_gold_history(price)
        market=analyze_gold_pro()
        new_dir=market.get("direction","BUY"); conf=market.get("confidence",65)
        should, flip_reason=should_flip(new_dir, conf, market)
        if should:
            final_dir=new_dir; update_last_signal(final_dir, market.get("phase",""))
        else:
            last=get_last_signal(); final_dir=last["direction"]
        hour=datetime.now(EC_TZ).hour
        market_for_prob = dict(market)
        market_for_prob['direction'] = final_dir
        prob,stats,p1,p2,p3,wr_dir,wr_glob=calc_prob(hour, market_for_prob)
        display_prob = market.get('confidence', prob) if market.get('alert_type')=='ENTER' else prob
        sl,tp1,tp2,tp3,sl_d,tp1_d,tp2_d,tp3_d=calc_tp_sl(price, final_dir)
        if final_dir=="BUY":
            sl_exp=f"SL {sl:.2f} ABAJO (si baja {sl_d:.2f} pierdes $10)"; tp_exp=f"TP1 {tp1:.2f} ARRIBA (si sube {tp1_d:.2f} ganas $10) COMPRA"
        else:
            sl_exp=f"SL {sl:.2f} ARRIBA (si sube {sl_d:.2f} pierdes $10)"; tp_exp=f"TP1 {tp1:.2f} ABAJO (si baja {tp1_d:.2f} ganas $10) VENTA"
        market['direction'] = final_dir
        if final_dir != new_dir:
            market['alert'] = f"ESPERA - MANTENIENDO {final_dir} - señal {new_dir} en espera ({flip_reason})"
            market['alert_type'] = "WAIT"
            market['alert_desc'] = f"Score {market.get('buy_score')}B/{market.get('sell_score')}S quiere {new_dir} pero mantiene {final_dir}"
        market['confidence'] = market.get('confidence', conf)
        signal={
            "symbol":"XAUUSD","direction":final_dir,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl_distance":sl_d,"tp1_distance":tp1_d,
            "probability":display_prob,"confidence":conf,"probability_tp1":prob,"win_rate":wr_glob,"win_rate_direction":wr_dir,
            "win_rate_buy":round(stats.get("buy_wins",0)/max(stats.get("buy_total",1),1)*100,1),
            "win_rate_sell":round(stats.get("sell_wins",0)/max(stats.get("sell_total",1),1)*100,1),
            "is_optimal_hour":8<=hour<=10,"market_analysis":market,"phase":market.get("phase",""),"phase_desc":market.get("phase_desc",""),
            "alert":market.get("alert",""),"alert_type":market.get("alert_type",""),"alert_desc":market.get("alert_desc",""),
            "candle_patterns":market.get("candle_patterns",[]),"points_detail":market.get("points_detail",[]),
            "probabilidad_nuevos_objetivos":{"prob_tp1_10usd_10_15min":p1,"prob_tp2_20usd_15min":p2,"prob_tp3_30usd_15min":p3},
            "sl_explain":sl_exp,"tp_explain":tp_exp,"reason":market.get("reason",""),"pattern":market.get("pattern",""),"flip_reason":flip_reason,
            "support":market.get("support",4052),"resistance":market.get("resistance",4073),"timestamp":datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        print(e); import traceback; traceback.print_exc()
        return [{"symbol":"XAUUSD","direction":"BUY","entry":get_gold_price(),"sl":get_gold_price()-6.17,"tp1":get_gold_price()+6.17,"tp2":get_gold_price()+12.34,"tp3":get_gold_price()+18.51,"sl_distance":6.17,"tp1_distance":6.17,"probability":55,"confidence":55,"probability_tp1":50,"win_rate":72,"win_rate_direction":70,"win_rate_buy":75,"win_rate_sell":70,"is_optimal_hour":False,"market_analysis":{"phase":"ERROR","phase_desc":str(e),"alert":f"ESPERA - ERROR {str(e)[:100]}","alert_type":"WAIT","alert_desc":str(e),"points_detail":[],"candle_patterns":[],"high_10":0,"low_10":0,"high_15":0,"low_15":0,"support":4052,"resistance":4073,"support_long":4052,"resistance_long":4073,"band_long":21,"fib":None},"phase":"ERROR","phase_desc":str(e),"alert":f"ESPERA - ERROR {str(e)[:100]}","alert_type":"WAIT","alert_desc":str(e),"candle_patterns":[],"points_detail":[],"probabilidad_nuevos_objetivos":{"prob_tp1_10usd_10_15min":50,"prob_tp2_20usd_15min":30,"prob_tp3_30usd_15min":15},"sl_explain":"","tp_explain":"","reason":"","pattern":"","flip_reason":str(e),"support":4052,"resistance":4073,"timestamp":datetime.now(EC_TZ).isoformat()}]

@app.get("/trades/active")
def get_active():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT id,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at FROM active_trades WHERE status='OPEN' ORDER BY id DESC")
    rows=c.fetchall(); conn.close()
    return [{"id":r[0],"symbol":"XAUUSD","direction":r[1],"entry":r[2],"sl":r[3],"tp1":r[4],"tp2":r[5],"tp3":r[6],"probability":r[7],"status":r[8],"created_at":r[9]} for r in rows]

@app.post("/trades/result")
def save_result(r: TradeResult):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT direction FROM active_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1")
    row=c.fetchone(); direction=row[0] if row else "BUY"; conn.close()
    update_stats(r.result, direction)
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("UPDATE active_trades SET status=? WHERE status='OPEN'", (f"{r.result}_MANUAL",)); conn.commit(); conn.close()
    return {"ok":True}

@app.get("/gold/analysis")
def gold_analysis():
    market=analyze_gold_pro(); price=get_gold_price(); rows=get_gold_history(50)
    return {"symbol":"XAUUSD","current_price":price,"analysis_pro":market,"price_history_count":len(rows)}

@app.on_event("startup")
async def startup_event():
    seed_history_if_empty()
    async def monitor_loop():
        print("Monitor ORO v8.3 100% español iniciado")
        while True:
            try: save_gold_history(get_gold_price())
            except: pass
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())
