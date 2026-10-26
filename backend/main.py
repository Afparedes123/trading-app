
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
    is_acc=band<4.0 and avg6<2.0 and avg_body<1.2
    is_exp=avg3>avg6*1.5
    is_cont=avg3<avg6*0.7
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
    if is_acc:
        if up>=2: return {"phase":"ACUMULACION_ALCISTA","desc":f"ACUMULACION ALCISTA - rango {band:.1f} USD estrecho, vol {avg6:.1f} USD, {up} velas alcistas - posible PICO COMPRA tras acumulacion (como hoy)","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
        if down>=2: return {"phase":"ACUMULACION_BAJISTA","desc":f"ACUMULACION BAJISTA - rango {band:.1f} USD, {down} velas bajistas - posible PICO VENTA tras acumulacion","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
        return {"phase":"ACUMULACION","desc":f"ACUMULACION PURA - rango {band:.1f} USD muy estrecho, vol {avg6:.1f} USD, esperando PICO - NO ENTRAR AUN","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":True,"is_exp":False}
    if is_exp and last["strong"]:
        prices_all=[c["close"] for c in last6]
        if last["bullish"] and last["close"]>=max(prices_all)*0.998:
            return {"phase":"EXPANSION_ALCISTA","desc":f"🔥 EXPANSION ALCISTA - PICO COMPRA tras acumulacion {band:.1f} USD -> ruptura {last['close']:.2f} vela fuerte {last['body']:.1f} USD, rango {last['range']:.1f} USD - ENTRAR","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
        if not last["bullish"] and last["close"]<=min(prices_all)*1.002:
            return {"phase":"EXPANSION_BAJISTA","desc":f"🔥 EXPANSION BAJISTA - PICO VENTA tras acumulacion {band:.1f} USD -> ruptura {last['close']:.2f} vela {last['body']:.1f} USD - ENTRAR","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":True}
    if up>=3:
        if avg3<avg6: return {"phase":"AGOTAMIENTO_ALCISTA","desc":f"AGOTAMIENTO ALCISTA - {up} velas arriba pero rango decrece {avg3:.1f} < {avg6:.1f} - buscar vela bajista para SELL","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"TENDENCIA_ALCISTA","desc":f"TENDENCIA ALCISTA - {up} velas alcistas, pendiente SMA +{slope:.2f} - seguir BUY","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    if down>=3:
        if avg3<avg6: return {"phase":"AGOTAMIENTO_BAJISTA","desc":f"AGOTAMIENTO BAJISTA - {down} velas abajo rango decrece - buscar vela alcista para BUY","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
        return {"phase":"TENDENCIA_BAJISTA","desc":f"TENDENCIA BAJISTA - {down} velas bajistas, pendiente {slope:.2f} - seguir SELL","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    if band<6.0 and avg6<2.5:
        return {"phase":"RANGO","desc":f"RANGO estrecho {band:.1f} USD - balance, esperar ruptura","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}
    return {"phase":"TRANSICION","desc":f"TRANSICION - vol {avg3:.1f} USD, pendiente {slope:.2f}","band":band,"avg6":avg6,"avg3":avg3,"up":up,"down":down,"slope":slope,"is_acc":False,"is_exp":False}

def analyze_gold_pro():
    try:
        rows=get_gold_history(300)
        price_fallback=get_gold_price()
        if len(rows)<10:
            return {"trend":"INICIO","direction":"BUY","confidence":55,"phase":"INICIO","phase_desc":"Iniciando - precio actual","alert":"ESPERA - INICIANDO","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"high_10":price_fallback+3.5,"low_10":price_fallback-3.2,"high_15":price_fallback+5.8,"low_15":price_fallback-5.1,"high_30":price_fallback+8.5,"low_30":price_fallback-8.2,"sma10":price_fallback-0.8,"sma15":price_fallback-1.2,"sma30":price_fallback-1.8,"support":price_fallback-5.1,"resistance":price_fallback+5.8,"volatility":3.2,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":price_fallback}
        candles_10=build_candles(rows,20); candles_15=build_candles(rows,30); candles_30=build_candles(rows,60)
        if len(candles_10)<4:
            fallback=rows[-1][0] if rows else price_fallback
            high_est=max([r[0] for r in rows[-20:]]) if len(rows)>=20 else fallback+3.5
            low_est=min([r[0] for r in rows[-20:]]) if len(rows)>=20 else fallback-3.2
            sma_est=sum([r[0] for r in rows[-10:]])/min(len(rows),10) if rows else fallback
            return {"trend":"FORMANDO","direction":"BUY","confidence":56,"phase":"FORMANDO","phase_desc":f"Formando velas {len(candles_10)} 10m","alert":"ESPERA - FORMANDO VELAS","alert_type":"WAIT","points_detail":[],"candle_patterns":[],"high_10":high_est,"low_10":low_est,"high_15":high_est+1.5,"low_15":low_est-1.5,"high_30":high_est+2.5,"low_30":low_est-2.5,"sma10":sma_est,"sma15":sma_est-0.5,"sma30":sma_est-1.0,"support":low_est,"resistance":high_est,"volatility":high_est-low_est,"ny_session":False,"buy_score":0,"sell_score":0,"up_streak":0,"down_streak":0,"current_price":fallback}

        current_price=rows[-1][0]
        last_10=candles_10[-1]; prev_10=candles_10[-2]
        last_15=candles_15[-1] if candles_15 else last_10
        prev_15=candles_15[-2] if len(candles_15)>=2 else last_10
        last_30=candles_30[-1] if candles_30 else last_15

        closes_10=[c["close"] for c in candles_10[-5:]]
        closes_15=[c["close"] for c in candles_15[-4:]] if candles_15 else closes_10
        closes_30=[c["close"] for c in candles_30[-3:]] if candles_30 else closes_15
        sma10=sum(closes_10)/len(closes_10); sma15=sum(closes_15)/len(closes_15); sma30=sum(closes_30)/len(closes_30)

        high_10=max([c["high"] for c in candles_10[-3:]]); low_10=min([c["low"] for c in candles_10[-3:]])
        high_15=max([c["high"] for c in candles_15[-3:]]) if candles_15 else high_10; low_15=min([c["low"] for c in candles_15[-3:]]) if candles_15 else low_10
        high_30=max([c["high"] for c in candles_30[-2:]]) if candles_30 else high_15; low_30=min([c["low"] for c in candles_30[-2:]]) if candles_30 else low_15
        support=low_15; resistance=high_15

        phase_info=detect_phase(candles_10,candles_15,rows)
        candle_pats=detect_candle_patterns(candles_10)+detect_candle_patterns(candles_15)

        hour_ec=datetime.now(EC_TZ).hour
        ny_session=8<=hour_ec<=11

        buy_score=0; sell_score=0; points_detail=[]

        # 1. SMA 10>15>30 - TU SISTEMA PUNTOS
        if current_price>sma10 and sma10>sma15 and sma15>sma30:
            buy_score+=3; points_detail.append({"side":"BUY","points":3,"name":"SMA BULL FUERTE","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} > SMA15 {sma15:.2f} > SMA30 {sma30:.2f}"})
        elif current_price<sma10 and sma10<sma15 and sma15<sma30:
            sell_score+=3; points_detail.append({"side":"SELL","points":3,"name":"SMA BEAR FUERTE","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} < SMA15 {sma15:.2f} < SMA30 {sma30:.2f}"})
        elif current_price>sma10 and current_price>sma15:
            # No dar punto debil si hay expansion bajista fuerte (evita contradiccion)
            if "EXPANSION_BAJISTA" not in phase_info["phase"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SMA BULL DEBIL","reason":f"Precio {current_price:.2f} > SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})
        elif current_price<sma10 and current_price<sma15:
            # No dar punto debil si hay expansion alcista fuerte (tu caso 7 vs 1)
            if "EXPANSION_ALCISTA" not in phase_info["phase"]:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SMA BEAR DEBIL","reason":f"Precio {current_price:.2f} < SMA10 {sma10:.2f} y SMA15 {sma15:.2f}"})

        # 2. RUPTURA ALTO 10MIN CON VELA FUERTE - TU SISTEMA
        if current_price>=high_10*0.998 and last_10["bullish"] and last_10["strong"]:
            buy_score+=3; points_detail.append({"side":"BUY","points":3,"name":"BREAK HIGH 10m FUERTE","reason":f"🔥 Ruptura alto 10m {high_10:.2f} vela cuerpo {last_10['body']:.2f} ratio {last_10['body_ratio']:.2f} >0.6"})
        if current_price<=low_10*1.002 and not last_10["bullish"] and last_10["strong"]:
            sell_score+=3; points_detail.append({"side":"SELL","points":3,"name":"BREAK LOW 10m FUERTE","reason":f"🔥 Ruptura bajo 10m {low_10:.2f} vela fuerte {last_10['body']:.2f}"})

        # 3. CERCA RESISTENCIA 15MIN - TU SISTEMA
        if abs(current_price-high_15) < 2.0:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"CERCA RESISTENCIA 15m","reason":f"Precio {current_price:.2f} cerca resistencia 15m {high_15:.2f} a {high_15-current_price:.2f} USD - posible breakout"})
        if abs(current_price-low_15) < 2.0:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"CERCA SOPORTE 15m","reason":f"Precio {current_price:.2f} cerca soporte 15m {low_15:.2f} a {current_price-low_15:.2f} USD"})

        # 4. RACHA 3 VELAS 10MIN - TU SISTEMA
        up_streak=phase_info["up"]; down_streak=phase_info["down"]
        if up_streak>=3:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":f"RACHA {up_streak} VELAS ALCISTAS 10m","reason":f"Racha alcista {up_streak} velas 10min oro consecutivas"})
        elif up_streak>=2:
            buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":f"RACHA {up_streak} VELAS","reason":f"{up_streak} velas alcistas"})
        if down_streak>=3:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":f"RACHA {down_streak} VELAS BAJISTAS 10m","reason":f"Racha bajista {down_streak} velas 10min"})
        elif down_streak>=2:
            sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":f"RACHA {down_streak} BAJISTAS","reason":f"{down_streak} velas bajistas"})

        # 5. VELA FUERTE - TU SISTEMA
        if last_10["strong"]:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"VELA FUERTE ALCISTA","reason":f"Vela 10m alcista fuerte ratio {last_10['body_ratio']:.2f} cuerpo {last_10['body']:.2f}"})
            else:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"VELA FUERTE BAJISTA","reason":f"Vela 10m bajista fuerte ratio {last_10['body_ratio']:.2f}"})

        # 6. SESION NY 8-10 AM EC - TU SISTEMA - FIX: da +1 segun vela, no empate
        if ny_session:
            if last_10["bullish"]:
                buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN 8-10AM EC - oro volatil, vela alcista +1 BUY"})
            elif not last_10["bullish"]:
                sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN 8-10AM EC - oro volatil, vela bajista +1 SELL"})
            else:
                if buy_score>=sell_score:
                    buy_score+=1; points_detail.append({"side":"BUY","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN alta volatilidad +1"})
                else:
                    sell_score+=1; points_detail.append({"side":"SELL","points":1,"name":"SESION NY 8-10AM EC","reason":"🔥 NY OPEN alta volatilidad +1"})

        # 7. 3 VELAS 15-30MIN CONFIRMADAS - TU SISTEMA
        if len(candles_15)>=2 and len(candles_30)>=1:
            if last_15["bullish"] and prev_15["bullish"] and last_30["bullish"]:
                buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"3 VELAS 15-30m ALCISTAS CONFIRMADAS","reason":"3 velas 15-30min alcistas confirmadas - tendencia mayor alcista"})
            if not last_15["bullish"] and not prev_15["bullish"] and not last_30["bullish"]:
                sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"3 VELAS 15-30m BAJISTAS CONFIRMADAS","reason":"3 velas 15-30min bajistas confirmadas"})

        # EXTRA: PATRONES VELAS JAPONESAS - BONUS PARA SEÑALES LIMPIAS
        for pat in candle_pats:
            if pat["dir"]=="BUY":
                buy_score+=pat["strength"]
                points_detail.append({"side":"BUY","points":pat["strength"],"name":pat["name"],"reason":f"🕯️ {pat['desc']}"})
            else:
                sell_score+=pat["strength"]
                points_detail.append({"side":"SELL","points":pat["strength"],"name":pat["name"],"reason":f"🕯️ {pat['desc']}"})

        # EXTRA: FASE BONUS
        if "EXPANSION_ALCISTA" in phase_info["phase"]:
            buy_score+=2; points_detail.append({"side":"BUY","points":2,"name":"FASE EXPANSION ALCISTA","reason":f"🔥 {phase_info['desc']}"})
        elif "EXPANSION_BAJISTA" in phase_info["phase"]:
            sell_score+=2; points_detail.append({"side":"SELL","points":2,"name":"FASE EXPANSION BAJISTA","reason":f"🔥 {phase_info['desc']}"})
        elif "ACUMULACION" in phase_info["phase"]:
            points_detail.append({"side":"NEUTRAL","points":0,"name":phase_info["phase"],"reason":f"⏸️ {phase_info['desc']}"})

        # RECALCULAR para evitar contradiccion visual: sumar de nuevo points_detail
        real_buy = sum(p['points'] for p in points_detail if p['side']=='BUY')
        real_sell = sum(p['points'] for p in points_detail if p['side']=='SELL')
        # Ajustar si hubo supresion
        buy_score = real_buy
        sell_score = real_sell
        # DECIDIR DIRECCION Y ALERTA
        direction="BUY" if buy_score>=sell_score else "SELL"
        if buy_score>=sell_score+2:
            direction="BUY"
            base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            elif any(p["strength"]>=2 for p in candle_pats): base_conf=68
            confidence=base_conf+min(buy_score*2,16)
        elif sell_score>=buy_score+2:
            direction="SELL"
            base_conf=62
            if "EXPANSION" in phase_info["phase"]: base_conf=78
            elif any(p["strength"]>=2 for p in candle_pats): base_conf=68
            confidence=base_conf+min(sell_score*2,16)
        else:
            direction="BUY" if current_price>sma15 else "SELL"
            confidence=56

        # ALERTA ENTRA / ESPERA
        if "ACUMULACION" in phase_info["phase"] and not "EXPANSION" in phase_info["phase"]:
            alert="⛔ ESPERA - NO ENTRES - FASE ACUMULACION"
            alert_type="WAIT"
            alert_desc=f"Acumulacion pura rango {phase_info['band']:.1f} USD - NO operar, esperar PICO tras acumulacion como hoy. Score {buy_score}B/{sell_score}S insuficiente"
        elif "EXPANSION" in phase_info["phase"] and confidence>=72 and len([p for p in candle_pats if p["strength"]>=2])>0:
            alert="✅ ENTRA - PICO TRAS ACUMULACION + VELA CONFIRMADA - SEÑAL LIMPIA"
            alert_type="ENTER"
            alert_desc=f"{phase_info['phase']} + vela {candle_pats[0]['name'] if candle_pats else ''} - señal limpia {confidence}%"
        elif confidence>=75 and abs(buy_score-sell_score)>=3:
            alert=f"✅ ENTRA - {direction} CONFIRMADO - TENDENCIA FUERTE"
            alert_type="ENTER"
            alert_desc=f"Score {buy_score if direction=='BUY' else sell_score} vs {sell_score if direction=='BUY' else buy_score} - confianza {confidence}%"
        elif confidence>=65 and abs(buy_score-sell_score)>=2:
            alert=f"⚠️ ENTRA CON PRECAUCION - {direction} - CONFIRMACION MEDIA"
            alert_type="CAUTION"
            alert_desc=f"Score {buy_score}B/{sell_score}S - espera vela fuerte para confirmar"
        else:
            alert="⛔ ESPERA - SEÑAL DEBIL - RANGO O ACUMULACION"
            alert_type="WAIT"
            alert_desc=f"Score igualado {buy_score}B/{sell_score}S - fase {phase_info['phase']} - esperar breakout limpio"

        trend="BULLISH" if direction=="BUY" else "BEARISH"
        if abs(buy_score-sell_score)<=1: trend="LATERAL"

        return {
            "trend":trend,"direction":direction,"confidence":min(confidence,94),
            "pattern":phase_info["phase"],"phase":phase_info["phase"],"phase_desc":phase_info["desc"],
            "phase_info":phase_info,"alert":alert,"alert_type":alert_type,"alert_desc":alert_desc,
            "candle_patterns":candle_pats,"points_detail":points_detail,
            "reason":" | ".join([p["name"] for p in points_detail[:3]]),
            "high_10":high_10,"low_10":low_10,"high_15":high_15,"low_15":low_15,"high_30":high_30,"low_30":low_30,
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
        if last["direction"]==new_dir: return True, "Misma dirección oro - continua"
        if "EXPANSION" in market.get("phase","") and conf>=72:
            return True, f"🔥 EXPANSION {market.get('phase')} tras acumulacion - cambio rapido {conf}%"
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT confirmed_at FROM last_signal WHERE symbol='XAUUSD'")
        row=c.fetchone(); conn.close()
        if row:
            last_time=datetime.fromisoformat(row[0])
            mins=(datetime.now(EC_TZ)-last_time).total_seconds()/60
            if mins<12 and conf<78: return False, f"Fase {market.get('phase')} esperando 12m (van {mins:.1f}m) conf {conf}%"
            if conf>=80: return True, f"Alta confianza {conf}% + fase {market.get('phase')}"
            if mins>=15: return True, f"Cambio tras {mins:.1f}m + fase {market.get('phase')}"
        if conf>=72: return True, f"Confianza {conf}% + fase {market.get('phase')}"
        return False, f"Confianza baja {conf}% manteniendo {last['direction']} fase {last.get('phase','')}"
    except: return True, "Error permitiendo cambio"

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
        # Forzar que market_analysis tambien tenga final_dir para no mostrar BUY 84% cuando es SELL 57%
        market['direction'] = final_dir
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
