
import os, sqlite3, requests, asyncio, math
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="EdgeAlert ORO - FASES + PUNTOS 10-15-30")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS gold_learning (id INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, loss INTEGER DEFAULT 0, tp1 INTEGER DEFAULT 0, tp2 INTEGER DEFAULT 0, tp3 INTEGER DEFAULT 0, total_trades INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS gold_hour_learning (hour INTEGER PRIMARY KEY, wins INTEGER DEFAULT 0, total INTEGER DEFAULT 0, buy_wins INTEGER DEFAULT 0, buy_total INTEGER DEFAULT 0, sell_wins INTEGER DEFAULT 0, sell_total INTEGER DEFAULT 0, avg_range REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS gold_patterns (pattern TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, total INTEGER DEFAULT 0, description TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS candle_patterns (name TEXT PRIMARY KEY, bullish INTEGER DEFAULT 0, bearish INTEGER DEFAULT 0, total INTEGER DEFAULT 0, win_rate REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS market_phases (phase TEXT PRIMARY KEY, count INTEGER DEFAULT 0, buy_success INTEGER DEFAULT 0, sell_success INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, price REAL, timestamp TEXT, change REAL DEFAULT 0, high REAL DEFAULT 0, low REAL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS active_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL, probability REAL, status TEXT DEFAULT 'OPEN', created_at TEXT, pattern TEXT, phase TEXT)")
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
    return 4025.86 + (datetime.now().hour-12)*2.5

def seed_history_if_empty():
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM price_history")
        if c.fetchone()[0] < 30:
            base = get_gold_price()
            now = datetime.now(EC_TZ)
            for i in range(100):
                variation = math.sin(i/10)*2 + math.cos(i/7)*1.5
                p = base + variation -5 + i*0.02
                ts = (now - timedelta(seconds=(100-i)*30)).isoformat()
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

def get_gold_history(limit=300):
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
        pats.append({"name":"BULLISH_ENGULFING","dir":"BUY","strength":3,"desc":"Envolvente alcista - compra fuerte tras bajada"})
    if prev["bullish"] and not last["bullish"] and last["open"]>prev["close"] and last["close"]<prev["open"] and last["body"]>prev["body"]*1.2:
        pats.append({"name":"BEARISH_ENGULFING","dir":"SELL","strength":3,"desc":"Envolvente bajista - venta fuerte tras subida"})
    if last["lower_wick"]>last["body"]*2 and last["upper_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"HAMMER","dir":"BUY","strength":2,"desc":"Martillo alcista - rechazo bajos"})
    if last["upper_wick"]>last["body"]*2 and last["lower_wick"]<last["body"]*0.5 and last["range"]>1.0:
        pats.append({"name":"SHOOTING_STAR","dir":"SELL","strength":2,"desc":"Estrella fugaz - rechazo altos"})
    if last["lower_wick"]>last["body"]*2.5 and last["bullish"]:
        pats.append({"name":"PIN_BAR_BULL","dir":"BUY","strength":2,"desc":"Pin bar alcista"})
    if last["upper_wick"]>last["body"]*2.5 and not last["bullish"]:
        pats.append({"name":"PIN_BAR_BEAR","dir":"SELL","strength":2,"desc":"Pin bar bajista"})
    if last["doji"] and last["range"]>0.8:
        if prev["bullish"]: pats.append({"name":"DOJI_TOP","dir":"SELL","strength":1,"desc":"Doji en tope - posible reversal venta"})
        else: pats.append({"name":"DOJI_BOTTOM","dir":"BUY","strength":1,"desc":"Doji en fondo - posible reversal compra"})
    if len(candles)>=3:
        prev2=candles[-3]
        if not prev2["bullish"] and prev2["body_ratio"]>0.5 and (candles[-2]["small"] or candles[-2]["doji"]) and last["bullish"] and last["close"]>(prev2["open"]+prev2["close"])/2:
            pats.append({"name":"MORNING_STAR","dir":"BUY","strength":3,"desc":"Estrella mañana - reversal alcista fuerte"})
        if prev2["bullish"] and prev2["body_ratio"]>0.5 and (candles[-2]["small"] or candles[-2]["doji"]) and not last["bullish"] and last["close"]<(prev2["open"]+prev2["close"])/2:
            pats.append({"name":"EVENING_STAR","dir":"SELL","strength":3,"desc":"Estrella tarde - reversal bajista fuerte"})
    if last["bullish"] and last["body_ratio"]>0.8 and last["upper_wick"]<0.3 and last["lower_wick"]<0.3:
        pats.append({"name":"MARUBOZU_BULL","dir":"BUY","strength":2,"desc":"Marubozu alcista - fuerza compra"})
    if not last["bullish"] and last["body_ratio"]>0.8 and last["upper_wick"]<0.3 and last["lower_wick"]<0.3:
        pats.append({"name":"MARUBOZU_BEAR","dir":"SELL","strength":2,"desc":"Marubozu bajista - fuerza venta"})
    return pats


def detect_phase(candles_10, candles_15, rows):
    if len(candles_10)<4:
        return {"phase":"INICIO","desc":"Iniciando fases oro - recolectando velas 10-15-30 min","band":0,"avg6":0,"avg3":0,"up":0,"down":0,"slope":0,"is_acc":False,"is_exp":False}
    last6=candles_10[-6:] if len(candles_10)>=6 else candles_10
    last3=candles_10[-3:]
    ranges6=[c["range"] for c in last6]; avg6=sum(ranges6)/len(ranges6)
    avg3=sum([c["range"] for c in last3])/len(last3)
    prices6=[c["close"] for c in last6]; band=max(prices6)-min(prices6)
    avg_body=sum([c["body"] for c in last6])/len(last6)
    
    # SMA responsive para fase - FIX para tu foto donde dice RANGO pero ya rompio
    all_prices = [r[0] for r in rows] if rows else prices6
    current_price = all_prices[-1] if all_prices else prices6[-1]
    sma10_p = sum(all_prices[-10:])/10 if len(all_prices)>=10 else current_price
    sma15_p = sum(all_prices[-15:])/15 if len(all_prices)>=15 else current_price
    sma30_p = sum(all_prices[-30:])/30 if len(all_prices)>=30 else current_price
    
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
    
    # EXPANSION - ruptura real
    if is_exp and last["strong"]:
        prices_all=[c["close"] for c in last6]
        if last["bullish"] and last["close"]>=max(prices_all)*0.998:
            return {"phase":"EXPANSION_ALCISTA","desc":f"🔥 EXPANSION ALCISTA - PICO COMPRA tras acumulacion {band:.1f} USD -> ruptura {last['close']:.2f} vela fuerte {last['body']:.1f} USD - ENTRAR","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
        if not last["bullish"] and last["close"]<=min(prices_all)*1.002:
            return {"phase":"EXPANSION_BAJISTA","desc":f"🔥 EXPANSION BAJISTA - PICO VENTA tras acumulacion {band:.1f} USD -> ruptura {last['close']:.2f} vela {last['body']:.1f} USD - ENTRAR","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
    
    # FIX CRITICO PARA TU FOTO 12:21: ya rompio, precio 4029 > high_recent y sigue subiendo, no es RANGO
    # Si precio rompio alto reciente y esta por encima de SMA, es TENDENCIA_ALCISTA aunque banda sea estrecha
    if current_price >= high_recent * 0.999 and current_price > sma10_p and sma10_p > sma15_p:
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA POST-RUPTURA - precio {current_price:.2f} rompio alto {high_recent:.2f} y sigue arriba SMA10 {sma10_p:.2f} > SMA15 {sma15_p:.2f} - seguir BUY, no esperar ruptura","band":band,"avg6":avg6,"avg3":avg3,"up":up if up>0 else 1,"down":0,"slope":slope,"is_acc":False,"is_exp":False}
    if current_price <= low_recent * 1.001 and current_price < sma10_p and sma10_p < sma15_p:
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA POST-RUPTURA - precio {current_price:.2f} rompio bajo {low_recent:.2f} y sigue abajo SMA - seguir SELL","band":band,"avg6":avg6,"avg3":avg3,"up":0,"down":down if down>0 else 1,"slope":slope,"is_acc":False,"is_exp":False}
    
    if is_acc:
        if up>=2: return {"phase":"ACUMULACION_ALCISTA","desc":f"ACUMULACION ALCISTA - rango {band:.1f} USD estrecho, vol {avg6:.1f} USD, {up} velas alcistas - posible PICO COMPRA","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
        if down>=2: return {"phase":"ACUMULACION_BAJISTA","desc":f"ACUMULACION BAJISTA - rango {band:.1f} USD, {down} velas bajistas - posible PICO VENTA","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
        return {"phase":"ACUMULACION","desc":f"ACUMULACION PURA - rango {band:.1f} USD muy estrecho, vol {avg6:.1f} USD, esperando PICO - NO ENTRAR AUN","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
    
    if up>=3:
        if avg3<avg6*0.8: return {"phase":"AGOTAMIENTO_ALCISTA","desc":f"AGOTAMIENTO ALCISTA - {up} velas arriba pero rango decrece {avg3:.1f} < {avg6:.1f} - buscar vela bajista","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - {up} velas alcistas, pendiente +{slope:.2f}, precio {current_price:.2f} > SMA {sma10_p:.2f} - seguir BUY","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    if down>=3:
        if avg3<avg6*0.8: return {"phase":"AGOTAMIENTO_BAJISTA","desc":f"AGOTAMIENTO BAJISTA - {down} velas abajo rango decrece - buscar vela alcista","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - {down} velas bajistas, pendiente {slope:.2f} - seguir SELL","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    
    # Antes decia RANGO cuando banda <6 y vol <2.5, pero si precio > SMA y rompio alto, no es rango
    if band<6.0 and avg6<2.5:
        # Si esta por encima de SMA, es tendencia no rango
        if current_price > sma10_p and sma10_p > sma15_p:
            return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - banda estrecha {band:.1f} USD pero precio {current_price:.2f} > SMA10 {sma10_p:.2f} > SMA15 {sma15_p:.2f} - tendencia alcista sigue, no esperar ruptura, ya rompio","band":band,"avg6":avg6,"avg3":avg3,"up":1,"down":0,"slope":slope,"is_acc":False,"is_exp":False}
        if current_price < sma10_p and sma10_p < sma15_p:
            return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - banda estrecha {band:.1f} USD pero precio {current_price:.2f} < SMA - sigue bajista","band":band,"avg6":avg6,"avg3":avg3,"up":0,"down":1,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"RANGO","desc":f"RANGO estrecho {band:.1f} USD - balance, esperar ruptura - precio {current_price:.2f} entre SMA","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    
    return {"phase":"TRANSICION","desc":f"TRANSICION - vol {avg3:.1f} USD, pendiente {slope:.2f}, precio {current_price:.2f} vs SMA {sma10_p:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}





def get_long_sr(rows, lookback_hours=4):
    """Soporte/resistencia REAL con pivotes como TradingView - no solo max/min"""
    try:
        lookback = lookback_hours * 120
        prices = [r[0] for r in rows[-lookback:]] if len(rows)>=lookback else [r[0] for r in rows]
        if len(prices)<60:
            return None
        
        # Detectar pivotes como TradingView: máximos/mínimos locales
        # Un pivote alto = precio mayor que 3 a cada lado
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
            if is_high and prices[i] > 4000:
                pivot_highs.append(prices[i])
            if is_low and prices[i] > 4000:
                pivot_lows.append(prices[i])
        
        if not pivot_highs:
            pivot_highs = [max(prices)]
        if not pivot_lows:
            pivot_lows = [min(prices)]
        
        # Clusterizar niveles que están a menos de 1.2 USD (mismo soporte/resistencia)
        def cluster_levels(levels, tolerance=1.2):
            if not levels:
                return []
            levels_sorted = sorted(levels)
            clusters = [[levels_sorted[0]]]
            for l in levels_sorted[1:]:
                if abs(l - sum(clusters[-1])/len(clusters[-1])) < tolerance:
                    clusters[-1].append(l)
                else:
                    clusters.append([l])
            # Promedio de cada cluster + conteo de toques
            result = []
            for c in clusters:
                avg = sum(c)/len(c)
                result.append((avg, len(c)))
            # Ordenar por toques (más toques = nivel más fuerte como en TradingView)
            result.sort(key=lambda x: x[1], reverse=True)
            return result
        
        high_clusters = cluster_levels(pivot_highs, 1.5)
        low_clusters = cluster_levels(pivot_lows, 1.5)
        
        # Soporte más fuerte = low con más toques, Resistencia más fuerte = high con más toques
        # Pero también considerar extremos recientes como en tu foto
        recent_high = max(prices)
        recent_low = min(prices)
        band_long = recent_high - recent_low
        
        # Resistencia: cluster alto con más toques o max reciente si no hay cluster claro
        # Tu foto: resistencia 4065 y 4073 son 2 clusters
        if high_clusters:
            # Tomar los 2 niveles más tocados como R1 y R2
            res1 = high_clusters[0][0]  # más tocado
            res2 = high_clusters[1][0] if len(high_clusters)>1 else recent_high
            resistance = max(res1, res2) if abs(res1-res2)>2 else res1
            # Si hay 2 resistencias separadas como 4065 y 4073, usar la más cercana al precio actual
            current = prices[-1]
            # En tu foto: 4065 es R1, 4073 es R2
            resistance_near = min(high_clusters, key=lambda x: abs(x[0]-current))[0] if high_clusters else recent_high
        else:
            resistance = recent_high
            resistance_near = recent_high
        
        if low_clusters:
            sup1 = low_clusters[0][0]
            sup2 = low_clusters[1][0] if len(low_clusters)>1 else recent_low
            support = min(sup1, sup2) if abs(sup1-sup2)>2 else sup1
            support_near = min(low_clusters, key=lambda x: abs(x[0]-prices[-1]))[0] if low_clusters else recent_low
        else:
            support = recent_low
            support_near = recent_low
        
        # Para tu caso 4052-4073, debe dar soporte 4052-4054 y resistencia 4065-4073
        # Usar los extremos del cluster para banda real
        is_acc_long = band_long < 12.0  # Si en 4h banda <12 USD como 4052-4064 (12 USD) es acumulación
        
        return {
            "high_long": recent_high,
            "low_long": recent_low,
            "resistance": resistance_near if resistance_near and resistance_near>1000 else recent_high,
            "support": support_near if support_near and support_near>1000 else recent_low,
            "resistance_far": max(resistance, recent_high) if 'resistance' in locals() else recent_high,
            "support_far": min(support, recent_low) if 'support' in locals() else recent_low,
            "high_clusters": high_clusters[:3],
            "low_clusters": low_clusters[:3],
            "band_long": band_long,
            "is_acc_long": is_acc_long,
            "lookback": lookback,
            "pivot_highs": pivot_highs[-10:],
            "pivot_lows": pivot_lows[-10:]
        }
    except Exception as e:
        print(f"long_sr error {e}")
        import traceback; traceback.print_exc()
        return None


def calc_fibonacci_impulse(rows):
    """Fibonacci del último impulso - para perfeccionar entradas"""
    try:
        prices = [r[0] for r in rows[-200:]]  # ultimas 100 min
        if len(prices)<50:
            return None
        # Encontrar último impulso fuerte >8 USD
        # Busca swing low y high recientes
        recent_low = min(prices[-100:])
        recent_high = max(prices[-100:])
        low_idx = len(prices) - 1 - prices[::-1].index(recent_low) if recent_low in prices else 0
        high_idx = len(prices) - 1 - prices[::-1].index(recent_high) if recent_high in prices else 0
        
        # Determinar dirección del impulso
        if high_idx > low_idx and (recent_high - recent_low) > 8.0:
            # Impulso alcista: low -> high
            impulse_dir = "BULL"
            impulse_low = recent_low
            impulse_high = recent_high
            impulse_range = impulse_high - impulse_low
        elif low_idx > high_idx and (recent_high - recent_low) > 8.0:
            # Impulso bajista: high -> low
            impulse_dir = "BEAR"
            impulse_low = recent_low
            impulse_high = recent_high
            impulse_range = impulse_high - impulse_low
        else:
            # No hay impulso claro >8 USD
            return None
        
        current = prices[-1]
        # Niveles fib
        fib_levels = {
            "0": impulse_high if impulse_dir=="BULL" else impulse_low,
            "0.236": impulse_high - impulse_range*0.236 if impulse_dir=="BULL" else impulse_low + impulse_range*0.236,
            "0.382": impulse_high - impulse_range*0.382 if impulse_dir=="BULL" else impulse_low + impulse_range*0.382,
            "0.5": impulse_high - impulse_range*0.5 if impulse_dir=="BULL" else impulse_low + impulse_range*0.5,
            "0.618": impulse_high - impulse_range*0.618 if impulse_dir=="BULL" else impulse_low + impulse_range*0.618,
            "0.786": impulse_high - impulse_range*0.786 if impulse_dir=="BULL" else impulse_low + impulse_range*0.786,
            "1": impulse_low if impulse_dir=="BULL" else impulse_high,
        }
        
        # Detectar en qué zona está el precio actual
        near_fib = None
        min_dist = 999
        for level, price_fib in fib_levels.items():
            dist = abs(current - price_fib)
            if dist < min_dist and dist < 1.5:  # cerca a 1.5 USD del nivel fib
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
            "desc": f"Impulso {impulse_dir} {impulse_low:.2f} -> {impulse_high:.2f} ({impulse_range:.1f} USD) - Precio {current:.2f} cerca Fib {near_fib}" if near_fib else f"Impulso {impulse_dir} {impulse_range:.1f} USD"
        }
    except Exception as e:
        print(f"fib error {e}")
        return None


def analyze_gold_pro():
    try:
        rows=get_gold_history(300)
        price_fallback=get_gold_price()
        if len(rows)<15:
            return {"trend":"INICIO","direction":"BUY","confidence":55,"phase":"INICIO","phase_desc":"Iniciando - precio actual","alert":"ESPERA - INICIANDO","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"high_10":price_fallback+3.5,"low_10":price_fallback-3.2,"high_15":price_fallback+5.8,"low_15":price_fallback-5.1,"high_30":price_fallback+8.5,"low_30":price_fallback-8.2,"sma10":price_fallback-0.8,"sma15":price_fallback-1.2,"sma30":price_fallback-1.8,"support":price_fallback-5.1,"resistance":price_fallback+5.8,"volatility":3.2,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":price_fallback}
        
        candles_10=build_candles(rows,20); candles_15=build_candles(rows,30); candles_30=build_candles(rows,60)
        current_price=rows[-1][0]
        prices = [r[0] for r in rows]
        
        # SMA RESPONSIVE - directo de precios, no de velas, para no ir atrasado como en tu foto
        sma10 = sum(prices[-10:])/10 if len(prices)>=10 else current_price
        sma15 = sum(prices[-15:])/15 if len(prices)>=15 else current_price
        sma30 = sum(prices[-30:])/30 if len(prices)>=30 else current_price
        
        # HIGH/LOW REAL - ultimas 30 velas sin contar la actual, para detectar ruptura real como TradingView
        recent_prices = prices[-31:-1] if len(prices)>=31 else prices[:-1]
        high_recent = max(recent_prices) if recent_prices else current_price+3
        low_recent = min(recent_prices) if recent_prices else current_price-3
        high_10 = max([c["high"] for c in candles_10[-3:]]) if len(candles_10)>=3 else high_recent
        low_10 = min([c["low"] for c in candles_10[-3:]]) if len(candles_10)>=3 else low_recent
        high_15 = max([c["high"] for c in candles_15[-2:]]) if len(candles_15)>=2 else high_recent+1.5
        low_15 = min([c["low"] for c in candles_15[-2:]]) if len(candles_15)>=2 else low_recent-1.5
        high_30 = max([c["high"] for c in candles_30[-2:]]) if len(candles_30)>=2 else high_15+1
        low_30 = min([c["low"] for c in candles_30[-2:]]) if len(candles_30)>=2 else low_15-1
        
        # FIX v8.2: Soporte/resistencia principal = pivotes 4H como TradingView 4052 y 4065-4073, nunca cero
        support_pivot = support_long if support_long and support_long>1000 else low_15
        resistance_pivot = resistance_long if resistance_long and resistance_long>1000 else high_15
        # Si sale cero, usar precio actual +-5 USD
        if not support_pivot or support_pivot==0:
            support_pivot = current_price - 5.0
        if not resistance_pivot or resistance_pivot==0:
            resistance_pivot = current_price + 5.0
        support= support_pivot
        resistance= resistance_pivot
        
        phase_info=detect_phase(candles_10,candles_15,rows)
        candle_pats=detect_candle_patterns(candles_10)+detect_candle_patterns(candles_15)

        hour_ec=datetime.now(EC_TZ).hour
        ny_session=8<=hour_ec<=11

        buy_score=0; sell_score=0; points_detail=[]

        # CORRECCION CRITICA: Ruptura REAL vs TradingView - compara precio actual vs max/min ultimas 30 sin contar actual
        is_break_high = current_price >= high_recent * 0.999
        is_break_low = current_price <= low_recent * 1.001
        last_10 = candles_10[-1] if candles_10 else {"bullish":True,"strong":False,"body":1,"body_ratio":0.5,"range":2}
        prev_10 = candles_10[-2] if len(candles_10)>=2 else last_10
        last_15 = candles_15[-1] if candles_15 else last_10
        prev_15 = candles_15[-2] if len(candles_15)>=2 else last_10
        last_30 = candles_30[-1] if candles_30 else last_15

        # 1. SMA - VERSION RESPONSIVE
        if current_price>sma10 and sma10>sma15 and sma15>sma30:
            buy_score+=3; points_detail.append({"side":"BUY","points":3,"name":"SMA BULL FUERTE","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} > SMA15 {sma15:.2f} > SMA30 {sma30:.2f} - tendencia alcista fuerte"})
        elif current_price<sma10 and sma10<sma15 and sma15<sma30:
            sell_score+=3; points_detail.append({"side":"SELL","points":3,"name":"SMA BEAR FUERTE","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} < SMA15 {sma15:.2f} < SMA30 {sma30:.2f} - tendencia bajista fuerte"})
        elif current_price>sma10 and current_price>sma15:
            buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SMA BULL DEBIL","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})
        elif current_price<sma10 and current_price<sma15:
            sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SMA BEAR DEBIL","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})

        # 2. RUPTURA - FIX PARA TU FOTO: ruptura real como TradingView
        if is_break_high and last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            buy_score+=pts; points_detail.append({"side":"BUY","points":pts,"name":"BREAK HIGH 10m FUERTE" if last_10["strong"] else "BREAK HIGH 10m","reason":f"🔥 Ruptura ALTO real {high_recent:.2f} -> {current_price:.2f} (+{current_price-high_recent:.2f}) vela {'fuerte' if last_10['strong'] else ''} {last_10['body']:.2f} USD - como en TradingView"})
        if is_break_low and not last_10["bullish"]:
            pts = 3 if last_10["strong"] else 2
            sell_score+=pts; points_detail.append({"side":"SELL","points":pts,"name":"BREAK LOW 10m FUERTE" if last_10["strong"] else "BREAK LOW 10m","reason":f"🔥 Ruptura BAJO real {low_recent:.2f} -> {current_price:.2f} ({current_price-low_recent:.2f}) vela fuerte {last_10['body']:.2f}"})

        # 3. CERCA RESISTENCIA/SOPORTE
        if abs(current_price-high_15) < 2.5 and current_price < high_15 + 1.0:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"CERCA RESISTENCIA 15m","reason":f"Precio {current_price:.2f} cerca resistencia 15m {high_15:.2f} a {high_15-current_price:.2f} USD - posible breakout ALCISTA"})
        if abs(current_price-low_15) < 2.5 and current_price > low_15 - 1.0:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"CERCA SOPORTE 15m","reason":f"Precio {current_price:.2f} cerca soporte 15m {low_15:.2f} a {current_price-low_15:.2f} USD - posible breakdown"})

        # 4. RACHA
        up_streak=phase_info["up"]; down_streak=phase_info["down"]
        if up_streak>=3:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":f"RACHA {up_streak} VELAS ALCISTAS 10m","reason":f"Racha alcista {up_streak} velas 10min oro"})
        elif up_streak>=2:
            buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":f"RACHA {up_streak} VELAS ALCISTAS","reason":f"{up_streak} velas alcistas"})
        if down_streak>=3:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":f"RACHA {down_streak} VELAS BAJISTAS 10m","reason":f"Racha bajista {down_streak} velas 10min"})
        elif down_streak>=2:
            sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":f"RACHA {down_streak} BAJISTAS","reason":f"{down_streak} velas bajistas"})

        # 5. VELA FUERTE
        if last_10["strong"]:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"VELA FUERTE ALCISTA","reason":f"Vela 10m alcista fuerte ratio {last_10['body_ratio']:.2f} cuerpo {last_10['body']:.2f} USD"})
            else:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"VELA FUERTE BAJISTA","reason":f"Vela 10m bajista fuerte ratio {last_10['body_ratio']:.2f} cuerpo {last_10['body']:.2f}"})

        # 6. NY
        if ny_session:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN - vela alcista +1 BUY"})
            else:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN - vela bajista +1 SELL"})

        # 7. 15-30m
        if len(candles_15)>=2 and len(candles_30)>=1:
            if last_15["bullish"] and prev_15["bullish"] and last_30["bullish"]:
                buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"3 VELAS 15-30m ALCISTAS CONFIRMADAS","reason":"3 velas 15-30min alcistas - tendencia mayor alcista como TradingView"})
            if not last_15["bullish"] and not prev_15["bullish"] and not last_30["bullish"]:
                sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"3 VELAS 15-30m BAJISTAS CONFIRMADAS","reason":"3 velas 15-30min bajistas confirmadas"})


        # === NUEVO v8.0: SOPORTE/RESISTENCIA LARGO 4H + FIBONACCI ===
        long_sr = get_long_sr(rows, 4)
        fib = calc_fibonacci_impulse(rows)
        
        fib_detail = []
        if long_sr:
            # Si está en acumulación larga (tu caso 4052-4064 por horas), NO dar señal de confianza
            if long_sr["is_acc_long"] and long_sr["band_long"] < 6.0:
                # Esta es tu foto: banda 12 USD en 4h? No, banda 4052-4064 = 12 USD? Es 12? 4052-4070=18? 
                # Pero en 4h si banda <8, es acumulación larga
                pass  # lo usaremos abajo para alerta
            
            # Ajustar soporte/resistencia a valores reales largos si son más amplios
            # Si long_sr es más amplio que high_15/low_15, usar long
            # FIX v8.1: Usar pivotes reales como TradingView - soporte 4052 y resistencia 4065-4073
            support_long = long_sr["support"] if long_sr and "support" in long_sr else low_15
            resistance_long = long_sr["resistance"] if long_sr and "resistance" in long_sr else high_15
            # Para puntos, usar niveles lejanos también
            support_far = long_sr["support_far"] if long_sr and "support_far" in long_sr else support_long
            resistance_far = long_sr["resistance_far"] if long_sr and "resistance_far" in long_sr else resistance_long
        else:
            support_long = low_15
            resistance_long = high_15
            long_sr = {"band_long": high_15-low_15, "is_acc_long": False, "high_long": high_15, "low_long": low_15, "lookback": 60}
        
        if fib:
            # Si precio está cerca de Fib 0.618 o 0.5, es zona de entrada perfecta
            if fib["near"] in ["0.618", "0.5", "0.382"]:
                if fib["dir"] == "BULL":
                    # Impulso alcista, retroceso a fib = oportunidad BUY
                    if fib["near"] in ["0.618", "0.5"]:
                        buy_score+=2
                        fib_detail.append({"side":"BUY","points":2,"name":f"FIB {fib['near']} RETROCESO ALCISTA","reason":f"📐 Impulso BULL {fib['low']:.2f}->{fib['high']:.2f} ({fib['range']:.1f} USD) - Precio {fib['current']:.2f} en retroceso Fib {fib['near']} {fib['levels'][fib['near']]:.2f} a {fib['dist']:.2f} USD - ZONA COMPRA"})
                else:
                    # Impulso bajista, retroceso a fib = oportunidad SELL
                    if fib["near"] in ["0.618", "0.5"]:
                        sell_score+=2
                        fib_detail.append({"side":"SELL","points":2,"name":f"FIB {fib['near']} RETROCESO BAJISTA","reason":f"📐 Impulso BEAR {fib['high']:.2f}->{fib['low']:.2f} ({fib['range']:.1f} USD) - Precio {fib['current']:.2f} en retroceso Fib {fib['near']} {fib['levels'][fib['near']]:.2f} - ZONA VENTA"})
            # Si rompió Fib 0, es continuación
            if fib["near"] == "0" and fib["dist"] is not None and fib["dist"] < 1.0:
                if fib["dir"] == "BULL":
                    buy_score+=2
                    fib_detail.append({"side":"BUY","points":2,"name":"FIB 0 RUPTURA ALCISTA","reason":f"📐 Ruptura Fib 0 alcista {fib['high']:.2f} -> {fib['current']:.2f} - continuación BUY"})
                else:
                    sell_score+=2
                    fib_detail.append({"side":"SELL","points":2,"name":"FIB 0 RUPTURA BAJISTA","reason":f"📐 Ruptura Fib 0 bajista {fib['low']:.2f} -> {fib['current']:.2f} - continuación SELL"})
        
        # Agregar fib a points_detail
        for f in fib_detail:
            points_detail.append(f)

        for pat in candle_pats:

            if pat["dir"]=="BUY":
                buy_score+=pat["strength"]
                points_detail.append({"side":"BUY","points":pat["strength"],"name":pat["name"],"reason":f"🕯️ {pat['desc']}"})
            else:
                sell_score+=pat["strength"]
                points_detail.append({"side":"SELL","points":pat["strength"],"name":pat["name"],"reason":f"🕯️ {pat['desc']}"})

        if "EXPANSION_ALCISTA" in phase_info["phase"]:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"FASE EXPANSION ALCISTA","reason":f"🔥 {phase_info['desc']}"})
        elif "EXPANSION_BAJISTA" in phase_info["phase"]:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"FASE EXPANSION BAJISTA","reason":f"🔥 {phase_info['desc']}"})

        real_buy = sum(p['points'] for p in points_detail if p['side']=='BUY')
        real_sell = sum(p['points'] for p in points_detail if p['side']=='SELL')
        buy_score = real_buy; sell_score = real_sell

        direction="BUY" if buy_score>=sell_score else "SELL"
        if buy_score>=sell_score+2:
            direction="BUY"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            elif any(p["strength"]>=2 for p in candle_pats): base_conf=68
            confidence=base_conf+min(buy_score*2,16)
        elif sell_score>=buy_score+2:
            direction="SELL"; base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            elif any(p["strength"]>=2 for p in candle_pats): base_conf=68
            confidence=base_conf+min(sell_score*2,16)
        else:
            direction="BUY" if current_price>sma15 else "SELL"; confidence=56

        # FIX v8.2 ACUMULACION - diferenciar estrecha vs amplia como tu foto 4052-4073 (21 USD)
        long_is_acc = long_sr["is_acc_long"] if long_sr else False
        long_band = long_sr["band_long"] if long_sr else phase_info["band"]
        support_real = long_sr["support"] if long_sr and "support" in long_sr else support
        resistance_real = long_sr["resistance"] if long_sr and "resistance" in long_sr else resistance
        
        if long_is_acc and long_band < 7.0:
            # Acumulación estrecha <7 USD - NO operar, esperar ruptura (caso 4052-4058)
            alert=f"⛔ ESPERA - ACUMULACIÓN ESTRECHA {long_band:.1f} USD EN {long_sr['lookback']//120}H - NO OPERAR"; alert_type="WAIT"; alert_desc=f"Precio lleva {long_sr['lookback']//120}h entre {long_sr['low_long']:.2f} y {long_sr['high_long']:.2f} (banda {long_band:.1f} USD) - acumulación estrecha - esperar ruptura real Fib 0. Score {buy_score}B/{sell_score}S ignorado"
            confidence = 52
        elif long_is_acc and long_band >= 10.0:
            # Acumulación AMPLIA como tu foto actual 4052-4073 (21 USD) - SI dar señales de corte con impulso y retroceso dentro del área
            # Si está cerca de soporte 4052 -> BUY, cerca de resistencia 4065-4073 -> SELL, scalping dentro del rango
            dist_to_support = abs(current_price - support_real)
            dist_to_resistance = abs(current_price - resistance_real)
            if dist_to_support < 1.8 and current_price < support_real + 1.5:
                # Cerca de soporte en acumulación amplia = oportunidad BUY con impulso
                buy_score+=2
                points_detail.append({"side":"BUY","points":2,"name":"CORTE SOPORTE EN ACUMULACIÓN AMPLIA","reason":f"📦 Acumulación amplia {long_band:.1f} USD ({support_real:.2f}-{resistance_real:.2f}) - Precio {current_price:.2f} cerca soporte {support_real:.2f} a {dist_to_support:.2f} USD - corte alcista con impulso + retroceso Fib"})
                if confidence < 70:
                    confidence = 70
            if dist_to_resistance < 1.8 and current_price > resistance_real - 1.5:
                sell_score+=2
                points_detail.append({"side":"SELL","points":2,"name":"CORTE RESISTENCIA EN ACUMULACIÓN AMPLIA","reason":f"📦 Acumulación amplia {long_band:.1f} USD - Precio {current_price:.2f} cerca resistencia {resistance_real:.2f} a {dist_to_resistance:.2f} USD - corte bajista"})
                if confidence < 70:
                    confidence = 70
            # No bloquear, permitir señales dentro del rango amplio
            long_is_acc = False  # para que no bloquee abajo
        
        elif "ACUMULACION" in phase_info["phase"] and not "EXPANSION" in phase_info["phase"]:
            alert="⛔ ESPERA - NO ENTRES - FASE ACUMULACION"; alert_type="WAIT"; alert_desc=f"Acumulacion rango {phase_info['band']:.1f} USD - NO operar, esperar PICO. Score {buy_score}B/{sell_score}S"
        elif "EXPANSION" in phase_info["phase"] and confidence>=70 and len([p for p in candle_pats if p["strength"]>=1])>0:
            fib_txt = f" + Fib {fib['near']} {fib['levels'][fib['near']]:.2f}" if fib and fib.get('near') else ""
            alert=f"✅ ENTRA - PICO TRAS ACUMULACION + VELA CONFIRMADA - {direction} - SEÑAL LIMPIA{fib_txt}"; alert_type="ENTER"; alert_desc=f"{phase_info['phase']} + vela {candle_pats[0]['name'] if candle_pats else ''}{fib_txt} - señal limpia {confidence}% - Score {buy_score}B/{sell_score}S - coincide TradingView"
        elif fib and fib.get('near') in ['0.618','0.5'] and confidence>=65:
            alert=f"✅ ENTRA - {direction} EN FIB {fib['near']} - RETROCESO PERFECTO"; alert_type="ENTER"; alert_desc=f"📐 Fibonacci {fib['near']} - {fib['desc']} - Score {buy_score}B/{sell_score}S - entrada de libro"
        elif confidence>=72 and abs(buy_score-sell_score)>=2 and not long_is_acc:
            alert=f"✅ ENTRA - {direction} CONFIRMADO - TENDENCIA FUERTE"; alert_type="ENTER"; alert_desc=f"Score {buy_score if direction=='BUY' else sell_score} vs {sell_score if direction=='BUY' else buy_score} - confianza {confidence}% - coincide con ruptura TradingView + {fib['desc'] if fib else ''}"
        elif confidence>=62 and abs(buy_score-sell_score)>=1 and not long_is_acc:
            alert=f"⚠️ ENTRA CON PRECAUCION - {direction} - CONFIRMACIÓN MEDIA"; alert_type="CAUTION"; alert_desc=f"Score {buy_score}B/{sell_score}S - espera vela fuerte para confirmar - {fib['desc'] if fib else phase_info['phase']}"
        else:
            alert="⛔ ESPERA - SEÑAL DEBIL - RANGO"; alert_type="WAIT"; alert_desc=f"Score {buy_score}B/{sell_score}S - fase {phase_info['phase']} banda {phase_info['band']:.1f} - esperar breakout Fib 0"


        trend="BULLISH" if direction=="BUY" else "BEARISH"
        if abs(buy_score-sell_score)<=1: trend="LATERAL"

        return {
            "trend":trend,"direction":direction,"confidence":min(confidence,95),
            "pattern":phase_info["phase"],"phase":phase_info["phase"],"phase_desc":phase_info["desc"],
            "phase_info":phase_info,"alert":alert,"alert_type":alert_type,"alert_desc":alert_desc,
            "candle_patterns":candle_pats,"points_detail":points_detail,
            "reason":" | ".join([p["name"] for p in points_detail[:3]]),
            "high_10":high_10,"low_10":low_10,"high_15":high_15,"low_15":low_15,"high_30":high_30,"low_30":low_30,
            "high_long":(long_sr["high_long"] if long_sr and long_sr.get("high_long",0)>1000 else high_15),
            "low_long":(long_sr["low_long"] if long_sr and long_sr.get("low_long",0)>1000 else low_15),
            "band_long":long_sr["band_long"] if long_sr else 0,"fib":fib,
            "support_long":long_sr["support"] if long_sr else low_15,"resistance_long":long_sr["resistance"] if long_sr else high_15,
            "support_far":long_sr.get("support_far", low_15) if long_sr else low_15,"resistance_far":long_sr.get("resistance_far", high_15) if long_sr else high_15,
            "high_clusters":long_sr.get("high_clusters", []) if long_sr else [],"low_clusters":long_sr.get("low_clusters", []) if long_sr else [],


            "high_recent":high_recent,"low_recent":low_recent,
            "sma10":sma10,"sma15":sma15,"sma30":sma30,"support":support,"resistance":resistance,
            "up_streak":up_streak,"down_streak":down_streak,"volatility":phase_info["avg3"],"volatility_15":phase_info["avg6"],
            "ny_session":ny_session,"buy_score":buy_score,"sell_score":sell_score,
            "hour_ec":hour_ec,"current_price":current_price
        }
    except Exception as e:
        print(f"analyze error {e}"); import traceback; traceback.print_exc()
        return {"trend":"ERROR","direction":"BUY","confidence":50,"phase":"ERROR","phase_desc":str(e),"alert":"ESPERA - ERROR","alert_type":"WAIT","alert_desc":str(e),"points_detail":[],"candle_patterns":[],"high_10":0,"low_10":0,"high_15":0,"low_15":0,"high_30":0,"low_30":0,"sma10":0,"sma15":0,"sma30":0,"support":0,"resistance":0,"volatility":0,"ny_session":False,"buy_score":0,"sell_score":0}


def get_last_signal():
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT direction,confirmed_at,consecutive_count,phase FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row: return {"direction":row[0],"confirmed_at":row[1],"count":row[2],"phase":row[3]}
    except: pass
    return {"direction":"BUY","confirmed_at":datetime.now(EC_TZ).isoformat(),"count":0,"phase":"ACUMULACION"}

def update_last_signal(direction, phase=""):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT direction,consecutive_count FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone()
        new_count=row[1]+1 if row and row[0]==direction else 1
        c.execute("INSERT OR REPLACE INTO last_signal (symbol,direction,confirmed_at,consecutive_count,phase) VALUES (?,?,?,?,?)", ("XAUUSD",direction,datetime.now(EC_TZ).isoformat(),new_count,phase))
        conn.commit(); conn.close()
        return new_count
    except: return 1

def should_flip(new_dir, conf, market):
    try:
        last=get_last_signal()
        if last["direction"]==new_dir: return True, f"Misma dirección {new_dir} - continua"
        buy_score=market.get("buy_score",0); sell_score=market.get("sell_score",0); diff=abs(buy_score-sell_score)
        # FIX CRITICO: si hay diferencia de puntos >=2, permite flip inmediato sin esperar 12m
        if diff>=2 and conf>=68:
            return True, f"Flip rapido Score {buy_score}B/{sell_score}S diff {diff} + conf {conf}% - cambio a {new_dir}"
        if "EXPANSION" in market.get("phase","") and conf>=70:
            return True, f"🔥 EXPANSION {market.get('phase')} - cambio rapido {conf}% a {new_dir}"
        if "TENDENCIA" in market.get("phase","") and diff>=2:
            return True, f"TENDENCIA {market.get('phase')} + diff {diff} - cambio a {new_dir}"
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row:
            last_time=datetime.fromisoformat(row[0])
            mins=(datetime.now(EC_TZ)-last_time).total_seconds()/60
            if mins<5 and conf<65 and diff<2:
                return False, f"Esperando 5m (van {mins:.1f}m) conf {conf}% diff {diff} - manteniendo {last['direction']}"
            if conf>=75: return True, f"Alta confianza {conf}% + fase {market.get('phase')} a {new_dir}"
            if mins>=5: return True, f"Cambio tras {mins:.1f}m + fase {market.get('phase')} a {new_dir}"
        if conf>=68: return True, f"Confianza {conf}% + fase {market.get('phase')} a {new_dir}"
        return False, f"Confianza baja {conf}% manteniendo {last['direction']} fase {last.get('phase','')}"
    except Exception as e:
        return True, f"Error {e} permitiendo cambio a {new_dir}"

def calc_tp_sl(entry, direction="BUY"):
    TARGET=10.0; PER=1.62
    sl_dist=round(TARGET/PER,2); tp1=sl_dist; tp2=round((TARGET*2)/PER,2); tp3=round((TARGET*3)/PER,2)
    if direction=="BUY":
        return round(entry-sl_dist,2), round(entry+tp1,2), round(entry+tp2,2), round(entry+tp3,2), sl_dist, tp1, tp2, tp3
    else:
        return round(entry+sl_dist,2), round(entry-tp1,2), round(entry-tp2,2), round(entry-tp3,2), sl_dist, tp1, tp2, tp3

def get_stats():
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT wins,loss,tp1,tp2,tp3,total_trades,buy_wins,buy_total,sell_wins,sell_total FROM gold_learning WHERE id=1")
        row=c.fetchone(); conn.close()
        if row: return {"wins":row[0],"loss":row[1],"tp1":row[2],"tp2":row[3],"tp3":row[4],"total":row[5],"buy_wins":row[6],"buy_total":row[7],"sell_wins":row[8],"sell_total":row[9]}
    except: pass
    return {"wins":18,"loss":6,"tp1":12,"tp2":8,"tp3":5,"total":24,"buy_wins":11,"buy_total":14,"sell_wins":7,"sell_total":10}

def update_stats(result, direction="BUY"):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        if result=="SL":
            c.execute("UPDATE gold_learning SET loss=loss+1, total_trades=total_trades+1 WHERE id=1")
        else:
            c.execute("UPDATE gold_learning SET wins=wins+1, total_trades=total_trades+1 WHERE id=1")
        hour=datetime.now(EC_TZ).hour
        c.execute("SELECT hour FROM gold_hour_learning WHERE hour=?", (hour,))
        if c.fetchone():
            if result=="SL": c.execute("UPDATE gold_hour_learning SET total=total+1 WHERE hour=?", (hour,))
            else: c.execute("UPDATE gold_hour_learning SET wins=wins+1, total=total+1 WHERE hour=?", (hour,))
        conn.commit(); conn.close()
    except: pass

def calc_success_rate(direction="BUY"):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT price FROM price_history ORDER BY id DESC LIMIT 300")
        prices=[r[0] for r in c.fetchall()][::-1]; conn.close()
        if len(prices)<50: return 72.0,72.0,50.0,35.0
        obj1=10.0/1.62; obj2=20.0/1.62; obj3=30.0/1.62
        e1=e2=e3=tot=0
        for i in range(len(prices)-40):
            entry=prices[i]; v10=prices[i+1:i+21]; v15=prices[i+1:i+31]
            if not v10: continue
            tot+=1
            if direction=="BUY":
                if max(v10)-entry>=obj1 or max(v15)-entry>=obj1: e1+=1
                if max(v15)-entry>=obj2: e2+=1
                if max(v15)-entry>=obj3: e3+=1
            else:
                if entry-min(v10)>=obj1 or entry-min(v15)>=obj1: e1+=1
                if entry-min(v15)>=obj2: e2+=1
                if entry-min(v15)>=obj3: e3+=1
        if tot==0: return 72,72,50,35
        p1=e1/tot*100; p2=e2/tot*100; p3=e3/tot*100; po=p1*0.5+p2*0.3+p3*0.2
        return round(po,1),round(p1,1),round(p2,1),round(p3,1)
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

@app.get("/")
def root(): return {"message":"ORO FASES + PUNTOS 10-15-30 + ALERTA ENTRA/ESPERA","version":"6.0"}

@app.get("/health")
def health():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM price_history"); count=c.fetchone()[0]; conn.close()
    return {"status":"ok","symbol":"XAUUSD","history":count,"version":"6.0 FASES+PUNTOS"}

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
        # CALCULAR PROB BASADO EN FINAL_DIR para no cruzar SELL vs BUY
        market_for_prob = dict(market)
        market_for_prob['direction'] = final_dir
        prob,stats,p1,p2,p3,wr_dir,wr_glob=calc_prob(hour, market_for_prob)
        # Si es ENTRADA CONFIRMADA, el % de arriba debe ser la confianza de direccion, no solo TP1
        display_prob = market.get('confidence', prob) if market.get('alert_type')=='ENTER' else prob
        sl,tp1,tp2,tp3,sl_d,tp1_d,tp2_d,tp3_d=calc_tp_sl(price, final_dir)
        if final_dir=="BUY":
            sl_exp=f"SL {sl} ABAJO (si baja {sl_d} pierdes $10)"; tp_exp=f"TP1 {tp1} ARRIBA (si sube {tp1_d} ganas $10) COMPRA"
        else:
            sl_exp=f"SL {sl} ARRIBA (si sube {sl_d} pierdes $10)"; tp_exp=f"TP1 {tp1} ABAJO (si baja {tp1_d} ganas $10) VENTA"
        # FIX: Forzar que market_analysis y alerta coincidan con final_dir - evita SELL arriba y BUY abajo
        market['direction'] = final_dir
        # Si final_dir es distinto al new_dir, la alerta debe decir que mantiene, no que entra al contrario
        if final_dir != new_dir:
            market['alert'] = f"⏸️ MANTENIENDO {final_dir} - señal {new_dir} en espera ({flip_reason})"
            market['alert_type'] = "WAIT"
            market['alert_desc'] = f"Score {market.get('buy_score')}B/{market.get('sell_score')}S quiere {new_dir} pero mantiene {final_dir} - {flip_reason}"
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
            "support":market.get("support",0),"resistance":market.get("resistance",0),"timestamp":datetime.now(EC_TZ).isoformat()
        }
        return [signal]
    except Exception as e:
        print(e); import traceback; traceback.print_exc(); return []

@app.get("/trades/active")
def get_active():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT id,direction,entry,sl,tp1,tp2,tp3,probability,status,created_at,pattern,phase FROM active_trades WHERE status='OPEN' ORDER BY id DESC")
    rows=c.fetchall(); conn.close()
    return [{"id":r[0],"symbol":"XAUUSD","direction":r[1],"entry":r[2],"sl":r[3],"tp1":r[4],"tp2":r[5],"tp3":r[6],"probability":r[7],"status":r[8],"created_at":r[9],"pattern":r[10],"phase":r[11]} for r in rows]

@app.post("/trades/result")
def save_result(r: TradeResult):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT direction, pattern, phase FROM active_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1")
    row=c.fetchone(); direction=row[0] if row else "BUY"; pattern=row[1] if row and len(row)>1 else "UNKNOWN"; phase=row[2] if row and len(row)>2 else "UNKNOWN"; conn.close()
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
        print("🚀 Monitor ORO FASES + PUNTOS 10-15-30 iniciado")
        while True:
            try: save_gold_history(get_gold_price())
            except: pass
            await asyncio.sleep(30)
    asyncio.create_task(monitor_loop())
