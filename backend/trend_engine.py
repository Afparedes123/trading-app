import math
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

def calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    """Calcula Average True Range (ATR) de 14 periodos"""
    if len(candles) < 2:
        return 1.8
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        pc = candles[i - 1]["close"]
        tr = max(c["high"] - c["low"], abs(c["high"] - pc), abs(c["low"] - pc))
        trs.append(tr)
    sub = trs[-period:] if len(trs) >= period else trs
    return round(max(float(sum(sub)) / len(sub), 0.5), 2)

class TrendSpiderAutoTrendlines:
    """
    Motor de Detección y Puntuación de Estructura (Auto-Trendlines)
    Basado en geometría computacional sobre series temporales, matrices de pivotes fractales,
    filtros dinámicos de volatilidad basados en ATR(14) y motor de scoring matemático.
    """
    def __init__(
        self,
        analysis_type: str = "Standard",      # "Original", "Standard", "Enhanced"
        drawing_input: str = "Wick",          # "Wick" (H/L) o "Body" (O/C)
        island_gaps: str = "Respect",         # "Respect" o "Ignore"
        quality_filter: str = "Most Relevant", # "Most Relevant" (Top 1%), "Moderately Relevant" (Top 10%), "Unfiltered"
        lines_proximity_factor: float = 3.5,  # k * ATR(14)
        atr_island_mult: float = 3.0          # 3 * ATR(14) para declarar saltos de liquidez
    ):
        self.analysis_type = analysis_type
        self.drawing_input = drawing_input
        self.island_gaps = island_gaps
        self.quality_filter = quality_filter
        self.lines_proximity_factor = lines_proximity_factor
        self.atr_island_mult = atr_island_mult

        # Ventana de pivotes (HH/LL Numbers) según Analysis Type
        if analysis_type.lower() == "original":
            self.window_n = 7   # Macro tendencias, filtra ruido intradía
        elif analysis_type.lower() == "enhanced":
            self.window_n = 3   # Microestructuras, alta sensibilidad scalping
        else:
            self.window_n = 5   # Standard: balance ponderado

    def _get_candle_extremes(self, candle: Dict[str, Any]) -> Tuple[float, float]:
        """Obtiene extremos según Drawing Input: Wick (H/L) vs Body (O/C)"""
        if self.drawing_input.lower() == "body":
            high_val = max(candle["open"], candle["close"])
            low_val = min(candle["open"], candle["close"])
        else:
            high_val = candle["high"]
            low_val = candle["low"]
        return float(high_val), float(low_val)

    def detect_pivots(self, candles: List[Dict[str, Any]], window: int) -> Tuple[List[int], List[int]]:
        """
        Detecta pivotes fractales de máximos y mínimos con ventana simétrica de 'window' barras
        """
        n = len(candles)
        pivot_highs = []
        pivot_lows = []
        if n < window * 2 + 1:
            return pivot_highs, pivot_lows

        for i in range(window, n - window):
            h_curr, l_curr = self._get_candle_extremes(candles[i])
            is_high = True
            is_low = True
            for k in range(1, window + 1):
                h_prev, l_prev = self._get_candle_extremes(candles[i - k])
                h_next, l_next = self._get_candle_extremes(candles[i + k])
                if h_curr < h_prev or h_curr < h_next:
                    is_high = False
                if l_curr > l_prev or l_curr > l_next:
                    is_low = False
            if is_high:
                pivot_highs.append(i)
            if is_low:
                pivot_lows.append(i)

        return pivot_highs, pivot_lows

    def detect_island_gaps(self, candles: List[Dict[str, Any]], atr: float) -> List[int]:
        """
        Detecta barras donde el salto entre el cierre previo y la apertura actual > 3 * ATR(14)
        """
        gap_indices = []
        threshold = self.atr_island_mult * atr
        for i in range(1, len(candles)):
            gap = abs(candles[i]["open"] - candles[i - 1]["close"])
            if gap >= threshold:
                gap_indices.append(i)
        return gap_indices

    def evaluate_trendline(
        self,
        candles: List[Dict[str, Any]],
        idx1: int,
        idx2: int,
        kind: str, # "RESISTANCE" o "SUPPORT"
        pivots_n: List[int],
        pivots_2n: List[int],
        island_gaps: List[int],
        atr: float
    ) -> Optional[Dict[str, Any]]:
        """
        Evalúa y calcula las variables internas exactas de TrendSpider para un vector candidato.
        """
        series_len = len(candles)
        if idx1 >= idx2 or idx2 >= series_len:
            return None

        # Si Island Gaps = Respect, prohibición estricta de trazar líneas que crucen un gap
        if self.island_gaps.lower() == "respect":
            for gap_idx in island_gaps:
                if idx1 < gap_idx <= idx2:
                    return None

        h1, l1 = self._get_candle_extremes(candles[idx1])
        h2, l2 = self._get_candle_extremes(candles[idx2])

        y1 = h1 if kind == "RESISTANCE" else l1
        y2 = h2 if kind == "RESISTANCE" else l2

        slope = (y2 - y1) / float(idx2 - idx1)

        # Variables internas de TrendSpider
        length = series_len - 1 - idx1 # barras cubiertas desde origen
        hits = 0
        points = 0
        points2x = 0
        bounce_up = 0
        peaks_up = 0
        bounce_down = 0
        peaks_down = 0
        violations = 0
        deviations = []

        touch_tolerance = max(0.18 * atr, 0.25)
        long_candle_threshold = 1.5 * atr

        # Proyectar el vector a lo largo de toda la serie desde idx1
        for i in range(idx1, series_len):
            proj_y = y1 + slope * (i - idx1)
            c = candles[i]
            hi, lo = self._get_candle_extremes(c)
            mid = (c["high"] + c["low"]) / 2.0
            dev = abs(proj_y - mid) / max(proj_y, 1.0)
            deviations.append(dev)

            # Comprobar si coincide con pivotes
            if i in pivots_n and abs((hi if kind == "RESISTANCE" else lo) - proj_y) <= touch_tolerance * 1.5:
                points += 1
            if i in pivots_2n and abs((hi if kind == "RESISTANCE" else lo) - proj_y) <= touch_tolerance * 1.5:
                points2x += 1

            if kind == "RESISTANCE":
                # Resistencia: evaluamos contactos superiores y violaciones
                diff = abs(c["high"] - proj_y)
                if diff <= touch_tolerance:
                    hits += 1
                    # bounceUp: High toca la línea pero no los adyacentes
                    prev_hi = candles[i - 1]["high"] if i > 0 else 0
                    next_hi = candles[i + 1]["high"] if i < series_len - 1 else 0
                    prev_y = y1 + slope * ((i - 1) - idx1)
                    next_y = y1 + slope * ((i + 1) - idx1)
                    if abs(prev_hi - prev_y) > touch_tolerance and abs(next_hi - next_y) > touch_tolerance:
                        bounce_up += 1
                        # peaksUp: vela larga donde High_actual - High_adyacente > 1.5 * ATR
                        if max(c["high"] - prev_hi, c["high"] - next_hi) > long_candle_threshold:
                            peaks_up += 1

                # Violación: cuerpo de la vela cruza y vulnera la línea
                candle_body_max = max(c["open"], c["close"])
                if candle_body_max > proj_y + touch_tolerance * 0.5:
                    violations += 1

            else: # SUPPORT
                diff = abs(c["low"] - proj_y)
                if diff <= touch_tolerance:
                    hits += 1
                    prev_lo = candles[i - 1]["low"] if i > 0 else 999999
                    next_lo = candles[i + 1]["low"] if i < series_len - 1 else 999999
                    prev_y = y1 + slope * ((i - 1) - idx1)
                    next_y = y1 + slope * ((i + 1) - idx1)
                    if abs(prev_lo - prev_y) > touch_tolerance and abs(next_lo - next_y) > touch_tolerance:
                        bounce_down += 1
                        # peaksDown: rechazo limpio prominente > 1.5 * ATR
                        if max(prev_lo - c["low"], next_lo - c["low"]) > long_candle_threshold:
                            peaks_down += 1

                candle_body_min = min(c["open"], c["close"])
                if candle_body_min < proj_y - touch_tolerance * 0.5:
                    violations += 1

        # Filtro de Proximidad por ATR: descartar líneas si se alejan más de k * ATR del precio reciente
        current_proj_y = y1 + slope * (series_len - 1 - idx1)
        latest_price = candles[-1]["close"]
        if abs(current_proj_y - latest_price) > (self.lines_proximity_factor * atr):
            return None

        # Si tiene demasiadas violaciones respecto a su longitud, descartar
        if violations > max(2, int(length * 0.15)):
            return None

        # Cuantiles de desviación (priceDev25, priceDev50, priceDev75)
        devs_arr = np.array(deviations) if deviations else np.array([0.0])
        price_dev25 = float(np.percentile(devs_arr, 25))
        price_dev50 = float(np.percentile(devs_arr, 50))
        price_dev75 = float(np.percentile(devs_arr, 75))

        # Fórmula matemática de Scoring de TrendSpider
        # Ponderación positiva: hits, points, points2x, peaks, length / seriesLength
        # Penalización exponencial: violations y dispersión priceDev50
        score = (
            (hits * 2.5) +
            (points * 3.5) +
            (points2x * 5.5) +
            ((peaks_up + peaks_down) * 4.0) +
            ((bounce_up + bounce_down) * 1.5) +
            ((float(length) / max(series_len, 1)) * 18.0) -
            ((violations ** 1.4) * 8.0) -
            (price_dev50 * 60.0)
        )

        # Breakout Detection (Anti-Fakeouts)
        # Regla estricta: Una ruptura SOLO se valida si el Close finaliza al lado opuesto del vector.
        # Perforaciones con mecha sin cierre NO se marcan como Breakout.
        latest_c = candles[-1]
        breakout = "NONE"
        if kind == "RESISTANCE":
            if latest_c["close"] > current_proj_y:
                breakout = "BULLISH_BREAKOUT" # Círculo verde al alza
            elif latest_c["high"] > current_proj_y and latest_c["close"] <= current_proj_y:
                breakout = "WICK_FAKEOUT"     # Rechazo por mecha (falso quiebre)
        else: # SUPPORT
            if latest_c["close"] < current_proj_y:
                breakout = "BEARISH_BREAKOUT" # Círculo rojo a la baja
            elif latest_c["low"] < current_proj_y and latest_c["close"] >= current_proj_y:
                breakout = "WICK_FAKEOUT"     # Rechazo por mecha (falso quiebre)

        return {
            "kind": kind,
            "origin_idx": idx1,
            "pivot_idx": idx2,
            "origin_ts": candles[idx1]["ts"],
            "pivot_ts": candles[idx2]["ts"],
            "y1": round(y1, 2),
            "y2": round(y2, 2),
            "slope": round(slope, 4),
            "current_y": round(current_proj_y, 2),
            "length": length,
            "seriesLength": series_len,
            "hits": hits,
            "points": points,
            "points2x": points2x,
            "bounceUp": bounce_up,
            "peaksUp": peaks_up,
            "bounceDown": bounce_down,
            "peaksDown": peaks_down,
            "violations": violations,
            "priceDev25": round(price_dev25, 4),
            "priceDev50": round(price_dev50, 4),
            "priceDev75": round(price_dev75, 4),
            "score": round(score, 2),
            "breakout": breakout
        }

    def compute_all_trendlines(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calcula hasta 2,000 vectores candidatos simultáneos conectando pivotes fractales,
        aplica scoring matemático y filtra según Quality Filter (Most Relevant: Top 1%).
        """
        n = len(candles)
        if n < 15:
            return {"active_lines": [], "top_score": 0.0, "total_candidates": 0, "atr": 1.5}

        atr = calc_atr(candles, 14)
        pivots_n_hi, pivots_n_lo = self.detect_pivots(candles, self.window_n)
        pivots_2n_hi, pivots_2n_lo = self.detect_pivots(candles, self.window_n * 2)
        island_gaps = self.detect_island_gaps(candles, atr)

        candidates = []
        vector_count = 0
        max_vectors = 2000

        # Candidatos de Resistencia (conectar pares de pivotes altos)
        for i in range(len(pivots_n_hi)):
            for j in range(i + 1, len(pivots_n_hi)):
                if vector_count >= max_vectors:
                    break
                p1, p2 = pivots_n_hi[i], pivots_n_hi[j]
                line = self.evaluate_trendline(
                    candles, p1, p2, "RESISTANCE",
                    pivots_n_hi, pivots_2n_hi, island_gaps, atr
                )
                if line:
                    candidates.append(line)
                vector_count += 1

        # Candidatos de Soporte (conectar pares de pivotes bajos)
        for i in range(len(pivots_n_lo)):
            for j in range(i + 1, len(pivots_n_lo)):
                if vector_count >= max_vectors:
                    break
                p1, p2 = pivots_n_lo[i], pivots_n_lo[j]
                line = self.evaluate_trendline(
                    candles, p1, p2, "SUPPORT",
                    pivots_n_lo, pivots_2n_lo, island_gaps, atr
                )
                if line:
                    candidates.append(line)
                vector_count += 1

        # Ordenar por Score descendente
        candidates.sort(key=lambda x: x["score"], reverse=True)
        total_valid = len(candidates)

        # Aplicar Quality Filter (Top 1% percentil, Top 10%, o Unfiltered)
        if self.quality_filter.lower() == "most relevant":
            top_k = max(2, int(math.ceil(total_valid * 0.01))) if total_valid > 0 else 0
            # Asegurar al menos 1 soporte y 1 resistencia si existen
            res_lines = [c for c in candidates if c["kind"] == "RESISTANCE"]
            sup_lines = [c for c in candidates if c["kind"] == "SUPPORT"]
            selected = []
            if res_lines:
                selected.extend(res_lines[:max(1, top_k // 2)])
            if sup_lines:
                selected.extend(sup_lines[:max(1, top_k // 2)])
            active_lines = selected if selected else candidates[:top_k]
        elif self.quality_filter.lower() == "moderately relevant":
            top_k = max(4, int(math.ceil(total_valid * 0.10)))
            active_lines = candidates[:top_k]
        else:
            active_lines = candidates[:15]

        top_score = active_lines[0]["score"] if active_lines else 0.0

        return {
            "active_lines": active_lines,
            "top_score": top_score,
            "total_candidates": total_valid,
            "atr": atr,
            "pivots_count": len(pivots_n_hi) + len(pivots_n_lo),
            "island_gaps_count": len(island_gaps)
        }
