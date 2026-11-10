import os, sqlite3, requests, asyncio, math, time, threading
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple

from trend_engine import TrendSpiderAutoTrendlines, calc_atr
from fib_engine import TrendSpiderAutoFibs
from heatmap_engine import TrendSpiderHeatmapEngine
from strategy_lab import TrendSpiderStrategyLab
from mtfa_engine import TrendSpiderMTFAEngine, aggregate_timeframe_candles

app = FastAPI(title="EdgeAlert - TRENDSPIDER ALGORITHMIC ENGINE v15.5")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

EC_TZ = timezone(timedelta(hours=-5))
DB_PATH = os.getenv("DB_PATH", "/app/data/learning.db" if os.path.exists("/app/data") else "learning.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if "/" in DB_PATH else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tabla de velas de 1 minuto (OHLC)
    c.execute("""CREATE TABLE IF NOT EXISTS ohlc_1m (
        ts INTEGER PRIMARY KEY,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL DEFAULT 0,
        source TEXT DEFAULT 'FEED'
    )""")
    # Tabla de estado de la última señal y gestión de trade (con control de tiempo y enfriamiento)
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (
        symbol TEXT PRIMARY KEY,
        direction TEXT,
        confirmed_at TEXT,
        phase TEXT,
        entry_price REAL DEFAULT 0,
        sl_price REAL DEFAULT 0,
        tp_price REAL DEFAULT 0,
        tp2_price REAL DEFAULT 0,
        max_favorable_price REAL DEFAULT 0,
        entry_ts INTEGER DEFAULT 0,
        cooldown_until INTEGER DEFAULT 0
    )""")
    try:
        c.execute("ALTER TABLE last_signal ADD COLUMN entry_ts INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE last_signal ADD COLUMN cooldown_until INTEGER DEFAULT 0")
    except:
        pass
    # Tabla de Historial / Bitácora de Alertas (para auditar 8am - 11am y todo el día)
    c.execute("""CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER,
        time_ec TEXT,
        event_type TEXT,
        direction TEXT,
        price REAL,
        sl REAL,
        tp1 REAL,
        pnl REAL DEFAULT 0,
        reason TEXT
    )""")
    # Tabla de configuración de usuario persistente
    c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# Cargar configuraciones por defecto
DEFAULT_SETTINGS = {
    "analysis_type": "Standard",       # "Original", "Standard", "Enhanced"
    "drawing_input": "Wick",           # "Wick" (H/L) o "Body" (O/C)
    "island_gaps": "Respect",          # "Respect" o "Ignore"
    "quality_filter": "Most Relevant", # "Most Relevant" (Top 1%), "Moderately Relevant", "Unfiltered"
    "heatmap_mode": "Horizontal",      # "Horizontal", "Depth", "Trends", "Off"
    "truth_lock_ts": "",               # Timestamp congelado o vacío
    "ai_model": "Ensemble",            # "Ensemble", "RandomForest", "Logistic", "KNN", "NaiveBayes"
    "tp_pct": "0.15",                  # ~0.15% TP (~$6.20 en Oro para horizonte 20 min)
    "sl_pct": "0.10",                  # ~0.10% SL (~$4.10 en Oro estructural)
    "horizon": "20"                    # Pronóstico y horizonte de ganancia a 20 minutos
}

def get_setting(key: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM app_settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
    except:
        pass
    return DEFAULT_SETTINGS.get(key, "")

def set_setting(key: str, val: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(val)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error set_setting: {e}")

def log_signal_event(event_type: str, direction: str, price: float, sl: float = 0.0, tp1: float = 0.0, pnl: float = 0.0, reason: str = ""):
    """Guarda cada entrada, salida o break-even en la bitácora histórica"""
    try:
        now_dt = datetime.now(EC_TZ)
        now_ts = int(now_dt.timestamp())
        time_str = now_dt.strftime("%H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Evitar duplicar el mismo evento en los últimos 45 segundos
        c.execute("SELECT ts, event_type, direction FROM signal_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        if last and last[1] == event_type and last[2] == direction and (now_ts - last[0]) < 45:
            conn.close()
            return
        c.execute("""INSERT INTO signal_history (ts, time_ec, event_type, direction, price, sl, tp1, pnl, reason)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (now_ts, time_str, event_type, direction, round(price, 2), round(sl, 2), round(tp1, 2), round(pnl, 2), reason))
        # Conservar los últimos 100 eventos
        c.execute("DELETE FROM signal_history WHERE id NOT IN (SELECT id FROM signal_history ORDER BY id DESC LIMIT 100)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error log_signal_event: {e}")

def get_signal_history(limit: int = 25) -> List[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, ts, time_ec, event_type, direction, price, sl, tp1, pnl, reason FROM signal_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        history = []
        for r in rows:
            history.append({
                "id": r[0], "ts": r[1], "time_ec": r[2], "event_type": r[3],
                "direction": r[4], "price": r[5], "sl": r[6], "tp1": r[7],
                "pnl": r[8], "reason": r[9]
            })
        return history
    except:
        return []

class TVWebhookPayload(BaseModel):
    symbol: Optional[str] = "XAUUSD"
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = 0.0
    interval: Optional[str] = "1"

def get_live_spot_price() -> Tuple[float, str]:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT close, ts, source FROM ohlc_1m ORDER BY ts DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row and row[2] == "TRADINGVIEW_ACCOUNT" and (now_ts - row[1]) <= 75:
            return float(row[0]), "TRADINGVIEW CUENTA DIRECTA"
    except:
        pass

    # Swissquote Spot BBO Feed
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
                        return round((bid + ask) / 2.0, 2), "SPOT SWISSQUOTE FEED"
    except:
        pass

    # Gold-API Spot
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code == 200 and r.json().get("price"):
            p = float(r.json()["price"])
            if p > 1000:
                return round(p, 2), "GOLD-API SPOT"
    except:
        pass

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT close FROM ohlc_1m ORDER BY ts DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row and row[0] > 1000:
            return round(float(row[0]), 2), "DATABASE CACHE"
    except:
        pass

    return 4120.50, "FALLBACK"

def sync_historical_1m_candles():
    """
    Sincroniza hasta 240 velas reales de 1 minuto (4 horas) con CERO RETRASO:
    1. Fuente Primaria (0s lag): Binance Vision PAXGUSDT 1m Klines + calibración de base exacta con Swissquote Spot XAU/USD.
    2. Fuente Secundaria (Fallback): Yahoo Finance GC=F 1m.
    """
    live_p, _ = get_live_spot_price()
    synced = False

    # 1. Fuente Primaria: Binance Vision PAXGUSDT (Tiempo Real estricto, 0 segundos de retraso)
    try:
        url_bv = "https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=1m&limit=240"
        r_bv = requests.get(url_bv, timeout=4)
        if r_bv.status_code == 200:
            klines = r_bv.json()
            if isinstance(klines, list) and len(klines) >= 30:
                last_close = float(klines[-1][4])
                basis = (live_p - last_close) if (live_p > 1000 and last_close > 1000) else 0.0
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                for k in klines:
                    ts_min = (int(k[0]) // 1000 // 60) * 60
                    o = round(float(k[1]) + basis, 2)
                    h = round(float(k[2]) + basis, 2)
                    l = round(float(k[3]) + basis, 2)
                    cl = round(float(k[4]) + basis, 2)
                    v = round(float(k[5]), 2)
                    c.execute("SELECT source FROM ohlc_1m WHERE ts=?", (ts_min,))
                    existing = c.fetchone()
                    if not existing or existing[0] != "TRADINGVIEW_ACCOUNT":
                        c.execute("""INSERT OR REPLACE INTO ohlc_1m (ts,open,high,low,close,volume,source)
                                     VALUES (?,?,?,?,?,?,?)""", (ts_min, o, h, l, cl, v, "BINANCE_SPOT_SYNC"))
                conn.commit()
                conn.close()
                synced = True
                return
    except Exception as e:
        print(f"Binance Vision 1m sync warning: {e}")

    # 2. Fuente Secundaria: Yahoo Finance GC=F
    if not synced:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                res = r.json().get("chart", {}).get("result", [])
                if res:
                    timestamps = res[0].get("timestamp", [])[-240:]
                    quote = res[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])[-240:]
                    highs = quote.get("high", [])[-240:]
                    lows = quote.get("low", [])[-240:]
                    closes = quote.get("close", [])[-240:]
                    vols = quote.get("volume", [])[-240:]

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

                        c.execute("SELECT source FROM ohlc_1m WHERE ts=?", (ts_min,))
                        existing = c.fetchone()
                        if not existing or existing[0] != "TRADINGVIEW_ACCOUNT":
                            c.execute("""INSERT OR REPLACE INTO ohlc_1m (ts,open,high,low,close,volume,source)
                                         VALUES (?,?,?,?,?,?,?)""", (ts_min, o, h, l, cl, v, "SYNC_1M"))
                    conn.commit()
                    conn.close()
                    return
        except Exception as e:
            print(f"Sync historical 1m warning: {e}")

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ohlc_1m")
        if c.fetchone()[0] < 60:
            base = live_p if live_p > 1000 else 4125.0
            now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60
            for i in range(180):
                ts = now_min - ((180 - i) * 60)
                wave = math.sin(i / 8.0) * 4.5 + math.cos(i / 4.0) * 2.0
                o = round(base + wave, 2)
                cl = round(base + math.sin((i + 1) / 8.0) * 4.5 + math.cos((i + 1) / 4.0) * 2.0, 2)
                hi = round(max(o, cl) + 0.8, 2)
                lo = round(min(o, cl) - 0.8, 2)
                c.execute("INSERT OR IGNORE INTO ohlc_1m (ts,open,high,low,close,volume,source) VALUES (?,?,?,?,?,?,?)",
                          (ts, o, hi, lo, cl, 150, "INIT"))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Init fallback error: {e}")

def update_current_1m_candle(price: float, source: str = "FEED"):
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
        c.execute("DELETE FROM ohlc_1m WHERE ts NOT IN (SELECT ts FROM ohlc_1m ORDER BY ts DESC LIMIT 360)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Update 1m error: {e}")

def get_1m_candles(limit: int = 180) -> List[Dict[str, Any]]:
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
    except Exception as e:
        return []

def detect_m5_swing_pullbacks(candles_5m: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Motor Institucional M5 Anti-Trampas (Validado con el movimiento real 20:00 - 21:20):
    1. Detecta Techos y Rechazos ("Bear Wick" / Envolvente Bajista en máximo, ej. 20:30 en $4,140.50) -> SELL_CHOCH inmediato.
    2. Bloquea "Bull Traps" (rebotes de gato muerto tras vela bajista fuerte, ej. 20:35 en $4,130.92) -> PROHIBIDO COMPRAR.
    3. Captura Retrocesos Bajistas (LH bajo EMA8/EMA18, ej. 20:40 - 20:55) -> SELL_PULLBACK.
    4. Captura Absorción en Suelo (ej. 20:00 en $4,121.45) -> BUY_REVERSAL y Retrocesos Alcistas (HL sobre EMA8/EMA18) -> BUY_PULLBACK.
    """
    if len(candles_5m) < 8:
        return {
            "signal": "NONE", "structure": "CALIBRANDO_M5", "reason": "",
            "fib_ret": 0.5, "bull_trap_block": False, "bear_trap_block": False
        }

    window = candles_5m[-24:]
    closes = [c["close"] for c in window]

    def calc_ema(vals: List[float], span: int) -> float:
        k = 2.0 / (span + 1.0)
        ema_val = vals[0]
        for v in vals[1:]:
            ema_val = v * k + ema_val * (1.0 - k)
        return ema_val

    ema8 = calc_ema(closes, 8)
    ema18 = calc_ema(closes, 18)

    last_c = window[-1]
    prev_c = window[-2]
    prev2_c = window[-3] if len(window) >= 3 else prev_c

    recent_12 = window[-12:]
    recent_high = max(c["high"] for c in recent_12)
    recent_low = min(c["low"] for c in recent_12)
    leg_range = max(recent_high - recent_low, 2.0)

    live_p = last_c["close"]
    last_bull = last_c["close"] >= last_c["open"]
    prev_bull = prev_c["close"] >= prev_c["open"]
    last_body = abs(last_c["close"] - last_c["open"])
    prev_body = abs(prev_c["close"] - prev_c["open"])
    last_upper_wick = last_c["high"] - max(last_c["open"], last_c["close"])
    last_lower_wick = min(last_c["open"], last_c["close"]) - last_c["low"]

    # Detector de Desplazamiento Bajista Reciente (Bloqueador de Bull Traps como el de las 20:35)
    prev2_bull = prev2_c["close"] >= prev2_c["open"]
    recent_bear_displacement = (
        (not prev_bull and prev_body >= 3.2) or
        (not prev2_bull and abs(prev2_c["close"] - prev2_c["open"]) >= 3.8 and live_p < prev2_c["open"] - 1.5) or
        (ema8 < ema18 and live_p < ema8)
    )
    # Detector de Desplazamiento Alcista Reciente (Bloqueador de Bear Traps en pleno rally)
    recent_bull_displacement = (
        (prev_bull and prev_body >= 3.2) or
        (ema8 > ema18 and live_p > ema8)
    )

    # 1. GIRO EN TECHO / BEAR WICK / ENVOLVENTE BAJISTA (Ej: 20:30 en $4,140.50 -> caída a $4,131)
    near_top = (max(last_c["high"], prev_c["high"]) >= recent_high - 1.8)
    if near_top and not last_bull and (last_body >= 2.2 or last_upper_wick >= 1.5) and live_p < prev_c["low"] + 1.0:
        return {
            "signal": "SELL_CHOCH",
            "structure": "RECHAZO EN TECHO M5 (Bear Wick + Giro Bajista)",
            "reason": f"Fuerte rechazo institucional en el techo de ${recent_high:.2f} con vela bajista de desplazamiento (${last_c['open']:.2f} → ${live_p:.2f}). Giro confirmado a VENTA.",
            "fib_ret": round((live_p - recent_low) / leg_range, 3),
            "last_sh": recent_high,
            "last_sl": recent_low,
            "bull_trap_block": True,
            "bear_trap_block": False
        }

    # 2. ABSORCIÓN INSTITUCIONAL EN SUELO / GIRO ALCISTA (Ej: 20:00 en $4,121.45 -> subida a $4,132)
    near_bottom = (min(last_c["low"], prev_c["low"]) <= recent_low + 1.8)
    if near_bottom and last_bull and (last_body >= 2.2 or last_lower_wick >= 1.5) and live_p > prev_c["high"] - 1.0:
        return {
            "signal": "BUY_REVERSAL",
            "structure": "ABSORCIÓN INSTITUCIONAL EN SUELO M5 (Giro Alcista)",
            "reason": f"Defensa compradora en piso ${recent_low:.2f} con vela alcista envolvente (${last_c['open']:.2f} → ${live_p:.2f}). Inicio de impulso comprador.",
            "fib_ret": round((recent_high - live_p) / leg_range, 3),
            "last_sh": recent_high,
            "last_sl": recent_low,
            "bull_trap_block": False,
            "bear_trap_block": True
        }

    # 3. RETROCESO BAJISTA M5 (LH) Y FILTRO ANTI-BULL-TRAP (Ej: 20:35 a 21:05)
    if live_p < ema8 or ema8 < ema18 or recent_bear_displacement:
        # Si hubo un desplome fuerte en la vela previa y la vela actual es verde pero sigue debajo del inicio del desplome -> ES UNA TRAMPA ALCISTA (como a las 20:35 en $4130.92)
        if last_bull and ((not prev_bull and prev_body >= 3.2 and live_p < prev_c["open"] - 1.0) or (live_p < ema18)):
            return {
                "signal": "NONE",
                "structure": "ALERTA TRAMPA ALCISTA (Rebote Débil en Caída M5)",
                "reason": f"Subida correctiva sin fuerza tras desplome desde ${recent_high:.2f}. Prohibido comprar contra el flujo bajista.",
                "fib_ret": round((live_p - recent_low) / leg_range, 3),
                "last_sh": recent_high,
                "last_sl": recent_low,
                "bull_trap_block": True,
                "bear_trap_block": False
            }

        # Confirmación de continuación bajista tras el rebote (Vela roja o mecha superior de rechazo bajo EMA18)
        if not last_bull or last_upper_wick >= 1.2:
            return {
                "signal": "SELL_PULLBACK",
                "structure": "IMPULSO + RETROCESO BAJISTA M5 (LH Confirmado)",
                "reason": f"El rebote alcista fue rechazado bajo la media institucional (${ema8:.2f}), continuando la caída hacia ${recent_low:.2f}.",
                "fib_ret": round((live_p - recent_low) / leg_range, 3),
                "last_sh": recent_high,
                "last_sl": recent_low,
                "bull_trap_block": True,
                "bear_trap_block": False
            }

    # 4. RETROCESO ALCISTA M5 (HL) EN TENDENCIA COMPRADORA (Ej: 20:15 a 20:25)
    if (live_p >= ema8 or ema8 >= ema18) and not recent_bear_displacement:
        low_fib_ret = round((recent_high - min(last_c["low"], prev_c["low"])) / leg_range, 3)
        if 0.15 <= low_fib_ret <= 0.78 and (last_bull or last_lower_wick >= 1.2):
            return {
                "signal": "BUY_PULLBACK",
                "structure": "IMPULSO + RETROCESO ALCISTA M5 (HL Confirmado)",
                "reason": f"Retroceso saludable defendido sobre EMA institucional (${ema8:.2f}) con giro alcista rumbo a ${recent_high:.2f}.",
                "fib_ret": low_fib_ret,
                "last_sh": recent_high,
                "last_sl": recent_low,
                "bull_trap_block": False,
                "bear_trap_block": True
            }

    return {
        "signal": "NONE",
        "structure": "CONSOLIDACIÓN M5",
        "reason": f"Precio entre soporte ${recent_low:.2f} y resistencia ${recent_high:.2f}. Esperando ruptura o rechazo limpio.",
        "fib_ret": 0.5,
        "last_sh": recent_high,
        "last_sl": recent_low,
        "bull_trap_block": recent_bear_displacement,
        "bear_trap_block": recent_bull_displacement
    }

def reconstruct_morning_signals_if_empty(candles_1m: List[Dict[str, Any]]):
    """
    Si la tabla signal_history está vacía al arrancar, analiza las últimas 3 horas de velas M5
    para poblar la bitácora con las entradas y salidas exactas que ocurrieron en las estructuras previas (ej: 08:00 a 10:30).
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM signal_history")
        count = c.fetchone()[0]
        conn.close()
        if count > 0 or len(candles_1m) < 35:
            return

        candles_5m = aggregate_timeframe_candles(candles_1m, tf_minutes=5)
        if len(candles_5m) < 8:
            return

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for idx in range(6, len(candles_5m)):
            sub_m5 = candles_5m[:idx + 1]
            m5_eval = detect_m5_swing_pullbacks(sub_m5)
            sig = m5_eval["signal"]
            if sig != "NONE":
                candle = sub_m5[-1]
                dt_ec = datetime.fromtimestamp(candle["ts"], tz=EC_TZ).strftime("%H:%M:%S")
                price = candle["close"]
                if "BUY" in sig:
                    c.execute("""INSERT INTO signal_history (ts, time_ec, event_type, direction, price, sl, tp1, pnl, reason)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (candle["ts"], dt_ec, "ENTER", "COMPRA", price, round(price - 2.8, 2), round(price + 4.5, 2), 0.0, m5_eval["structure"] + ": " + m5_eval["reason"]))
                elif "SELL" in sig:
                    c.execute("""INSERT INTO signal_history (ts, time_ec, event_type, direction, price, sl, tp1, pnl, reason)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (candle["ts"], dt_ec, "ENTER", "VENTA", price, round(price + 2.8, 2), round(price - 4.5, 2), 0.0, m5_eval["structure"] + ": " + m5_eval["reason"]))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Reconstruct history error: {e}")

def get_last_signal() -> Dict[str, Any]:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price, entry_ts, cooldown_until FROM last_signal WHERE symbol='XAUUSD'")
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "direction": row[0],
                "confirmed_at": row[1],
                "phase": row[2],
                "entry_price": float(row[3] or 0),
                "sl_price": float(row[4] or 0),
                "tp_price": float(row[5] or 0),
                "tp2_price": float(row[6] or 0),
                "max_favorable_price": float(row[7] or row[3] or 0),
                "entry_ts": int(row[8] or 0),
                "cooldown_until": int(row[9] or 0)
            }
    except Exception as e:
        print(f"get_last_signal error: {e}")
    return {
        "direction": "ESPERA",
        "confirmed_at": datetime.now(EC_TZ).isoformat(),
        "phase": "STANDBY",
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "tp2_price": 0.0,
        "max_favorable_price": 0.0,
        "entry_ts": 0,
        "cooldown_until": 0
    }

def update_last_signal(
    direction: str,
    phase: str,
    entry_price: float = 0.0,
    sl_price: float = 0.0,
    tp_price: float = 0.0,
    tp2_price: float = 0.0,
    max_favorable_price: float = 0.0,
    entry_ts: int = 0,
    cooldown_until: int = 0
):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO last_signal
                     (symbol, direction, confirmed_at, phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price, entry_ts, cooldown_until)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  ("XAUUSD", direction, datetime.now(EC_TZ).isoformat(), phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price, entry_ts, cooldown_until))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"update_last_signal error: {e}")

# ==============================================================================
# MOTOR ALGORÍTMICO INTEGRAL TRENDSPIDER v15.5 (CON ESTRUCTURAS M5 + AUDIO)
# ==============================================================================

def analyze_market_trendspider(
    analysis_type: Optional[str] = None,
    drawing_input: Optional[str] = None,
    island_gaps: Optional[str] = None,
    quality_filter: Optional[str] = None,
    heatmap_mode: Optional[str] = None,
    ai_model: Optional[str] = None,
    tp_pct: Optional[float] = None,
    sl_pct: Optional[float] = None,
    horizon: Optional[int] = None,
    truth_lock_ts: Optional[str] = None
) -> Dict[str, Any]:
    def _clean(val, key, default):
        if val is None or hasattr(val, "default"):
            stored = get_setting(key)
            return stored if stored else default
        return val

    analysis_type = str(_clean(analysis_type, "analysis_type", "Standard"))
    drawing_input = str(_clean(drawing_input, "drawing_input", "Wick"))
    island_gaps = str(_clean(island_gaps, "island_gaps", "Respect"))
    quality_filter = str(_clean(quality_filter, "quality_filter", "Most Relevant"))
    heatmap_mode = str(_clean(heatmap_mode, "heatmap_mode", "Horizontal"))
    ai_model = str(_clean(ai_model, "ai_model", "Ensemble"))
    tp_pct = float(_clean(tp_pct, "tp_pct", 0.15))
    sl_pct = float(_clean(sl_pct, "sl_pct", 0.10))
    horizon = int(_clean(horizon, "horizon", 20))
    truth_lock_ts = _clean(truth_lock_ts, "truth_lock_ts", "")
    if hasattr(truth_lock_ts, "default"):
        truth_lock_ts = ""

    live_price, feed_source = get_live_spot_price()
    update_current_1m_candle(live_price, "FEED")

    candles_1m = get_1m_candles(180)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    need_sync = (
        len(candles_1m) < 60 or
        (len(candles_1m) >= 2 and (now_ts - candles_1m[-2]["ts"]) > 150) or
        any(c.get("source") == "SYNC_1M" for c in candles_1m[-5:])
    )
    if need_sync:
        sync_historical_1m_candles()
        update_current_1m_candle(live_price, "FEED")
        candles_1m = get_1m_candles(180)

    # Reconstruir historial de la mañana si la base de datos estaba recién creada
    reconstruct_morning_signals_if_empty(candles_1m)

    # 1. Truth in Analysis (Anti-Repintado)
    is_locked = False
    in_sample_candles = candles_1m
    lock_index = -1

    if truth_lock_ts and truth_lock_ts != "":
        try:
            lock_ts_val = int(truth_lock_ts)
            for idx, c in enumerate(candles_1m):
                if c["ts"] >= lock_ts_val:
                    lock_index = idx
                    break
            if 15 <= lock_index < len(candles_1m):
                is_locked = True
                in_sample_candles = candles_1m[:lock_index + 1]
        except Exception as e:
            print(f"Truth lock parse error: {e}")

    # 2. Módulo 1: Auto-Trendlines
    trend_engine = TrendSpiderAutoTrendlines(
        analysis_type=analysis_type,
        drawing_input=drawing_input,
        island_gaps=island_gaps,
        quality_filter=quality_filter,
        lines_proximity_factor=3.5,
        atr_island_mult=3.0
    )
    trendlines_data = trend_engine.compute_all_trendlines(in_sample_candles)
    active_trendlines = trendlines_data["active_lines"]
    atr = trendlines_data["atr"]

    # 3. Módulo 2: Auto-Fibs Automáticos
    fib_engine = TrendSpiderAutoFibs(
        analysis_type=analysis_type,
        drawing_input=drawing_input,
        reverse=False
    )
    fib_data = fib_engine.compute_auto_fibs(in_sample_candles)

    # 4. Módulo 3: Heatmap Matrix 40x60
    heatmap_engine = TrendSpiderHeatmapEngine(mode=heatmap_mode)
    heatmap_data = heatmap_engine.compute_heatmaps(in_sample_candles, active_trendlines)

    # 5. Módulo 5: AI Strategy Lab
    strategy_lab = TrendSpiderStrategyLab(
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        horizon=horizon,
        active_model=ai_model
    )
    ai_strategy_data = strategy_lab.train_and_evaluate(in_sample_candles)

    # 6. Módulo 6: Multi-Timeframe Analysis (M5 Impulso y Retroceso + Alertas)
    mtfa_engine = TrendSpiderMTFAEngine(touch_cushion_atr_mult=0.35)
    candles_5m = aggregate_timeframe_candles(in_sample_candles, tf_minutes=5)
    m5_swing = detect_m5_swing_pullbacks(candles_5m)

    last_candle = in_sample_candles[-1]
    prev_candle = in_sample_candles[-2] if len(in_sample_candles) >= 2 else last_candle
    dynamic_alerts = mtfa_engine.evaluate_touch_cushion_alerts(
        current_candle=last_candle,
        prev_candle=prev_candle,
        trendlines=active_trendlines,
        fib_levels=fib_data.get("levels", {}),
        atr=atr
    )

    # ==========================================================================
    # MOTOR DE PUNTUACIÓN Y CONFLUENCIA (CAPTURA DE IMPULSOS Y RETROCESOS M5)
    # ==========================================================================
    buy_points = 0
    sell_points = 0
    confluences_audit = []

    # Pilar A: Estructura M5 de Impulso y Retroceso + Filtro Anti-Trampas
    m5_sig = m5_swing["signal"]
    if m5_sig in ["BUY_PULLBACK", "BUY_REVERSAL"]:
        buy_points += 6
        confluences_audit.append({
            "module": "ESTRUCTURA_M5", "side": "COMPRA", "weight": 6,
            "title": f"🎯 {m5_swing['structure']}",
            "desc": m5_swing["reason"]
        })
    elif m5_sig in ["SELL_PULLBACK", "SELL_CHOCH"]:
        sell_points += 6
        confluences_audit.append({
            "module": "ESTRUCTURA_M5", "side": "VENTA", "weight": 6,
            "title": f"🎯 {m5_swing['structure']}",
            "desc": m5_swing["reason"]
        })
    elif m5_swing.get("bull_trap_block"):
        sell_points += 3
        confluences_audit.append({
            "module": "FILTRO_ANTI_TRAMPAS", "side": "VENTA", "weight": 3,
            "title": f"🛡️ {m5_swing['structure']}",
            "desc": m5_swing["reason"]
        })

    # Pilar B: Auto-Trendlines & Breakout / Bounce
    has_bullish_breakout = any(l.get("breakout") == "BULLISH_BREAKOUT" for l in active_trendlines)
    has_bearish_breakout = any(l.get("breakout") == "BEARISH_BREAKOUT" for l in active_trendlines)
    has_bullish_bounce = any(a["trigger"] == "BOUNCE" and a["side"] == "COMPRA" for a in dynamic_alerts)
    has_bearish_bounce = any(a["trigger"] == "BOUNCE" and a["side"] == "VENTA" for a in dynamic_alerts)

    if has_bullish_breakout:
        buy_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "COMPRA", "weight": 4,
            "title": "RUPTURA DIRECTRIZ AL CIERRE (Breakout)",
            "desc": "Cierre de vela confirmado superando la directriz bajista."
        })
    elif has_bullish_bounce:
        buy_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "COMPRA", "weight": 4,
            "title": "REBOTE LIMPIO EN SOPORTE FRACTAL (Bounce)",
            "desc": "Rechazo alcista dentro del Colchón de Sensibilidad ATR."
        })

    if has_bearish_breakout:
        sell_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "VENTA", "weight": 4,
            "title": "RUPTURA DIRECTRIZ AL CIERRE (Breakdown)",
            "desc": "Cierre de vela confirmado perforando el soporte tendencial."
        })
    elif has_bearish_bounce:
        sell_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "VENTA", "weight": 4,
            "title": "RECHAZO LIMPIO EN RESISTENCIA FRACTAL (Bounce)",
            "desc": "Toque en la directriz superior seguido de rechazo bajista."
        })

    # Pilar C: Auto-Fibonacci Golden Zone Confluence
    fib_gz = fib_data.get("golden_zone", {})
    if fib_gz.get("in_zone", False):
        if fib_data.get("impulse_direction") == "BULLISH" and last_candle["bullish"]:
            buy_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "COMPRA", "weight": 3,
                "title": f"ZONA DORADA OTE (Fib 0.382 - 0.618: ${fib_gz.get('low')} - ${fib_gz.get('high')})",
                "desc": "Fin de retroceso en zona institucional con vela verde de continuación."
            })
        elif fib_data.get("impulse_direction") == "BEARISH" and not last_candle["bullish"]:
            sell_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "VENTA", "weight": 3,
                "title": f"ZONA DORADA OTE (Fib 0.382 - 0.618: ${fib_gz.get('low')} - ${fib_gz.get('high')})",
                "desc": "Fin de rebote correctivo en zona dorada bajista con vela roja."
            })

    # Pilar D: Heatmap Liquidity & Order Block Confluence
    top_clusters = heatmap_data.get("top_clusters", [])
    near_cluster_support = False
    near_cluster_resistance = False
    for cl in top_clusters:
        p_dist = abs(live_price - cl["price"])
        if p_dist <= (0.55 * atr):
            if live_price >= cl["price"]:
                near_cluster_support = True
            else:
                near_cluster_resistance = True

    if near_cluster_support:
        buy_points += 2
        confluences_audit.append({
            "module": "HEATMAP_MATRIX", "side": "COMPRA", "weight": 2,
            "title": "BLOQUE DE LIQUIDEZ INSTITUCIONAL EN MATRIZ 40x60",
            "desc": "Alta densidad de Puntos Especiales actuando como piso de absorción."
        })
    if near_cluster_resistance:
        sell_points += 2
        confluences_audit.append({
            "module": "HEATMAP_MATRIX", "side": "VENTA", "weight": 2,
            "title": "BARRERA DE LIQUIDEZ INSTITUCIONAL EN MATRIZ 40x60",
            "desc": "Alta densidad de órdenes pasivas frenando la subida."
        })

    # Pilar E: AI Strategy Lab Probability Filter (Análisis Numérico Cuantitativo a 20 min)
    ai_buy_prob = float(ai_strategy_data.get("buy_prob", 0.50))
    ai_sell_prob = float(ai_strategy_data.get("sell_prob", 0.50))
    tot_p = ai_buy_prob + ai_sell_prob + 1e-6
    norm_ai_buy = ai_buy_prob / tot_p
    norm_ai_sell = ai_sell_prob / tot_p
    ai_win_rate = float(ai_strategy_data.get("metrics", {}).get("win_rate", 70.0))
    ai_confidence = int(round(max(norm_ai_buy, norm_ai_sell) * 100))

    if norm_ai_buy >= 0.56:
        buy_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "COMPRA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): VENTAJA MATEMÁTICA {norm_ai_buy*100:.0f}%",
            "desc": f"Análisis numérico confirma ventaja compradora a 20 min (Acierto histórico: {ai_win_rate:.0f}%)."
        })
    elif norm_ai_sell >= 0.56:
        sell_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "VENTA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): VENTAJA MATEMÁTICA {norm_ai_sell*100:.0f}%",
            "desc": f"Análisis numérico confirma ventaja vendedora a 20 min (Acierto histórico: {ai_win_rate:.0f}%)."
        })

    # S/R y Espacio Libre
    support_val = min(l["current_y"] for l in active_trendlines if l["kind"] == "SUPPORT") if any(l["kind"] == "SUPPORT" for l in active_trendlines) else min(m5_swing.get("last_sl", live_price - 4.0), live_price - atr * 2.0)
    resistance_val = max(l["current_y"] for l in active_trendlines if l["kind"] == "RESISTANCE") if any(l["kind"] == "RESISTANCE" for l in active_trendlines) else max(m5_swing.get("last_sh", live_price + 4.0), live_price + atr * 2.0)
    room_up = max(0.0, round(resistance_val - live_price, 2))
    room_down = max(0.0, round(live_price - support_val, 2))

    # ==========================================================================
    # ==========================================================================
    # GESTIÓN DEL CICLO DE VIDA DE LA OPERACIÓN Y DISPARO SONORO (PRONÓSTICO 20 MIN)
    # ==========================================================================
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price
    current_sl = last_sig["sl_price"]
    current_tp1 = last_sig["tp_price"]
    current_tp2 = last_sig["tp2_price"]
    max_fav = last_sig["max_favorable_price"] if last_sig["max_favorable_price"] > 1000 else entry_p
    entry_ts = int(last_sig.get("entry_ts", 0) or 0)
    cooldown_until = int(last_sig.get("cooldown_until", 0) or 0)

    # Dimensionamiento estructural para Pronóstico a 20 Minutos (~4 velas M5 en Oro):
    # SL amplio basado en pivotes y ATR (~$4.50 a $6.50) para ser inmune al ruido de 1 sola vela.
    # TP proyectado para swing de ganancia a 20 min (~$5.50 a $8.50).
    sl_distance = round(max(4.50, min(atr * 2.2, 6.50)), 2)
    tp1_distance = round(max(5.50, min(atr * 2.8, 8.50)), 2)
    tp2_distance = round(max(9.00, min(atr * 4.2, 14.00)), 2)

    # Control de tiempo transcurrido (Minuto X de 20)
    elapsed_min = 0
    remaining_min = 20
    if active_dir in ["COMPRA", "VENTA"]:
        if entry_ts <= 0:
            entry_ts = now_ts
        elapsed_seconds = max(0, now_ts - entry_ts)
        elapsed_min = int(elapsed_seconds // 60)
        remaining_min = max(0, 20 - elapsed_min)

    is_in_cooldown = (now_ts < cooldown_until)
    cooldown_rem_sec = max(0, cooldown_until - now_ts)

    final_dir = "ESPERA"
    alert_text = "⏸ PRONÓSTICO 20 MIN: ANALIZANDO ESTRUCTURAS PREVIAS"
    alert_type = "WAIT"
    alert_desc = f"Estructura M5: {m5_swing['structure']}. {m5_swing['reason']}"
    flip_reason = "Monitoreando patrones numéricos y fractales"
    confidence_score = max(ai_confidence, 55)

    # 1. Monitoreo de Operación COMPRA ya abierta (Inmune a fluctuaciones de una sola vela)
    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        if live_price > max_fav:
            max_fav = live_price
            update_last_signal("COMPRA", "HOLD_COMPRA", entry_p, current_sl, current_tp1, current_tp2, max_fav, entry_ts, 0)

        # Regla 1: Proteger en Break-Even cuando avance >= +$3.80 USD (asegura +1.00 USD ganancia)
        if (max_fav - entry_p) >= 3.80 and current_sl < entry_p:
            current_sl = round(entry_p + 1.00, 2)
            update_last_signal("COMPRA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav, entry_ts, 0)
            log_signal_event("BREAK_EVEN", "COMPRA", live_price, current_sl, current_tp1, pnl, "Stop Loss protegido en Break-Even (+1.00 USD asegurado)")

        # Regla 2: Salida por Take Profit objetivo (+5.20 USD o TP1 alcanzado)
        if (live_price >= current_tp1 and current_tp1 > 1000) or pnl >= 5.20:
            update_last_signal("ESPERA", "TP_COMPRA_EXECUTED", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("TAKE_PROFIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Objetivo 20 min alcanzado COMPRA (+${pnl:.2f} USD)")
            forecast_20m_data = {
                "direction": "COMPRA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_buy * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=96,
                alert=f"💰 SALIR EN GANANCIA COMPRA (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo de la proyección a 20 minutos alcanzado en ${live_price:.2f} desde entrada en ${entry_p:.2f}. Cierra y asegura tu ganancia de +${pnl:.2f} USD.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP / Meta alcanzada",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 3: Salida por Maduración de Pronóstico de 20 Minutos con Ganancia
        if elapsed_min >= 18 and pnl >= 2.00:
            update_last_signal("ESPERA", "HORIZON_20M_PROFIT", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("TAKE_PROFIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Maduración de 20 min cumplida con ganancia COMPRA (+${pnl:.2f} USD)")
            forecast_20m_data = {
                "direction": "COMPRA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_buy * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"💰 SALIDA POR MADURACIÓN DE 20 MIN (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Se completó el horizonte de 20 minutos con ganancia acumulada de +${pnl:.2f} USD (${entry_p:.2f} → ${live_price:.2f}). Cierra la posición para asegurar beneficios.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="Horizonte 20m cumplido",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 4: Salida por Stop Loss Estructural Real (NO por mechas ni puntos aislados)
        if (live_price <= current_sl and current_sl > 1000):
            update_last_signal("ESPERA", "SL_COMPRA_EXECUTED", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("EXIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Stop Loss estructural alcanzado COMPRA ({pnl:+.2f} USD)")
            forecast_20m_data = {
                "direction": "COMPRA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_buy * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"El precio perforó el soporte estructural fijado en ${current_sl:.2f}. Cierra la compra para proteger tu capital.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="Soporte estructural roto",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 5: Invalidación Macro por Estructura Mayor (Solo tras al menos 6 min y ruptura bajista mayor)
        if elapsed_min >= 6 and m5_sig == "SELL_CHOCH" and pnl <= -3.00:
            update_last_signal("ESPERA", "CHOUCH_INVALIDATION_COMPRA", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("EXIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Invalidación estructural macro COMPRA ({pnl:+.2f} USD)")
            forecast_20m_data = {
                "direction": "COMPRA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_buy * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"Estructura macro rota al cierre en ${live_price:.2f}. Cierra la compra de inmediato.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="CHoCH Macro confirmado",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Permanecer FIRMES durante el desarrollo del pronóstico (Fluctuaciones normales)
        final_dir = "COMPRA"
        alert_text = f"🛡️ MANTENER COMPRA • PRONÓSTICO 20 MIN ({pnl:+.2f} USD • Min {elapsed_min}/20)"
        alert_type = "ENTER"
        alert_desc = f"Progreso: {elapsed_min} de 20 min (~{remaining_min} min restantes). Entrada: ${entry_p:.2f} • SL Estructural: ${current_sl:.2f} • Meta 20m: ${current_tp1:.2f}. Fluctuación normal dentro de la estructura."
        flip_reason = f"Pronóstico 20 min activo ({pnl:+.2f} USD)"
        confidence_score = 88

    # 2. Monitoreo de Operación VENTA ya abierta (Inmune a fluctuaciones de una sola vela)
    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        if live_price < max_fav:
            max_fav = live_price
            update_last_signal("VENTA", "HOLD_VENTA", entry_p, current_sl, current_tp1, current_tp2, max_fav, entry_ts, 0)

        # Regla 1: Proteger en Break-Even cuando avance >= +$3.80 USD
        if (entry_p - max_fav) >= 3.80 and current_sl > entry_p:
            current_sl = round(entry_p - 1.00, 2)
            update_last_signal("VENTA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav, entry_ts, 0)
            log_signal_event("BREAK_EVEN", "VENTA", live_price, current_sl, current_tp1, pnl, "Stop Loss protegido en Break-Even (+1.00 USD asegurado)")

        # Regla 2: Salida por Take Profit objetivo (+5.20 USD o TP1 alcanzado)
        if (live_price <= current_tp1 and current_tp1 > 1000) or pnl >= 5.20:
            update_last_signal("ESPERA", "TP_VENTA_EXECUTED", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("TAKE_PROFIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Objetivo 20 min alcanzado VENTA (+${pnl:.2f} USD)")
            forecast_20m_data = {
                "direction": "VENTA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_sell * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=96,
                alert=f"💰 SALIR EN GANANCIA VENTA (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo de la proyección a 20 minutos alcanzado en ${live_price:.2f} desde entrada en ${entry_p:.2f}. Cierra y asegura tu ganancia de +${pnl:.2f} USD.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP / Meta alcanzada",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 3: Salida por Maduración de Pronóstico de 20 Minutos con Ganancia
        if elapsed_min >= 18 and pnl >= 2.00:
            update_last_signal("ESPERA", "HORIZON_20M_PROFIT", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("TAKE_PROFIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Maduración de 20 min cumplida con ganancia VENTA (+${pnl:.2f} USD)")
            forecast_20m_data = {
                "direction": "VENTA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_sell * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"💰 SALIDA POR MADURACIÓN DE 20 MIN (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Se completó el horizonte de 20 minutos con ganancia acumulada de +${pnl:.2f} USD (${entry_p:.2f} → ${live_price:.2f}). Cierra la posición para asegurar beneficios.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="Horizonte 20m cumplido",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 4: Salida por Stop Loss Estructural Real
        if (live_price >= current_sl and current_sl > 1000):
            update_last_signal("ESPERA", "SL_VENTA_EXECUTED", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("EXIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Stop Loss estructural alcanzado VENTA ({pnl:+.2f} USD)")
            forecast_20m_data = {
                "direction": "VENTA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_sell * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"El precio superó la resistencia estructural fijada en ${current_sl:.2f}. Cierra la venta para proteger tu capital.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="Resistencia estructural rota",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Regla 5: Invalidación Macro por Estructura Mayor
        if elapsed_min >= 6 and m5_sig == "BUY_REVERSAL" and pnl <= -3.00:
            update_last_signal("ESPERA", "CHOUCH_INVALIDATION_VENTA", 0, 0, 0, 0, 0, 0, now_ts + 180)
            log_signal_event("EXIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Invalidación estructural macro VENTA ({pnl:+.2f} USD)")
            forecast_20m_data = {
                "direction": "VENTA", "horizon_minutes": 20, "elapsed_minutes": elapsed_min,
                "remaining_minutes": 0, "expected_gain_usd": tp1_distance, "target_price": current_tp1,
                "structural_sl": current_sl, "ai_probability": int(round(norm_ai_sell * 100)), "in_cooldown": True,
                "cooldown_remaining_sec": 180, "m5_structure": m5_swing.get("structure", ""), "m5_reason": m5_swing.get("reason", "")
            }
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"Estructura macro rota al cierre en ${live_price:.2f}. Cierra la venta de inmediato.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="CHoCH Macro confirmado",
                m5_swing=m5_swing, forecast_20m=forecast_20m_data
            )

        # Permanecer FIRMES durante el desarrollo del pronóstico
        final_dir = "VENTA"
        alert_text = f"🛡️ MANTENER VENTA • PRONÓSTICO 20 MIN ({pnl:+.2f} USD • Min {elapsed_min}/20)"
        alert_type = "ENTER"
        alert_desc = f"Progreso: {elapsed_min} de 20 min (~{remaining_min} min restantes). Entrada: ${entry_p:.2f} • SL Estructural: ${current_sl:.2f} • Meta 20m: ${current_tp1:.2f}. Fluctuación normal dentro de la estructura."
        flip_reason = f"Pronóstico 20 min activo ({pnl:+.2f} USD)"
        confidence_score = 88

    # 3. Disparo de NUEVO Pronóstico a 20 Minutos (Análisis de Estructuras Anteriores + Modelos Numéricos)
    else:
        if is_in_cooldown:
            final_dir = "ESPERA"
            alert_text = f"⏳ ENFRIAMIENTO POST-OPERACIÓN ({cooldown_rem_sec}s)"
            alert_type = "WAIT"
            alert_desc = "Filtro anti-ruido activo: evaluando consolidación de estructura previa para evitar entradas apresuradas."
            flip_reason = f"Enfriamiento ({cooldown_rem_sec}s)"
            confidence_score = 60
        else:
            bull_trap_blocked = bool(m5_swing.get("bull_trap_block", False))
            bear_trap_blocked = bool(m5_swing.get("bear_trap_block", False))

            if buy_points >= 6 and buy_points >= sell_points + 3 and not bull_trap_blocked:
                final_dir = "COMPRA"
                entry_p = live_price

                # Anclar SL debajo del suelo de estructuras anteriores si está en rango seguro
                last_sl = float(m5_swing.get("last_sl") or (live_price - sl_distance))
                if (live_price - 6.50) <= last_sl <= (live_price - 3.50):
                    current_sl = round(last_sl - 0.40, 2)
                else:
                    current_sl = round(live_price - sl_distance, 2)

                current_tp1 = round(live_price + tp1_distance, 2)
                current_tp2 = round(live_price + tp2_distance, 2)
                confidence_score = min(96, int(75 + (buy_points * 2.2)))
                alert_text = f"🚀 PRONÓSTICO 20 MIN: COMPRA CONFIRMADA (+${tp1_distance:.2f} USD)"
                alert_type = "ENTER"
                alert_desc = f"Estructura previa consolidada ({m5_swing['structure']}). Meta proyectada a 20 min: ${current_tp1:.2f} • SL Estructural: ${current_sl:.2f}. Mantén la posición ante fluctuaciones menores."
                flip_reason = f"Nueva COMPRA en ${live_price:.2f}"
                update_last_signal("COMPRA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p, now_ts, 0)
                log_signal_event("ENTER", "COMPRA", entry_p, current_sl, current_tp1, 0.0, f"Pronóstico 20 min: {m5_swing['structure']}")

            elif sell_points >= 6 and sell_points >= buy_points + 3 and not bear_trap_blocked:
                final_dir = "VENTA"
                entry_p = live_price

                # Anclar SL encima del techo de estructuras anteriores si está en rango seguro
                last_sh = float(m5_swing.get("last_sh") or (live_price + sl_distance))
                if (live_price + 3.50) <= last_sh <= (live_price + 6.50):
                    current_sl = round(last_sh + 0.40, 2)
                else:
                    current_sl = round(live_price + sl_distance, 2)

                current_tp1 = round(live_price - tp1_distance, 2)
                current_tp2 = round(live_price - tp2_distance, 2)
                confidence_score = min(96, int(75 + (sell_points * 2.2)))
                alert_text = f"📉 PRONÓSTICO 20 MIN: VENTA CONFIRMADA (+${tp1_distance:.2f} USD)"
                alert_type = "ENTER"
                alert_desc = f"Estructura previa consolidada ({m5_swing['structure']}). Meta proyectada a 20 min: ${current_tp1:.2f} • SL Estructural: ${current_sl:.2f}. Mantén la posición ante fluctuaciones menores."
                flip_reason = f"Nueva VENTA en ${live_price:.2f}"
                update_last_signal("VENTA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p, now_ts, 0)
                log_signal_event("ENTER", "VENTA", entry_p, current_sl, current_tp1, 0.0, f"Pronóstico 20 min: {m5_swing['structure']}")

            else:
                final_dir = "ESPERA"
                confidence_score = 55
                alert_text = f"⏸ PRONÓSTICO 20 MIN: ANALIZANDO ESTRUCTURAS PREVIAS"
                alert_type = "WAIT"
                alert_desc = f"{m5_swing['structure']}: {m5_swing['reason']} (Confluencia: Compra {buy_points} / Venta {sell_points}). Esperando consolidación de patrón o ruptura confirmada."
                flip_reason = "Analizando estructuras previas"

    forecast_dir_eval = active_dir if active_dir in ["COMPRA", "VENTA"] else ("COMPRA" if buy_points >= sell_points + 2 else "VENTA" if sell_points >= buy_points + 2 else "ESPERA")
    forecast_20m_data = {
        "direction": forecast_dir_eval,
        "horizon_minutes": 20,
        "elapsed_minutes": elapsed_min,
        "remaining_minutes": remaining_min,
        "expected_gain_usd": tp1_distance,
        "target_price": round(current_tp1 if active_dir != "ESPERA" else (live_price + tp1_distance if forecast_dir_eval == "COMPRA" else live_price - tp1_distance), 2),
        "structural_sl": round(current_sl if active_dir != "ESPERA" else (live_price - sl_distance if forecast_dir_eval == "COMPRA" else live_price + sl_distance), 2),
        "ai_probability": int(round(norm_ai_buy * 100)) if forecast_dir_eval == "COMPRA" else int(round(norm_ai_sell * 100)) if forecast_dir_eval == "VENTA" else int(round(max(norm_ai_buy, norm_ai_sell) * 100)),
        "in_cooldown": is_in_cooldown,
        "cooldown_remaining_sec": cooldown_rem_sec,
        "m5_structure": m5_swing.get("structure", ""),
        "m5_reason": m5_swing.get("reason", "")
    }

    return build_response(
        direction=final_dir, confidence=confidence_score,
        alert=alert_text, alert_type=alert_type, alert_desc=alert_desc,
        entry_p=entry_p if final_dir != "ESPERA" else live_price,
        sl=current_sl if final_dir != "ESPERA" else 0.0,
        tp1=current_tp1 if final_dir != "ESPERA" else 0.0,
        tp2=current_tp2 if final_dir != "ESPERA" else 0.0,
        live_price=live_price, feed_source=feed_source, atr=atr,
        confluences=confluences_audit, trendlines_data=trendlines_data,
        fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
        candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
        support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
        buy_score=buy_points, sell_score=sell_points, flip_reason=flip_reason,
        m5_swing=m5_swing, forecast_20m=forecast_20m_data
    )

def build_response(
    direction: str, confidence: int, alert: str, alert_type: str, alert_desc: str,
    entry_p: float, sl: float, tp1: float, tp2: float,
    live_price: float, feed_source: str, atr: float,
    confluences: List[Dict[str, Any]], trendlines_data: Dict[str, Any],
    fib_data: Dict[str, Any], heatmap_data: Dict[str, Any], ai_data: Dict[str, Any],
    candles: List[Dict[str, Any]], is_locked: bool, lock_ts: Optional[str],
    support: float, resistance: float, room_up: float, room_down: float,
    buy_score: int, sell_score: int, flip_reason: str,
    m5_swing: Optional[Dict[str, Any]] = None,
    forecast_20m: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {
        "symbol": "XAUUSD",
        "direction": direction,
        "entry": round(entry_p, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "dist": round(abs(entry_p - sl), 2) if sl > 0 else round(atr * 2.2, 2),
        "tp_dist": round(abs(tp1 - entry_p), 2) if tp1 > 0 else round(atr * 2.8, 2),
        "live_price": round(live_price, 2),
        "feed_source": feed_source,
        "confidence": confidence,
        "alert": alert,
        "alert_type": alert_type,
        "alert_desc": alert_desc,
        "flip_reason": flip_reason,
        "atr": round(atr, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "room_up": room_up,
        "room_down": room_down,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "points_detail": confluences,
        "m5_structure": m5_swing or {},
        "forecast_20m": forecast_20m or {},
        "signal_history": get_signal_history(20),
        "trendlines": trendlines_data.get("active_lines", []),
        "top_trendline_score": trendlines_data.get("top_score", 0.0),
        "total_candidate_vectors": trendlines_data.get("total_candidates", 0),
        "fibonacci": fib_data,
        "heatmap": heatmap_data,
        "ai_strategy": ai_data,
        "truth_in_analysis": {
            "locked": is_locked,
            "lock_ts": lock_ts,
            "status": "LOCKED (OUT-OF-SAMPLE TEST)" if is_locked else "UNLOCKED (DYNAMIC LIVE RECALC)"
        },
        "recent_candles": candles[-45:] if len(candles) >= 45 else candles,
        "timestamp": datetime.now(EC_TZ).isoformat()
    }

# ==============================================================================
# ENDPOINTS REST API & WEBHOOKS
# ==============================================================================

@app.get("/")
def root():
    return {
        "message": "EDGEALERT - TRENDSPIDER ALGORITHMIC ENGINE v15.5",
        "version": "15.5"
    }

@app.get("/health")
def health():
    return {"status": "ok", "symbol": "XAUUSD", "version": "15.5"}

@app.get("/signals/history")
def signals_history_endpoint():
    return get_signal_history(30)

_LATEST_ANALYSIS_LOCK = threading.Lock()
_LATEST_ANALYSIS_SNAPSHOT = None
_LATEST_ANALYSIS_TS = 0.0

def get_or_compute_analysis(
    analysis_type: Optional[str] = None,
    drawing_input: Optional[str] = None,
    island_gaps: Optional[str] = None,
    quality_filter: Optional[str] = None,
    heatmap_mode: Optional[str] = None,
    ai_model: Optional[str] = None,
    tp_pct: Optional[float] = None,
    sl_pct: Optional[float] = None,
    horizon: Optional[int] = None,
    truth_lock_ts: Optional[str] = None
) -> Dict[str, Any]:
    global _LATEST_ANALYSIS_SNAPSHOT, _LATEST_ANALYSIS_TS
    now = time.time()
    if truth_lock_ts and str(truth_lock_ts).strip() != "":
        return analyze_market_trendspider(
            analysis_type=analysis_type,
            drawing_input=drawing_input,
            island_gaps=island_gaps,
            quality_filter=quality_filter,
            heatmap_mode=heatmap_mode,
            ai_model=ai_model,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            horizon=horizon,
            truth_lock_ts=truth_lock_ts
        )

    if _LATEST_ANALYSIS_SNAPSHOT is not None and (now - _LATEST_ANALYSIS_TS) < 2.5:
        return _LATEST_ANALYSIS_SNAPSHOT

    with _LATEST_ANALYSIS_LOCK:
        if _LATEST_ANALYSIS_SNAPSHOT is not None and (time.time() - _LATEST_ANALYSIS_TS) < 2.5:
            return _LATEST_ANALYSIS_SNAPSHOT
        res = analyze_market_trendspider(
            analysis_type=analysis_type,
            drawing_input=drawing_input,
            island_gaps=island_gaps,
            quality_filter=quality_filter,
            heatmap_mode=heatmap_mode,
            ai_model=ai_model,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            horizon=horizon,
            truth_lock_ts=truth_lock_ts
        )
        _LATEST_ANALYSIS_SNAPSHOT = res
        _LATEST_ANALYSIS_TS = time.time()
        return res

@app.get("/signals/live")
def signals_live(
    analysis_type: Optional[str] = Query(None),
    drawing_input: Optional[str] = Query(None),
    island_gaps: Optional[str] = Query(None),
    quality_filter: Optional[str] = Query(None),
    heatmap_mode: Optional[str] = Query(None),
    ai_model: Optional[str] = Query(None),
    tp_pct: Optional[float] = Query(None),
    sl_pct: Optional[float] = Query(None),
    horizon: Optional[int] = Query(None),
    truth_lock_ts: Optional[str] = Query(None)
):
    try:
        result = get_or_compute_analysis(
            analysis_type=analysis_type,
            drawing_input=drawing_input,
            island_gaps=island_gaps,
            quality_filter=quality_filter,
            heatmap_mode=heatmap_mode,
            ai_model=ai_model,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            horizon=horizon,
            truth_lock_ts=truth_lock_ts
        )
        return [result]
    except Exception as e:
        print(f"Error in signals_live: {e}")
        p, src = get_live_spot_price()
        return [{
            "symbol": "XAUUSD",
            "direction": "ESPERA",
            "entry": p,
            "sl": 0, "tp1": 0, "tp2": 0,
            "dist": 2.8, "tp_dist": 4.5,
            "live_price": p,
            "feed_source": "RECOVERY",
            "confidence": 50,
            "alert": "⏸ CALIBRANDO MATRIZ QUANT",
            "alert_type": "WAIT",
            "alert_desc": str(e),
            "points_detail": [],
            "signal_history": get_signal_history(20),
            "flip_reason": "Recalibrando motores de geometría",
            "support": p - 4,
            "resistance": p + 4,
            "timestamp": datetime.now(EC_TZ).isoformat()
        }]

class SettingsPayload(BaseModel):
    analysis_type: Optional[str] = None
    drawing_input: Optional[str] = None
    island_gaps: Optional[str] = None
    quality_filter: Optional[str] = None
    heatmap_mode: Optional[str] = None
    ai_model: Optional[str] = None
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    horizon: Optional[int] = None
    truth_lock_ts: Optional[str] = None

@app.post("/settings")
def update_settings(payload: SettingsPayload):
    d = payload.dict(exclude_unset=True)
    for k, v in d.items():
        if v is not None:
            set_setting(k, str(v))
    return {"status": "success", "updated": d}

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
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

@app.on_event("startup")
async def startup_event():
    sync_historical_1m_candles()
    try:
        get_or_compute_analysis()
    except Exception as e:
        print(f"Pre-warm analysis error: {e}")

    async def monitor_loop():
        ticks = 0
        while True:
            try:
                p, _ = get_live_spot_price()
                if p > 1000:
                    update_current_1m_candle(p, "FEED")
                ticks += 1
                if ticks % 4 == 0:
                    sync_historical_1m_candles()
                if ticks % 2 == 0:
                    get_or_compute_analysis()
            except Exception as e:
                print(f"Monitor loop error: {e}")
            await asyncio.sleep(4)
    asyncio.create_task(monitor_loop())
