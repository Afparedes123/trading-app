import os, sqlite3, requests, asyncio, math, time
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

app = FastAPI(title="EdgeAlert - TRENDSPIDER REALTIME M5 ENGINE v16.0")
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
    # Tabla de velas de 1 minuto (OHLC) en tiempo real sin retraso
    c.execute("""CREATE TABLE IF NOT EXISTS ohlc_1m (
        ts INTEGER PRIMARY KEY,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL DEFAULT 0,
        source TEXT DEFAULT 'FEED'
    )""")
    # Tabla de estado de la última señal y gestión de trade
    c.execute("""CREATE TABLE IF NOT EXISTS last_signal (
        symbol TEXT PRIMARY KEY,
        direction TEXT,
        confirmed_at TEXT,
        phase TEXT,
        entry_price REAL DEFAULT 0,
        sl_price REAL DEFAULT 0,
        tp_price REAL DEFAULT 0,
        tp2_price REAL DEFAULT 0,
        max_favorable_price REAL DEFAULT 0
    )""")
    # Tabla de Historial / Bitácora de Alertas
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
    # Tabla de configuración persistente
    c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

DEFAULT_SETTINGS = {
    "analysis_type": "Standard",       # "Original", "Standard", "Enhanced"
    "drawing_input": "Wick",           # "Wick" (H/L) o "Body" (O/C)
    "island_gaps": "Respect",          # "Respect" o "Ignore"
    "quality_filter": "Most Relevant", # "Most Relevant" (Top 1%), "Moderately Relevant", "Unfiltered"
    "heatmap_mode": "Horizontal",      # "Horizontal", "Depth", "Trends", "Off"
    "truth_lock_ts": "",               # Timestamp congelado o vacío
    "ai_model": "Ensemble",            # "Ensemble", "RandomForest", "Logistic", "KNN", "NaiveBayes"
    "tp_pct": "0.12",                  # ~0.12% TP (~$4.90 en Oro)
    "sl_pct": "0.08",                  # ~0.08% SL (~$3.30 en Oro)
    "horizon": "30"                    # 30 velas de horizonte
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
    """Guarda cada entrada, salida, giro o break-even en la bitácora histórica"""
    try:
        now_dt = datetime.now(EC_TZ)
        now_ts = int(now_dt.timestamp())
        time_str = now_dt.strftime("%H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT ts, event_type, direction FROM signal_history ORDER BY id DESC LIMIT 1")
        last = c.fetchone()
        if last and last[1] == event_type and last[2] == direction and (now_ts - last[0]) < 45:
            conn.close()
            return
        c.execute("""INSERT INTO signal_history (ts, time_ec, event_type, direction, price, sl, tp1, pnl, reason)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (now_ts, time_str, event_type, direction, round(price, 2), round(sl, 2), round(tp1, 2), round(pnl, 2), reason))
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

    # 1. Swissquote Spot BBO Feed (Tiempo Real 0 Delay)
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
                        return round((bid + ask) / 2.0, 2), "SPOT SWISSQUOTE REALTIME"
    except:
        pass

    # 2. Gold-API Spot (Tiempo Real 0 Delay)
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=3)
        if r.status_code == 200 and r.json().get("price"):
            p = float(r.json()["price"])
            if p > 1000:
                return round(p, 2), "GOLD-API REALTIME"
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

    return 4107.50, "FALLBACK"

def sync_historical_1m_candles():
    """
    Sincroniza las últimas 240 velas de 1 minuto EN TIEMPO REAL (0 segundos de retraso)
    usando el feed de Kraken PAXGUSD ajustado al centavo con el Spot XAU/USD de Swissquote.
    (Elimina por completo el retraso de 10 minutos que tenía Yahoo Finance GC=F).
    """
    live_p, _ = get_live_spot_price()
    now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60

    # 1. Fuente Primaria: Kraken Real-Time 1m OHLC (0 Delay, incluye los últimos 15 minutos reales)
    try:
        url = "https://api.kraken.com/0/public/OHLC?pair=PAXGUSD&interval=1"
        r = requests.get(url, timeout=4)
        if r.status_code == 200:
            data = r.json().get("result", {}).get("PAXGUSD", [])
            if data and len(data) >= 30:
                recent = data[-240:]
                last_kraken_close = float(recent[-1][4])
                basis = live_p - last_kraken_close

                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                for row in recent:
                    ts_min = (int(row[0]) // 60) * 60
                    o = round(float(row[1]) + basis, 2)
                    h = round(float(row[2]) + basis, 2)
                    l = round(float(row[3]) + basis, 2)
                    cl = round(float(row[4]) + basis, 2)
                    v = float(row[6] or 1.0)

                    # En la vela del minuto actual, respetar los extremos tocados por Swissquote en vivo
                    c.execute("SELECT open, high, low, close, source FROM ohlc_1m WHERE ts=?", (ts_min,))
                    existing = c.fetchone()
                    if existing and existing[4] == "TRADINGVIEW_ACCOUNT":
                        continue
                    if existing and ts_min >= now_min - 120:
                        # No sobrescribir velas de los últimos 2 minutos que ya estamos alimentando con Swissquote tick a tick
                        continue
                    c.execute("""INSERT OR REPLACE INTO ohlc_1m (ts,open,high,low,close,volume,source)
                                 VALUES (?,?,?,?,?,?,?)""", (ts_min, o, h, l, cl, v, "REALTIME_SYNC"))
                conn.commit()
                conn.close()
                return
    except Exception as e:
        print(f"Kraken realtime sync warning: {e}")

    # 2. Respaldo si Kraken falla
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ohlc_1m")
        if c.fetchone()[0] < 60:
            for i in range(180):
                ts = now_min - ((180 - i) * 60)
                wave = math.sin(i / 8.0) * 4.5 + math.cos(i / 4.0) * 2.0
                o = round(live_p + wave, 2)
                cl = round(live_p + math.sin((i + 1) / 8.0) * 4.5 + math.cos((i + 1) / 4.0) * 2.0, 2)
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
            final_src = "TRADINGVIEW_ACCOUNT" if source == "TRADINGVIEW_ACCOUNT" else "LIVE_SPOT_TICK"
            c.execute("UPDATE ohlc_1m SET high=?, low=?, close=?, volume=?, source=? WHERE ts=?",
                      (new_h, new_l, price, v + 1, final_src, now_min))
        else:
            c.execute("INSERT INTO ohlc_1m (ts,open,high,low,close,volume,source) VALUES (?,?,?,?,?,?,?)",
                      (now_min, price, price, price, price, 1, "LIVE_SPOT_TICK"))
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

def detect_m5_swing_pullbacks(candles_5m: List[Dict[str, Any]], live_price: float) -> Dict[str, Any]:
    """
    Detector M5 Institucional en Tiempo Real (Con Filtro Anti-Cuchillo Que Cae y Detección de Rango Roto):
    1. Si las últimas 2-4 velas M5 acumularon en un piso pequeño y la vela actual rompe ese piso hacia abajo -> BREAKDOWN BAJISTA (SELL_BREAKDOWN)
    2. Si las últimas 2-4 velas M5 acumularon y rompe hacia arriba -> BREAKOUT ALCISTA (BUY_BREAKOUT)
    3. PROHIBIDO dar BUY_PULLBACK si venimos de una vela roja gigante de desplome (> $3.50) sin antes formar al menos 2 velas de freno y cierre superior.
    """
    if len(candles_5m) < 6:
        return {"signal": "NONE", "structure": "CALIBRANDO_M5", "reason": "", "fib_ret": 0.5, "last_sh": live_price + 4, "last_sl": live_price - 4}

    window = candles_5m[-24:]
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    last_c = window[-1]
    prev_c = window[-2]
    prev2_c = window[-3] if len(window) >= 3 else prev_c
    prev3_c = window[-4] if len(window) >= 4 else prev2_c

    # 1. DETECTOR DE ACUMULACIÓN DE 3 VELAS + RUPTURA (Exactamente lo que pasó en $4114 -> $4106)
    consol_candles = window[-4:-1] # las 3 velas de 5m previas a la actual
    consol_high = max(c["high"] for c in consol_candles)
    consol_low = min(c["low"] for c in consol_candles)
    consol_span = consol_high - consol_low

    # Si las 3 velas previas acumularon en un rango estrecho/medio y el precio actual rompe el soporte por más de $0.45:
    if live_price < consol_low - 0.45 and last_c["close"] < last_c["open"]:
        return {
            "signal": "SELL_BREAKDOWN",
            "structure": "QUIEBRE BAJISTA DE ACUMULACIÓN M5",
            "reason": f"El precio acumuló por 3 velas M5 en piso ${consol_low:.2f} y acaba de romper a la baja con fuerza hacia ${live_price:.2f}.",
            "fib_ret": 0.85,
            "last_sh": consol_high,
            "last_sl": consol_low
        }

    # Si las 3 velas previas acumularon y rompe el techo al alza con fuerza:
    if live_price > consol_high + 0.45 and last_c["close"] > last_c["open"]:
        return {
            "signal": "BUY_BREAKOUT",
            "structure": "RUPTURA ALCISTA DE ACUMULACIÓN M5",
            "reason": f"El precio acumuló por 3 velas M5 bajo ${consol_high:.2f} y acaba de romper al alza con fuerza hacia ${live_price:.2f}.",
            "fib_ret": 0.20,
            "last_sh": consol_high,
            "last_sl": consol_low
        }

    # Identificar pivotes principales en M5
    swing_highs = []
    swing_lows = []
    for i in range(1, len(window) - 1):
        if window[i]["high"] >= window[i - 1]["high"] and window[i]["high"] >= window[i + 1]["high"]:
            swing_highs.append((i, window[i]["high"]))
        if window[i]["low"] <= window[i - 1]["low"] and window[i]["low"] <= window[i + 1]["low"]:
            swing_lows.append((i, window[i]["low"]))

    if not swing_highs:
        swing_highs = [(0, max(highs))]
    if not swing_lows:
        swing_lows = [(0, min(lows))]

    last_sh_idx, last_sh = swing_highs[-1]
    prev_sh = swing_highs[-2][1] if len(swing_highs) >= 2 else last_sh
    last_sl_idx, last_sl = swing_lows[-1]
    prev_sl = swing_lows[-2][1] if len(swing_lows) >= 2 else last_sl

    last_bull = last_c["close"] >= last_c["open"]
    prev_bull = prev_c["close"] >= prev_c["open"]

    # Filtro Anti-Cuchillo Que Cae (Falling Knife Protection):
    # Si en las últimas 3 velas hubo un desplome bajista violento (> $5.50 de caída), NO permitir compras prematuras
    recent_drop = max(c["high"] for c in window[-4:]) - min(c["low"] for c in window[-2:])
    is_falling_knife = (recent_drop >= 5.5) and (live_price < prev2_c["open"] - 3.0)

    leg_range = max(abs(last_sh - last_sl), 2.0)

    # Caso A: Estructura Alcista M5 (Impulso -> Retroceso HL -> Giro Confirmado)
    if not is_falling_knife and (last_sl_idx < last_sh_idx or live_p_above_mid(live_price, last_sh, last_sl)):
        fib_ret = round((last_sh - live_price) / leg_range, 3)
        low_fib_ret = round((last_sh - min(last_c["low"], prev_c["low"])) / leg_range, 3)

        # Para confirmar Compra en retroceso:
        # 1. El retroceso tocó entre 32% y 72% Fib
        # 2. La vela actual es verde Y su cierre supera el máximo o apertura de la vela previa
        if 0.32 <= low_fib_ret <= 0.72 and last_bull and live_price > prev_c["close"] + 0.35:
            if last_sl >= prev_sl - 1.5:
                return {
                    "signal": "BUY_PULLBACK",
                    "structure": "IMPULSO + RETROCESO ALCISTA M5 (HL)",
                    "reason": f"Retroceso sano al {low_fib_ret*100:.0f}% Fib (${min(last_c['low'], prev_c['low']):.2f}) con vela de giro confirmada rumbo a ${last_sh:.2f}.",
                    "fib_ret": fib_ret,
                    "last_sh": last_sh,
                    "last_sl": min(last_c["low"], prev_c["low"], last_sl)
                }

    # Caso B: CHoCH Bajista o Continuación de Caída
    if is_falling_knife or last_sh_idx < last_sl_idx or live_price < (last_sh + last_sl) / 2.0:
        fib_ret = round((live_price - last_sl) / leg_range, 3)
        high_fib_ret = round((max(last_c["high"], prev_c["high"]) - last_sl) / leg_range, 3)

        # Re-entrada en Venta tras rebote débil (30%-72% Fib) o continuación tras ruptura
        if (0.28 <= high_fib_ret <= 0.75 and not last_bull and live_price < prev_c["close"] - 0.35) or (is_falling_knife and not last_bull):
            return {
                "signal": "SELL_PULLBACK",
                "structure": "ESTRUCTURA BAJISTA M5 EN DOMINIO (LH + LL)",
                "reason": f"Fuerte presión vendedora tras rechazar ${max(last_c['high'], prev_c['high']):.2f}, rompiendo soportes hacia ${live_price:.2f}.",
                "fib_ret": fib_ret,
                "last_sh": max(last_c["high"], prev_c["high"], last_sh),
                "last_sl": last_sl
            }

    return {
        "signal": "NONE",
        "structure": "CONSOLIDACIÓN M5",
        "reason": f"Precio entre soporte M5 ${consol_low:.2f} y resistencia ${consol_high:.2f}.",
        "fib_ret": 0.5,
        "last_sh": max(last_sh, consol_high),
        "last_sl": min(last_sl, consol_low)
    }

def live_p_above_mid(p: float, hi: float, lo: float) -> bool:
    return p >= (hi + lo) / 2.0

def get_last_signal() -> Dict[str, Any]:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT direction, confirmed_at, phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price FROM last_signal WHERE symbol='XAUUSD'")
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
                "max_favorable_price": float(row[7] or row[3] or 0)
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
        "max_favorable_price": 0.0
    }

def update_last_signal(
    direction: str,
    phase: str,
    entry_price: float = 0.0,
    sl_price: float = 0.0,
    tp_price: float = 0.0,
    tp2_price: float = 0.0,
    max_favorable_price: float = 0.0
):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO last_signal
                     (symbol, direction, confirmed_at, phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  ("XAUUSD", direction, datetime.now(EC_TZ).isoformat(), phase, entry_price, sl_price, tp_price, tp2_price, max_favorable_price))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"update_last_signal error: {e}")

# ==============================================================================
# MOTOR ALGORÍTMICO INTEGRAL TRENDSPIDER v16.0 (0 DELAY + ANTI-STOP-HUNT)
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
    tp_pct = float(_clean(tp_pct, "tp_pct", 0.12))
    sl_pct = float(_clean(sl_pct, "sl_pct", 0.08))
    horizon = int(_clean(horizon, "horizon", 30))
    truth_lock_ts = _clean(truth_lock_ts, "truth_lock_ts", "")
    if hasattr(truth_lock_ts, "default"):
        truth_lock_ts = ""

    live_price, feed_source = get_live_spot_price()
    update_current_1m_candle(live_price, "FEED")

    candles_1m = get_1m_candles(180)
    if len(candles_1m) < 45:
        sync_historical_1m_candles()
        candles_1m = get_1m_candles(180)

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

    # Calcular ATR tanto en 1m como en 5m para que el SL tenga tamaño real de M5 (evitando que lo saquen por mecha)
    candles_5m = aggregate_timeframe_candles(in_sample_candles, tf_minutes=5)
    atr_1m = trendlines_data["atr"]
    atr_5m = calc_atr(candles_5m, 14) if len(candles_5m) >= 6 else (atr_1m * 2.2)
    effective_atr = max(atr_5m, atr_1m * 1.8, 2.2)

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

    # 6. Módulo 6: Multi-Timeframe Analysis (M5 Tiempo Real + Alertas)
    mtfa_engine = TrendSpiderMTFAEngine(touch_cushion_atr_mult=0.35)
    m5_swing = detect_m5_swing_pullbacks(candles_5m, live_price)

    last_candle = in_sample_candles[-1]
    prev_candle = in_sample_candles[-2] if len(in_sample_candles) >= 2 else last_candle
    dynamic_alerts = mtfa_engine.evaluate_touch_cushion_alerts(
        current_candle=last_candle,
        prev_candle=prev_candle,
        trendlines=active_trendlines,
        fib_levels=fib_data.get("levels", {}),
        atr=effective_atr
    )

    # ==========================================================================
    # MOTOR DE PUNTUACIÓN Y CONFLUENCIA EN TIEMPO REAL
    # ==========================================================================
    buy_points = 0
    sell_points = 0
    confluences_audit = []

    m5_sig = m5_swing["signal"]
    if m5_sig in ["BUY_PULLBACK", "BUY_BREAKOUT"]:
        buy_points += 5
        confluences_audit.append({
            "module": "ESTRUCTURA_M5", "side": "COMPRA", "weight": 5,
            "title": f"🚀 {m5_swing['structure']}",
            "desc": m5_swing["reason"]
        })
    elif m5_sig in ["SELL_PULLBACK", "SELL_BREAKDOWN"]:
        sell_points += 5
        confluences_audit.append({
            "module": "ESTRUCTURA_M5", "side": "VENTA", "weight": 5,
            "title": f"📉 {m5_swing['structure']}",
            "desc": m5_swing["reason"]
        })

    # Layer B: Auto-Trendlines & Breakout / Bounce
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
        buy_points += 3
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "COMPRA", "weight": 3,
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
        sell_points += 3
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "VENTA", "weight": 3,
            "title": "RECHAZO LIMPIO EN RESISTENCIA FRACTAL (Bounce)",
            "desc": "Toque en la directriz superior seguido de rechazo bajista."
        })

    # Layer C: Auto-Fibonacci Golden Zone
    fib_gz = fib_data.get("golden_zone", {})
    if fib_gz.get("in_zone", False):
        if fib_data.get("impulse_direction") == "BULLISH" and last_candle["bullish"]:
            buy_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "COMPRA", "weight": 3,
                "title": f"ZONA DORADA OTE (${fib_gz.get('low')} - ${fib_gz.get('high')})",
                "desc": "Fin de retroceso en zona institucional con vela verde."
            })
        elif fib_data.get("impulse_direction") == "BEARISH" and not last_candle["bullish"]:
            sell_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "VENTA", "weight": 3,
                "title": f"ZONA DORADA OTE (${fib_gz.get('low')} - ${fib_gz.get('high')})",
                "desc": "Fin de rebote correctivo en zona dorada bajista con vela roja."
            })

    # Layer D: AI Strategy Lab
    ai_buy_prob = ai_strategy_data.get("buy_prob", 0.50)
    ai_sell_prob = ai_strategy_data.get("sell_prob", 0.50)
    ai_confidence = ai_strategy_data.get("ensemble_confidence", 50)

    if ai_buy_prob >= 0.58:
        buy_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "COMPRA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): PROBABILIDAD {ai_buy_prob*100:.0f}%",
            "desc": "Clasificador estadístico confirma ventaja compradora."
        })
    elif ai_sell_prob >= 0.58:
        sell_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "VENTA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): PROBABILIDAD {ai_sell_prob*100:.0f}%",
            "desc": "Clasificador estadístico confirma ventaja vendedora."
        })

    support_val = round(min(m5_swing.get("last_sl", live_price - 4.0), live_price - 1.5), 2)
    resistance_val = round(max(m5_swing.get("last_sh", live_price + 4.0), live_price + 1.5), 2)
    room_up = max(0.0, round(resistance_val - live_price, 2))
    room_down = max(0.0, round(live_price - support_val, 2))

    # ==========================================================================
    # GESTIÓN DEL CICLO DE VIDA Y STOP LOSS DETRÁS DEL SWING M5 (ANTI-BARRIDOS)
    # ==========================================================================
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price
    current_sl = last_sig["sl_price"]
    current_tp1 = last_sig["tp_price"]
    current_tp2 = last_sig["tp2_price"]
    max_fav = last_sig["max_favorable_price"] if last_sig["max_favorable_price"] > 1000 else entry_p

    # Calcular SL real en M5: detrás del último Swing Low/High M5 + colchón de $1.20 (entre $3.50 y $5.20 de margen)
    # Así una mecha de re-testeo en 1 minuto jamás te saca antes de que suba.
    buy_swing_sl = round(m5_swing.get("last_sl", live_price - 3.8) - 1.20, 2)
    sell_swing_sl = round(m5_swing.get("last_sh", live_price + 3.8) + 1.20, 2)

    sl_dist_buy = round(max(3.50, min(abs(live_price - buy_swing_sl), 5.20)), 2)
    sl_dist_sell = round(max(3.50, min(abs(sell_swing_sl - live_price), 5.20)), 2)
    tp1_distance = round(max(4.80, min(effective_atr * 2.0, 8.50)), 2)
    tp2_distance = round(max(8.00, min(effective_atr * 3.5, 14.0)), 2)

    final_dir = "ESPERA"
    alert_text = "⏸ ESPERANDO CONFIRMACIÓN ESTRUCTURAL M5"
    alert_type = "WAIT"
    alert_desc = f"Estructura M5: {m5_swing['structure']}. {m5_swing['reason']}"
    flip_reason = "Monitoreando estructura M5 en tiempo real"
    confidence_score = max(ai_confidence, 55)

    # 1. Monitoreo de Operación COMPRA ya abierta
    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        if live_price > max_fav:
            max_fav = live_price
            update_last_signal("COMPRA", "HOLD_COMPRA", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        # A. Si la estructura rompe a la baja tras acumular 3 velas (SELL_BREAKDOWN) -> GIRAR INMEDIATAMENTE A VENTA
        if m5_sig == "SELL_BREAKDOWN" or (sell_points >= 6 and sell_points >= buy_points + 3) or (live_price <= current_sl and current_sl > 1000):
            # Si hay ruptura bajista clara de acumulación, no solo cerramos compra sino que activamos alerta de salida inmediata / giro a venta
            new_sl = round(live_price + sl_dist_sell, 2)
            new_tp1 = round(live_price - tp1_distance, 2)
            new_tp2 = round(live_price - tp2_distance, 2)
            if m5_sig == "SELL_BREAKDOWN" or sell_points >= 6:
                update_last_signal("VENTA", "REVERSAL_TO_SELL", live_price, new_sl, new_tp1, new_tp2, live_price)
                log_signal_event("EXIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Cierre de COMPRA y Giro a VENTA por ruptura de acumulación M5 ({pnl:+.2f} USD)")
                log_signal_event("ENTER", "VENTA", live_price, new_sl, new_tp1, 0.0, m5_swing["reason"])
                return build_response(
                    direction="VENTA", confidence=92,
                    alert=f"🚨 CIERRA COMPRA Y GIRA A VENTA AHORA (${live_price:.2f})",
                    alert_type="EXIT",
                    alert_desc=f"¡Ruptura Bajista Confirmada! {m5_swing['reason']} Cierra la compra de inmediato.",
                    entry_p=live_price, sl=new_sl, tp1=new_tp1, tp2=new_tp2,
                    live_price=live_price, feed_source=feed_source, atr=effective_atr,
                    confluences=confluences_audit, trendlines_data=trendlines_data,
                    fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                    candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                    support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                    buy_score=buy_points, sell_score=sell_points, flip_reason="Ruptura de soporte M5 -> Giro a VENTA",
                    m5_swing=m5_swing
                )
            else:
                update_last_signal("ESPERA", "SL_COMPRA_EXECUTED", 0, 0, 0, 0, 0)
                log_signal_event("EXIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Stop Loss / Salida de protección COMPRA ({pnl:+.2f} USD)")
                return build_response(
                    direction="ESPERA", confidence=90,
                    alert=f"🛑 SALIR DE COMPRA AHORA ({pnl:+.2f} USD)",
                    alert_type="EXIT",
                    alert_desc=f"El precio perforó el soporte de seguridad (${current_sl:.2f}). Cierra la compra inmediatamente.",
                    entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                    live_price=live_price, feed_source=feed_source, atr=effective_atr,
                    confluences=confluences_audit, trendlines_data=trendlines_data,
                    fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                    candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                    support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                    buy_score=buy_points, sell_score=sell_points, flip_reason="Soporte roto",
                    m5_swing=m5_swing
                )

        # B. Proteger en Break-Even cuando avance >= +$2.50 USD
        if (max_fav - entry_p) >= 2.50 and current_sl < entry_p:
            current_sl = round(entry_p + 0.40, 2)
            update_last_signal("COMPRA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav)
            log_signal_event("BREAK_EVEN", "COMPRA", live_price, current_sl, current_tp1, pnl, "Stop Loss asegurado en Break-Even (+0.40 USD)")

        # C. Take Profit alcanzado
        if (live_price >= current_tp1 and current_tp1 > 1000) or (pnl >= 2.80 and m5_sig == "SELL_PULLBACK"):
            update_last_signal("ESPERA", "TP_COMPRA_EXECUTED", 0, 0, 0, 0, 0)
            log_signal_event("TAKE_PROFIT", "COMPRA", live_price, current_sl, current_tp1, pnl, f"Take Profit COMPRA logrado (+${pnl:.2f} USD)")
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"💰 SALIR EN GANANCIA COMPRA (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo alcanzado en ${live_price:.2f}. Asegura tu ganancia ahora.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=effective_atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP logrado",
                m5_swing=m5_swing
            )

        final_dir = "COMPRA"
        alert_text = f"🛡️ MANTENER COMPRA ({pnl:+.2f} USD)"
        alert_type = "ENTER"
        alert_desc = f"Entrada: ${entry_p:.2f} • SL Estructural M5: ${current_sl:.2f} • Meta TP1: ${current_tp1:.2f}."
        flip_reason = f"En COMPRA ({pnl:+.2f} USD)"
        confidence_score = 86

    # 2. Monitoreo de Operación VENTA ya abierta
    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        if live_price < max_fav:
            max_fav = live_price
            update_last_signal("VENTA", "HOLD_VENTA", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        # A. Si rompe al alza con fuerza (BUY_BREAKOUT) -> GIRAR A COMPRA O SALIR DE VENTA
        if m5_sig == "BUY_BREAKOUT" or (buy_points >= 6 and buy_points >= sell_points + 3) or (live_price >= current_sl and current_sl > 1000):
            new_sl = round(live_price - sl_dist_buy, 2)
            new_tp1 = round(live_price + tp1_distance, 2)
            new_tp2 = round(live_price + tp2_distance, 2)
            if m5_sig == "BUY_BREAKOUT" or buy_points >= 6:
                update_last_signal("COMPRA", "REVERSAL_TO_BUY", live_price, new_sl, new_tp1, new_tp2, live_price)
                log_signal_event("EXIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Cierre de VENTA y Giro a COMPRA por ruptura alcista M5 ({pnl:+.2f} USD)")
                log_signal_event("ENTER", "COMPRA", live_price, new_sl, new_tp1, 0.0, m5_swing["reason"])
                return build_response(
                    direction="COMPRA", confidence=92,
                    alert=f"🚨 CIERRA VENTA Y GIRA A COMPRA AHORA (${live_price:.2f})",
                    alert_type="EXIT",
                    alert_desc=f"¡Ruptura Alcista Confirmada! {m5_swing['reason']} Cierra la venta de inmediato.",
                    entry_p=live_price, sl=new_sl, tp1=new_tp1, tp2=new_tp2,
                    live_price=live_price, feed_source=feed_source, atr=effective_atr,
                    confluences=confluences_audit, trendlines_data=trendlines_data,
                    fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                    candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                    support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                    buy_score=buy_points, sell_score=sell_points, flip_reason="Ruptura alcista M5 -> Giro a COMPRA",
                    m5_swing=m5_swing
                )
            else:
                update_last_signal("ESPERA", "SL_VENTA_EXECUTED", 0, 0, 0, 0, 0)
                log_signal_event("EXIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Stop Loss / Salida de protección VENTA ({pnl:+.2f} USD)")
                return build_response(
                    direction="ESPERA", confidence=90,
                    alert=f"🛑 SALIR DE VENTA AHORA ({pnl:+.2f} USD)",
                    alert_type="EXIT",
                    alert_desc=f"El precio superó la resistencia de seguridad (${current_sl:.2f}). Cierra la venta inmediatamente.",
                    entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                    live_price=live_price, feed_source=feed_source, atr=effective_atr,
                    confluences=confluences_audit, trendlines_data=trendlines_data,
                    fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                    candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                    support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                    buy_score=buy_points, sell_score=sell_points, flip_reason="Resistencia rota",
                    m5_swing=m5_swing
                )

        if (entry_p - max_fav) >= 2.50 and current_sl > entry_p:
            current_sl = round(entry_p - 0.40, 2)
            update_last_signal("VENTA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav)
            log_signal_event("BREAK_EVEN", "VENTA", live_price, current_sl, current_tp1, pnl, "Stop Loss asegurado en Break-Even (+0.40 USD)")

        if (live_price <= current_tp1 and current_tp1 > 1000) or (pnl >= 2.80 and m5_sig == "BUY_PULLBACK"):
            update_last_signal("ESPERA", "TP_VENTA_EXECUTED", 0, 0, 0, 0, 0)
            log_signal_event("TAKE_PROFIT", "VENTA", live_price, current_sl, current_tp1, pnl, f"Take Profit VENTA logrado (+${pnl:.2f} USD)")
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"💰 SALIR EN GANANCIA VENTA (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo bajista alcanzado en ${live_price:.2f}. Asegura tu ganancia ahora.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=effective_atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP logrado",
                m5_swing=m5_swing
            )

        final_dir = "VENTA"
        alert_text = f"🛡️ MANTENER VENTA ({pnl:+.2f} USD)"
        alert_type = "ENTER"
        alert_desc = f"Entrada: ${entry_p:.2f} • SL Estructural M5: ${current_sl:.2f} • Meta TP1: ${current_tp1:.2f}."
        flip_reason = f"En VENTA ({pnl:+.2f} USD)"
        confidence_score = 86

    # 3. Disparo de NUEVA Entrada desde ESPERA
    else:
        if buy_points >= 5 and buy_points >= sell_points + 3:
            final_dir = "COMPRA"
            entry_p = live_price
            current_sl = round(live_price - sl_dist_buy, 2)
            current_tp1 = round(live_price + tp1_distance, 2)
            current_tp2 = round(live_price + tp2_distance, 2)
            confidence_score = min(96, int(75 + (buy_points * 2.2)))
            alert_text = f"🚀 ENTRADA COMPRA CONFIRMADA ({m5_swing['structure']})"
            alert_type = "ENTER"
            alert_desc = f"{m5_swing['reason']} • SL protegido detrás del Swing Low M5 (${current_sl:.2f})."
            flip_reason = f"Nueva COMPRA en ${live_price:.2f}"
            update_last_signal("COMPRA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p)
            log_signal_event("ENTER", "COMPRA", entry_p, current_sl, current_tp1, 0.0, m5_swing["structure"] + ": " + m5_swing["reason"])

        elif sell_points >= 5 and sell_points >= buy_points + 3:
            final_dir = "VENTA"
            entry_p = live_price
            current_sl = round(live_price + sl_dist_sell, 2)
            current_tp1 = round(live_price - tp1_distance, 2)
            current_tp2 = round(live_price - tp2_distance, 2)
            confidence_score = min(96, int(75 + (sell_points * 2.2)))
            alert_text = f"📉 ENTRADA VENTA CONFIRMADA ({m5_swing['structure']})"
            alert_type = "ENTER"
            alert_desc = f"{m5_swing['reason']} • SL protegido detrás del Swing High M5 (${current_sl:.2f})."
            flip_reason = f"Nueva VENTA en ${live_price:.2f}"
            update_last_signal("VENTA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p)
            log_signal_event("ENTER", "VENTA", entry_p, current_sl, current_tp1, 0.0, m5_swing["structure"] + ": " + m5_swing["reason"])

        else:
            final_dir = "ESPERA"
            confidence_score = 55
            alert_text = f"⏸ ESPERA • {m5_swing['structure']}"
            alert_type = "WAIT"
            alert_desc = f"{m5_swing['reason']} (Compra {buy_points} pts / Venta {sell_points} pts)."
            flip_reason = "Esperando ruptura o confirmación de giro M5"

    return build_response(
        direction=final_dir, confidence=confidence_score,
        alert=alert_text, alert_type=alert_type, alert_desc=alert_desc,
        entry_p=entry_p if final_dir != "ESPERA" else live_price,
        sl=current_sl if final_dir != "ESPERA" else 0.0,
        tp1=current_tp1 if final_dir != "ESPERA" else 0.0,
        tp2=current_tp2 if final_dir != "ESPERA" else 0.0,
        live_price=live_price, feed_source=feed_source, atr=effective_atr,
        confluences=confluences_audit, trendlines_data=trendlines_data,
        fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
        candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
        support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
        buy_score=buy_points, sell_score=sell_points, flip_reason=flip_reason,
        m5_swing=m5_swing
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
    m5_swing: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {
        "symbol": "XAUUSD",
        "direction": direction,
        "entry": round(entry_p, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "dist": round(abs(entry_p - sl), 2) if sl > 0 else round(atr * 1.5, 2),
        "tp_dist": round(abs(tp1 - entry_p), 2) if tp1 > 0 else round(atr * 2.2, 2),
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
        "signal_history": get_signal_history(25),
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
        "message": "EDGEALERT - TRENDSPIDER REALTIME M5 ENGINE v16.0",
        "version": "16.0"
    }

@app.get("/health")
def health():
    return {"status": "ok", "symbol": "XAUUSD", "version": "16.0"}

@app.get("/signals/history")
def signals_history_endpoint():
    return get_signal_history(30)

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
        result = analyze_market_trendspider(
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
            "dist": 3.8, "tp_dist": 5.5,
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
    async def monitor_loop():
        ticks = 0
        while True:
            try:
                p, _ = get_live_spot_price()
                update_current_1m_candle(p, "FEED")
                analyze_market_trendspider()
                ticks += 1
                if ticks % 30 == 0:
                    sync_historical_1m_candles()
            except Exception as e:
                print(f"Monitor loop error: {e}")
            await asyncio.sleep(6)
    asyncio.create_task(monitor_loop())
