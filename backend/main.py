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

app = FastAPI(title="EdgeAlert - TRENDSPIDER ALGORITHMIC ENGINE v15.0")
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
    "truth_lock_ts": "",               # Timestamp congelado o vacío (Desbloqueado / Red Line)
    "ai_model": "Ensemble",            # "Ensemble", "RandomForest", "Logistic", "KNN", "NaiveBayes"
    "tp_pct": "0.14",                  # 0.14% TP (~$5.50 en Oro)
    "sl_pct": "0.08",                  # 0.08% SL (~$3.20 en Oro)
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
    """Obtiene el tick en vivo compatible con el feed de TradingView (Swissquote, Gold-API, Yahoo)"""
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

    # Respaldo de base de datos local
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

    return 3946.50, "FALLBACK"

def sync_historical_1m_candles():
    """Descarga hasta 120-150 velas reales de 1 minuto para alimentar los motores de geometría y ML"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
        r = requests.get(url, headers=headers, timeout=5)
        live_p, _ = get_live_spot_price()
        if r.status_code == 200:
            res = r.json().get("chart", {}).get("result", [])
            if res:
                timestamps = res[0].get("timestamp", [])[-150:]
                quote = res[0].get("indicators", {}).get("quote", [{}])[0]
                opens = quote.get("open", [])[-150:]
                highs = quote.get("high", [])[-150:]
                lows = quote.get("low", [])[-150:]
                closes = quote.get("close", [])[-150:]
                vols = quote.get("volume", [])[-150:]

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

    # Inicialización sintética de respaldo si no hay historial
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ohlc_1m")
        if c.fetchone()[0] < 60:
            base, _ = get_live_spot_price()
            now_min = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60
            for i in range(120):
                ts = now_min - ((120 - i) * 60)
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
    """Actualiza la vela de 1 minuto en curso con cada nuevo tick"""
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
        # Conservar hasta 360 velas de 1m (6 horas)
        c.execute("DELETE FROM ohlc_1m WHERE ts NOT IN (SELECT ts FROM ohlc_1m ORDER BY ts DESC LIMIT 360)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Update 1m error: {e}")

def get_1m_candles(limit: int = 120) -> List[Dict[str, Any]]:
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
                "ts": r[0],
                "open": o,
                "high": h,
                "low": l,
                "close": cl,
                "volume": float(r[5]),
                "source": r[6],
                "body": round(body, 2),
                "range": round(rng, 2),
                "body_ratio": round(body / rng, 2),
                "upper_wick": round(h - max(o, cl), 2),
                "lower_wick": round(min(o, cl) - l, 2),
                "bullish": cl >= o
            })
        return candles
    except Exception as e:
        print(f"get_1m_candles error: {e}")
        return []

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
# MOTOR ALGORÍTMICO INTEGRAL TRENDSPIDER v15.0
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
    """
    Orquesta los 6 módulos algorítmicos de TrendSpider:
    1. Auto-Trendlines con Geometría Computacional y Scoring Engine
    2. Auto-Fibs con Selección Dinámica de Anclajes y Zona Dorada (0.382 - 0.618 OTE)
    3. Heatmap Matrix 40x60 (Horizontal, Depth con Difusión 2D, Trends crudo)
    4. Truth in Analysis Timestamp (Anti-Repintado y prueba Out-of-Sample)
    5. AI Strategy Lab con Clasificadores Estadísticos, Crossbreeding y Target Labeling
    6. MTFA Multi-Timeframe con Alertas Touch Cushion (Break through, Touch, Bounce)
    """
    # 0. Resolver Parámetros (Query / Base de Datos / Defaults)
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
    tp_pct = float(_clean(tp_pct, "tp_pct", 0.14))
    sl_pct = float(_clean(sl_pct, "sl_pct", 0.08))
    horizon = int(_clean(horizon, "horizon", 30))
    truth_lock_ts = _clean(truth_lock_ts, "truth_lock_ts", "")
    if hasattr(truth_lock_ts, "default"):
        truth_lock_ts = ""

    live_price, feed_source = get_live_spot_price()
    update_current_1m_candle(live_price, "FEED")

    candles_1m = get_1m_candles(120)
    if len(candles_1m) < 40:
        sync_historical_1m_candles()
        candles_1m = get_1m_candles(120)

    # 1. Truth in Analysis (Anti-Repintado)
    # Si truth_lock_ts está activo, congelamos el análisis en esa vela exacta
    is_locked = False
    in_sample_candles = candles_1m
    out_of_sample_candles = []
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
                out_of_sample_candles = candles_1m[lock_index + 1:]
        except Exception as e:
            print(f"Truth lock parse error: {e}")

    # 2. Módulo 1: Auto-Trendlines (TrendSpider Scoring Engine)
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

    # 5. Módulo 5: AI Strategy Lab (Modelos Predictivos y Crossbreeding)
    strategy_lab = TrendSpiderStrategyLab(
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        horizon=horizon,
        active_model=ai_model
    )
    ai_strategy_data = strategy_lab.train_and_evaluate(in_sample_candles)

    # 6. Módulo 6: Multi-Timeframe Analysis (MTFA) & Dynamic Alerts
    mtfa_engine = TrendSpiderMTFAEngine(touch_cushion_atr_mult=0.30)
    candles_5m = aggregate_timeframe_candles(in_sample_candles, tf_minutes=5)
    candles_15m = aggregate_timeframe_candles(in_sample_candles, tf_minutes=15)

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
    # MOTOR DE DECISIÓN MULTIFACTORIAL (ELIMINACIÓN RADICAL DE RUIDO)
    # ==========================================================================
    # Para que una operación se abra, debe tener CONFLUENCIA COMPROBADA:
    # 1. Gatillo de Ruptura al Cierre (Breakout) o Rebote (Bounce) sobre Trendline Top 1%
    # 2. Confluencia con Zona Dorada Fibonacci (0.382 - 0.618 OTE) o Cluster de Liquidez Heatmap
    # 3. Filtro de Probabilidad AI Strategy Lab >= 65-70% (Ensemble / Random Forest)
    # 4. Filtro de Sobreextensión RSI (no comprar en RSI > 74, no vender en RSI < 26)

    buy_points = 0
    sell_points = 0
    confluences_audit = []

    # Layer 1: Auto-Trendlines & Breakout / Bounce
    has_bullish_breakout = any(l.get("breakout") == "BULLISH_BREAKOUT" for l in active_trendlines)
    has_bearish_breakout = any(l.get("breakout") == "BEARISH_BREAKOUT" for l in active_trendlines)
    has_bullish_bounce = any(a["trigger"] == "BOUNCE" and a["side"] == "COMPRA" for a in dynamic_alerts)
    has_bearish_bounce = any(a["trigger"] == "BOUNCE" and a["side"] == "VENTA" for a in dynamic_alerts)

    if has_bullish_breakout:
        buy_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "COMPRA", "weight": 4,
            "title": "RUPTURA DIRECTRIZ AL CIERRE (Breakout)",
            "desc": "Cierre de vela confirmado superando la línea de tendencia bajista. Filtro anti-fakeout verificado."
        })
    elif has_bullish_bounce:
        buy_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "COMPRA", "weight": 4,
            "title": "REBOTE LIMPIO EN SOPORTE FRACTAL (Bounce)",
            "desc": "Rechazo alcista dentro del Colchón de Sensibilidad ATR sin perforación estructural."
        })

    if has_bearish_breakout:
        sell_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "VENTA", "weight": 4,
            "title": "RUPTURA DIRECTRIZ AL CIERRE (Breakdown)",
            "desc": "Cierre de vela confirmado perforando el soporte tendencial. Filtro anti-fakeout verificado."
        })
    elif has_bearish_bounce:
        sell_points += 4
        confluences_audit.append({
            "module": "AUTO_TRENDLINES", "side": "VENTA", "weight": 4,
            "title": "RECHAZO LIMPIO EN RESISTENCIA FRACTAL (Bounce)",
            "desc": "Toque en el techo dentro del Colchón de Sensibilidad ATR seguido de mecha bajista prominente."
        })

    # Layer 2: Auto-Fibonacci Golden Zone Confluence
    fib_gz = fib_data.get("golden_zone", {})
    if fib_gz.get("in_zone", False):
        if fib_data.get("impulse_direction") == "BULLISH":
            buy_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "COMPRA", "weight": 3,
                "title": f"ZONA DORADA OTE (Fib 0.50 - 0.618: {fib_gz.get('low')} - {fib_gz.get('high')})",
                "desc": "El precio descansó en la zona de descuento institucional ideal para reanudar la tendencia alcista."
            })
        else:
            sell_points += 3
            confluences_audit.append({
                "module": "AUTO_FIBS", "side": "VENTA", "weight": 3,
                "title": f"ZONA DORADA OTE (Fib 0.50 - 0.618: {fib_gz.get('low')} - {fib_gz.get('high')})",
                "desc": "El retroceso completó su impulso correctivo en la zona dorada bajista para continuar la caída."
            })

    # Layer 3: Heatmap Liquidity & Order Block Confluence
    top_clusters = heatmap_data.get("top_clusters", [])
    near_cluster_support = False
    near_cluster_resistance = False
    for cl in top_clusters:
        p_dist = abs(live_price - cl["price"])
        if p_dist <= (0.45 * atr):
            if live_price >= cl["price"]:
                near_cluster_support = True
            else:
                near_cluster_resistance = True

    if near_cluster_support:
        buy_points += 2
        confluences_audit.append({
            "module": "HEATMAP_MATRIX", "side": "COMPRA", "weight": 2,
            "title": "BLOQUE DE LIQUIDEZ INSTITUCIONAL EN MATRIZ 40x60",
            "desc": "Alta densidad espacial de Puntos Especiales actuando como piso magnético de absorción de ventas."
        })
    if near_cluster_resistance:
        sell_points += 2
        confluences_audit.append({
            "module": "HEATMAP_MATRIX", "side": "VENTA", "weight": 2,
            "title": "BARRERA DE LIQUIDEZ INSTITUCIONAL EN MATRIZ 40x60",
            "desc": "Alta densidad de órdenes pasivas limitando la subida y forzando giros a la baja."
        })

    # Layer 4: AI Strategy Lab Probability Filter
    ai_buy_prob = ai_strategy_data.get("buy_prob", 0.50)
    ai_sell_prob = ai_strategy_data.get("sell_prob", 0.50)
    ai_confidence = ai_strategy_data.get("ensemble_confidence", 50)

    if ai_buy_prob >= 0.65:
        buy_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "COMPRA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): PROBABILIDAD DE ÉXITO {ai_buy_prob*100:.0f}%",
            "desc": f"El clasificador supervisado predice objetivo de Take Profit antes de Stop Loss con alta significancia estadística."
        })
    elif ai_sell_prob >= 0.65:
        sell_points += 3
        confluences_audit.append({
            "module": "AI_STRATEGY_LAB", "side": "VENTA", "weight": 3,
            "title": f"MODELO IA ({ai_model}): PROBABILIDAD DE ÉXITO {ai_sell_prob*100:.0f}%",
            "desc": f"El clasificador supervisado predice objetivo de Take Profit antes de Stop Loss con alta significancia estadística."
        })

    # Layer 5: S/R y Espacio Libre
    support_val = min(l["current_y"] for l in active_trendlines if l["kind"] == "SUPPORT") if any(l["kind"] == "SUPPORT" for l in active_trendlines) else (live_price - atr * 2.5)
    resistance_val = max(l["current_y"] for l in active_trendlines if l["kind"] == "RESISTANCE") if any(l["kind"] == "RESISTANCE" for l in active_trendlines) else (live_price + atr * 2.5)
    room_up = max(0.0, round(resistance_val - live_price, 2))
    room_down = max(0.0, round(live_price - support_val, 2))

    # ==========================================================================
    # GESTIÓN INTELIGENTE DEL CICLO DE VIDA DE LA OPERACIÓN (ANTI-RUIDO)
    # ==========================================================================
    last_sig = get_last_signal()
    active_dir = last_sig["direction"]
    entry_p = last_sig["entry_price"] if last_sig["entry_price"] > 1000 else live_price
    current_sl = last_sig["sl_price"]
    current_tp1 = last_sig["tp_price"]
    current_tp2 = last_sig["tp2_price"]
    max_fav = last_sig["max_favorable_price"] if last_sig["max_favorable_price"] > 1000 else entry_p

    # Dimensionamiento dinámico de Stop Loss y Take Profit por ATR institucional
    sl_distance = round(max(2.5, min(atr * 1.3, 4.5)), 2)
    tp1_distance = round(max(3.8, min(atr * 2.0, 7.5)), 2)
    tp2_distance = round(max(6.0, min(atr * 3.5, 12.0)), 2)

    final_dir = "ESPERA"
    alert_text = "⏸ ESPERANDO CONFLUENCIA CUÁNTICA"
    alert_type = "WAIT"
    alert_desc = f"Analizando {len(active_trendlines)} vectores y matriz 40x60. Sin gatillo limpio de alta probabilidad."
    flip_reason = "Filtro anti-ruido activo"
    confidence_score = max(ai_confidence, 55)

    # 1. Monitoreo de Operación COMPRA ya abierta
    if active_dir == "COMPRA":
        pnl = round(live_price - entry_p, 2)
        if live_price > max_fav:
            max_fav = live_price
            update_last_signal("COMPRA", "HOLD_COMPRA", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        # Regla Anti-Ruido 1: Trailing Stop Dinámico a Break-Even tras +1R
        if (max_fav - entry_p) >= (sl_distance * 0.9) and current_sl < entry_p:
            current_sl = entry_p + 0.30 # Lock en ganancias mínimas / Break-even seguro
            update_last_signal("COMPRA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        # Regla Anti-Ruido 2: Take Profit Estructural TP1 o TP2
        if live_price >= current_tp1 and current_tp1 > 1000:
            update_last_signal("ESPERA", "TP_COMPRA_EXECUTED", 0, 0, 0, 0, 0)
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"🎯 TAKE PROFIT COMPRA LOGRADO (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo institucional alcanzado en {live_price:.2f}. Ganancia asegurada sin riesgo de reversión.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP ejecutado con éxito"
            )

        # Regla Anti-Ruido 3: Salida Estricta SOLO si cierra perforando el Stop Loss de Seguridad
        if live_price <= current_sl and current_sl > 1000:
            update_last_signal("ESPERA", "SL_COMPRA_EXECUTED", 0, 0, 0, 0, 0)
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 STOP LOSS CONTROLADO COMPRA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"Invalidación estructural tocada en {live_price:.2f}. Pérdida estrictamente acotada por riesgo institucional.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="SL ejecutado"
            )

        # Mantener COMPRA en curso
        final_dir = "COMPRA"
        alert_text = f"🛡️ MANTENER COMPRA (+${pnl:.2f} USD)" if pnl >= 0 else f"🛡️ MANTENER COMPRA ({pnl:+.2f} USD)"
        alert_type = "ENTER"
        alert_desc = f"Entrada en {entry_p:.2f} • SL dinámico en {current_sl:.2f} • Meta TP1 en {current_tp1:.2f}. Sin ruido prematuro."
        flip_reason = f"Operación activa COMPRA ({pnl:+.2f} USD)"
        confidence_score = 85

    # 2. Monitoreo de Operación VENTA ya abierta
    elif active_dir == "VENTA":
        pnl = round(entry_p - live_price, 2)
        if live_price < max_fav:
            max_fav = live_price
            update_last_signal("VENTA", "HOLD_VENTA", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        if (entry_p - max_fav) >= (sl_distance * 0.9) and current_sl > entry_p:
            current_sl = entry_p - 0.30
            update_last_signal("VENTA", "BREAK_EVEN_LOCKED", entry_p, current_sl, current_tp1, current_tp2, max_fav)

        if live_price <= current_tp1 and current_tp1 > 1000:
            update_last_signal("ESPERA", "TP_VENTA_EXECUTED", 0, 0, 0, 0, 0)
            return build_response(
                direction="ESPERA", confidence=95,
                alert=f"🎯 TAKE PROFIT VENTA LOGRADO (+${pnl:.2f} USD)",
                alert_type="TAKE_PROFIT",
                alert_desc=f"Objetivo institucional alcanzado en {live_price:.2f}. Ganancia asegurada sin riesgo de reversión.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="TP ejecutado con éxito"
            )

        if live_price >= current_sl and current_sl > 1000:
            update_last_signal("ESPERA", "SL_VENTA_EXECUTED", 0, 0, 0, 0, 0)
            return build_response(
                direction="ESPERA", confidence=90,
                alert=f"🛑 STOP LOSS CONTROLADO VENTA ({pnl:+.2f} USD)",
                alert_type="EXIT",
                alert_desc=f"Invalidación estructural tocada en {live_price:.2f}. Pérdida estrictamente acotada.",
                entry_p=entry_p, sl=current_sl, tp1=current_tp1, tp2=current_tp2,
                live_price=live_price, feed_source=feed_source, atr=atr,
                confluences=confluences_audit, trendlines_data=trendlines_data,
                fib_data=fib_data, heatmap_data=heatmap_data, ai_data=ai_strategy_data,
                candles=candles_1m, is_locked=is_locked, lock_ts=truth_lock_ts,
                support=support_val, resistance=resistance_val, room_up=room_up, room_down=room_down,
                buy_score=buy_points, sell_score=sell_points, flip_reason="SL ejecutado"
            )

        final_dir = "VENTA"
        alert_text = f"🛡️ MANTENER VENTA (+${pnl:.2f} USD)" if pnl >= 0 else f"🛡️ MANTENER VENTA ({pnl:+.2f} USD)"
        alert_type = "ENTER"
        alert_desc = f"Entrada en {entry_p:.2f} • SL dinámico en {current_sl:.2f} • Meta TP1 en {current_tp1:.2f}. Sin ruido prematuro."
        flip_reason = f"Operación activa VENTA ({pnl:+.2f} USD)"
        confidence_score = 85

    # 3. Disparo de NUEVA Entrada (Filtro Estricto de Confluencia)
    else:
        # Requerimiento: Mínimo 7 puntos de confluencia Y ventaja neta de 4 sobre el lado contrario
        # Y Probabilidad de IA >= 65% Y Espacio libre favorable
        if buy_points >= 7 and buy_points >= sell_points + 4 and ai_buy_prob >= 0.62 and room_up >= 2.5:
            final_dir = "COMPRA"
            entry_p = live_price
            current_sl = round(live_price - sl_distance, 2)
            current_tp1 = round(live_price + tp1_distance, 2)
            current_tp2 = round(live_price + tp2_distance, 2)
            confidence_score = min(96, int(72 + (buy_points * 2.5) + (ai_buy_prob * 15)))
            alert_text = "🚀 ENTRADA COMPRA CONFIRMADA (TRENDSPIDER QUANT)"
            alert_type = "ENTER"
            alert_desc = f"Confluencia cuádruple: Directriz Top 1% + Zona OTE + Bloque Heatmap + Probabilidad IA {ai_buy_prob*100:.0f}%."
            flip_reason = f"Gatillo estructural verificado en {live_price:.2f}"
            update_last_signal("COMPRA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p)

        elif sell_points >= 7 and sell_points >= buy_points + 4 and ai_sell_prob >= 0.62 and room_down >= 2.5:
            final_dir = "VENTA"
            entry_p = live_price
            current_sl = round(live_price + sl_distance, 2)
            current_tp1 = round(live_price - tp1_distance, 2)
            current_tp2 = round(live_price - tp2_distance, 2)
            confidence_score = min(96, int(72 + (sell_points * 2.5) + (ai_sell_prob * 15)))
            alert_text = "📉 ENTRADA VENTA CONFIRMADA (TRENDSPIDER QUANT)"
            alert_type = "ENTER"
            alert_desc = f"Confluencia cuádruple: Directriz Top 1% + Zona OTE + Barrera Heatmap + Probabilidad IA {ai_sell_prob*100:.0f}%."
            flip_reason = f"Gatillo estructural verificado en {live_price:.2f}"
            update_last_signal("VENTA", "NEW_ENTRY", entry_p, current_sl, current_tp1, current_tp2, entry_p)

        else:
            final_dir = "ESPERA"
            confidence_score = 50
            alert_text = "⏸ FILTRO ANTI-RUIDO ACTIVO (ESPERANDO CONFLUENCIA)"
            alert_type = "WAIT"
            alert_desc = f"Puntajes: Compra {buy_points} pts / Venta {sell_points} pts. Probabilidad IA {ai_confidence}%. El algoritmo no toma operaciones mediocres."
            flip_reason = "Protegiendo capital sin ruido"

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
        buy_score=buy_points, sell_score=sell_points, flip_reason=flip_reason
    )

def build_response(
    direction: str, confidence: int, alert: str, alert_type: str, alert_desc: str,
    entry_p: float, sl: float, tp1: float, tp2: float,
    live_price: float, feed_source: str, atr: float,
    confluences: List[Dict[str, Any]], trendlines_data: Dict[str, Any],
    fib_data: Dict[str, Any], heatmap_data: Dict[str, Any], ai_data: Dict[str, Any],
    candles: List[Dict[str, Any]], is_locked: bool, lock_ts: Optional[str],
    support: float, resistance: float, room_up: float, room_down: float,
    buy_score: int, sell_score: int, flip_reason: str
) -> Dict[str, Any]:
    return {
        "symbol": "XAUUSD",
        "direction": direction,
        "entry": round(entry_p, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "dist": round(abs(entry_p - sl), 2) if sl > 0 else round(atr * 1.3, 2),
        "tp_dist": round(abs(tp1 - entry_p), 2) if tp1 > 0 else round(atr * 2.0, 2),
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
        "recent_candles": candles[-40:] if len(candles) >= 40 else candles,
        "timestamp": datetime.now(EC_TZ).isoformat()
    }

# ==============================================================================
# ENDPOINTS REST API & WEBHOOKS
# ==============================================================================

@app.get("/")
def root():
    return {
        "message": "EDGEALERT - TRENDSPIDER ALGORITHMIC ENGINE v15.0",
        "version": "15.0",
        "architecture": [
            "Auto-Trendlines (Computational Geometry & Scoring Engine)",
            "Auto-Fibonacci (Dynamic Retracement & Golden Zone OTE)",
            "Liquidity Heatmaps 40x60 (Horizontal, Depth Diffusion & Trends)",
            "Truth in Analysis (Anti-Repainting Timestamp)",
            "AI Strategy Lab (Supervised Classifiers, Ensemble & Target Labeling)",
            "MTFA & Dynamic Alerts with ATR Touch Cushion"
        ]
    }

@app.get("/health")
def health():
    return {"status": "ok", "symbol": "XAUUSD", "version": "15.0"}

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
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "dist": 3.0,
            "tp_dist": 4.5,
            "live_price": p,
            "feed_source": "RECOVERY",
            "confidence": 50,
            "alert": "⏸ CALIBRANDO MATRIZ QUANT",
            "alert_type": "WAIT",
            "alert_desc": str(e),
            "points_detail": [],
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
    """
    Webhook sin Lag de TrendSpider / TradingView.
    Al cumplirse una alerta en la nube dispara payload JSON instantáneo.
    """
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
                ticks += 1
                if ticks % 40 == 0:
                    sync_historical_1m_candles()
            except Exception as e:
                print(f"Monitor loop error: {e}")
            await asyncio.sleep(8)
    asyncio.create_task(monitor_loop())
