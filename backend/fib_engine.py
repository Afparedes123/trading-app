from typing import List, Dict, Any, Optional

class TrendSpiderAutoFibs:
    """
    Construcción de Retrocesos de Fibonacci Automáticos (Auto-Fibs).
    Hereda dinámicamente la configuración del motor de tendencias (Analysis Type y Drawing Input)
    para mantener coherencia estructural sin parámetros arbitrarios.
    """
    def __init__(
        self,
        analysis_type: str = "Standard",  # "Original" (Macro), "Enhanced" (Micro/Scalp), "Standard"
        drawing_input: str = "Wick",      # "Wick" (H/L) o "Body" (O/C)
        reverse: bool = False             # Invertir 0% y 100%
    ):
        self.analysis_type = analysis_type
        self.drawing_input = drawing_input
        self.reverse = reverse

    def _get_candle_extremes(self, candle: Dict[str, Any]):
        if self.drawing_input.lower() == "body":
            hi = max(candle["open"], candle["close"])
            lo = min(candle["open"], candle["close"])
        else:
            hi = candle["high"]
            lo = candle["low"]
        return float(hi), float(lo)

    def compute_auto_fibs(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(candles)
        if n < 10:
            return {}

        # 1. Selección de anclajes según Analysis Type heredado
        if self.analysis_type.lower() == "original":
            # Macro dominante: máximo y mínimo absoluto en toda la ventana histórica analizada
            window = candles
            highs = [self._get_candle_extremes(c)[0] for c in window]
            lows = [self._get_candle_extremes(c)[1] for c in window]
            max_p = max(highs)
            min_p = min(lows)
            max_idx = highs.index(max_p)
            min_idx = lows.index(min_p)
        elif self.analysis_type.lower() == "enhanced":
            # Microestructura: último impulso fractal corto (menor distancia entre velas, ventana corta ~15-20 velas)
            sub_window = candles[-20:] if n >= 20 else candles
            highs = [self._get_candle_extremes(c)[0] for c in sub_window]
            lows = [self._get_candle_extremes(c)[1] for c in sub_window]
            max_p = max(highs)
            min_p = min(lows)
            offset = n - len(sub_window)
            max_idx = offset + highs.index(max_p)
            min_idx = offset + lows.index(min_p)
        else:
            # Standard: pierna de tendencia intermedia (últimas 35-45 velas)
            sub_window = candles[-45:] if n >= 45 else candles
            highs = [self._get_candle_extremes(c)[0] for c in sub_window]
            lows = [self._get_candle_extremes(c)[1] for c in sub_window]
            max_p = max(highs)
            min_p = min(lows)
            offset = n - len(sub_window)
            max_idx = offset + highs.index(max_p)
            min_idx = offset + lows.index(min_p)

        # Determinar dirección del impulso dominante:
        # Si el mínimo ocurrió antes del máximo -> Impulso ALCISTA (origen en mínimo, fin en máximo)
        # Si el máximo ocurrió antes del mínimo -> Impulso BAJISTA (origen en máximo, fin en mínimo)
        if min_idx < max_idx:
            impulse_dir = "BULLISH" # Impulso hacia arriba, retrocede hacia abajo
            origin_p = min_p
            peak_p = max_p
            origin_ts = candles[min_idx]["ts"]
            peak_ts = candles[max_idx]["ts"]
        else:
            impulse_dir = "BEARISH" # Impulso hacia abajo, retrocede hacia arriba
            origin_p = max_p
            peak_p = min_p
            origin_ts = candles[max_idx]["ts"]
            peak_ts = candles[min_idx]["ts"]

        span = peak_p - origin_p
        abs_span = abs(span)
        if abs_span < 0.2:
            abs_span = 1.0

        # Secuencia estándar de ratios de Fibonacci TrendSpider
        # 0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618
        standard_ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618]
        levels = {}

        for r in standard_ratios:
            ratio_eff = (1.0 - r) if self.reverse else r
            # En un impulso alcista: 0% está en peak_p, 100% en origin_p
            # Retroceso r = peak_p - (peak_p - origin_p) * r
            if impulse_dir == "BULLISH":
                price_lvl = peak_p - (abs_span * ratio_eff) if not self.reverse else origin_p + (abs_span * ratio_eff)
            else:
                price_lvl = peak_p + (abs_span * ratio_eff) if not self.reverse else origin_p - (abs_span * ratio_eff)

            levels[str(r)] = round(price_lvl, 2)

        # Zona dorada ("Full Mid", entre 0.382 y 0.618, con núcleo OTE 0.5 - 0.618)
        golden_zone_low = min(levels["0.382"], levels["0.618"])
        golden_zone_high = max(levels["0.382"], levels["0.618"])

        # Estado actual del precio respecto al retroceso
        live_price = candles[-1]["close"]
        if impulse_dir == "BULLISH":
            current_retracement = round((peak_p - live_price) / abs_span, 3)
        else:
            current_retracement = round((live_price - peak_p) / abs_span, 3)

        in_golden_zone = (golden_zone_low <= live_price <= golden_zone_high)

        return {
            "analysis_type": self.analysis_type,
            "drawing_input": self.drawing_input,
            "impulse_direction": impulse_dir,
            "origin_price": round(origin_p, 2),
            "peak_price": round(peak_p, 2),
            "origin_ts": origin_ts,
            "peak_ts": peak_ts,
            "range": round(abs_span, 2),
            "levels": levels,
            "golden_zone": {
                "low": round(golden_zone_low, 2),
                "high": round(golden_zone_high, 2),
                "in_zone": in_golden_zone
            },
            "current_retracement": current_retracement,
            "reverse": self.reverse
        }
